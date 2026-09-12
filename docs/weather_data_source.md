# AeroCast-NCR Weather Data Layer

> Weather data source, normalization, storage, and API for the Delhi NCR
> coupled forecasting system. This layer feeds weather observations into
> forecasting, inversion/PBL analysis, and fire-transport features. **No ML is
> performed here** — this is the ingestion/normalisation/storage/API tier.

---

## 1. Source selection

### Chosen source: **Open-Meteo** (`https://api.open-meteo.com`, free, no API key)

Open-Meteo is an open-source weather API that exposes reanalysis and forecast
models (ERA5, GFS, ICON, ECMWF IFS) as JSON. It is the only free source that
provides **all seven required variables in one call, including a real PBL
height**, without credentials.

### Alternatives considered (and why they lost)

| Candidate | Verdict | Reason |
|-----------|---------|--------|
| **Open-Meteo** | ✅ **chosen** | Free, keyless, 0–7 day forecast + archive (ERA5) back to 1940, single HTTP call returns all 7 variables incl. `boundary_layer_height`; verified live HTTP 200 (see §4). |
| IMD API (data.gov.in / MOSDAC) | ❌ | Needs registration keys; granular surface METAR/station data only; no boundary-layer height; IMD radar not exposed as a public REST feed. |
| ECMWF ERA5 (Copernicus CDS) | ⚠️ production upgrade | The *reference* PBL/temperature source, but requires an account, API key, licence acceptance, and large CDS downloads — not suitable for the prototype's hourly refresh path. Documented as the production-scale upgrade. |
| NOAA GFS (NOMADS) | ❌ | Free but GRIB-only and historically spotty; heavier parsing (pygrib/cfgrib) for no accuracy gain over Open-Meteo's ERA5-backed archive. |
| SYNOP / METAR stations | ❌ | Delhi/IGI + a handful of NCR airports; no PBL height, no precipitation-quality guarantee, irregular sampling. |

Open-Meteo's underlying models are the same global NWP products a bespoke
IMD/ERA5 pipeline would use; using the API is therefore a *delivery* choice,
not an accuracy downgrade — with the honest caveat documented here that
boundary-layer height comes from the model (~9 km grid) rather than a Delhi
sounding.

### Model grids behind Open-Meteo (as stated by the service itself)

- Forecast: **ECMWF IFS 0.25°** (primary for NCR) with GFS/ICON fallbacks.
- Archive: **ERA5** reanalysis, the same product NCMRWF/IMD use for research.
- PBL height (`boundary_layer_height`): supplied by the active forecast model
  (ERA5 PBL in the archive). **It is a real atmospheric field, not a derived
  heuristic, and is never invented or patched with fallback constants** — when
  the value is missing for a given hour, the API returns it as `null` and the
  downstream PBL/inversion logic handles `null` explicitly (see §2).

---

## 2. Data normalisation

### Variable mapping (raw → stored → API field)

| Required variable | Open-Meteo hourly field | DB column (`weather_observations`) | API field |
|-------------------|-------------------------|------------------------------------|-----------|
| temperature | `temperature_2m` (degC) | `temperature` | `temperature` |
| humidity | `relative_humidity_2m` (%) | `humidity` | `humidity` |
| pressure | `pressure_msl` (hPa) + `surface_pressure` (hPa) | `pressure_msl`, `surface_pressure` | `pressure_msl`, `surface_pressure` |
| wind_speed | `wind_speed_10m` (km/h) | `wind_speed` | `wind_speed` |
| wind_direction | `wind_direction_10m` (deg) | `wind_direction` | `wind_direction` |
| precipitation | `precipitation` (mm) | `precipitation` | `precipitation` |
| PBL height | `boundary_layer_height` (m) | `pbl_height` | `pbl_height` |

Extra persisted fields: `cloud_cover`, and vertical pressure-level temperatures
(`temperature_{1000,925,850,700}hPa`) + geopotential heights used by the
inversion layer (`docs/SIH_FINAL_COMPLIANCE.md`, R1/R2).

### Normalisation rules (`backend/app/services/refresh_service.py`)

1. **Numeric coercion** — every raw value passes through `_to_float()`
   (`None`-safe, NaN→`None`, prevents string junk from ever reaching the DB).
2. **Timestamp convention (UTC, naive)** — the API is queried with
   `timezone=UTC` (`utc_offset_seconds = 0`), and times are parsed with
   `pd.to_datetime(..., utc=True).dt.tz_localize(None)`. Stored datetimes are
   therefore **naive UTC by convention**: the wall clock is unambiguous and
   Pydantic serializes them with `Z` when served. The refresh window is also
   computed in UTC (`datetime.utcnow()`), so query-window math never mixes
   local and UTC clocks (the pre-existing Asia/Kolkata fetch had a latent
   5.5 h skew — fixed).
3. **Spatial association** — each reading carries `station_id` plus the
   station lat/lon (`latitude`/`longitude` columns captured at fetch time), so
   every weather row is spatially anchored to an NCR station.
4. **Upsert / dedup** — a `(station_id, timestamp)` uniqueness rule is applied
   at ingest; already-stored timestamps are skipped, keeping refresh idempotent.

---

## 3. Storage (PostgreSQL)

- Table: **`weather_observations`**, model `WeatherReading`
  (`backend/app/models/db_models.py`).
- Index: `idx_weather_station_time (station_id, timestamp)` for the latest /
  history query paths.
- Connection: SQLAlchemy engine from `DATABASE_URL`
  (`.env` → `postgresql://aerocast:...@localhost:5432/aerocast_ncr`).
- Schema lifecycle: Alembic migrations + additive `apply_migrations()` for the
  dev SQLite path. Columns are additive-only; the existing DB is preserved.

## 4. API surface

| Route | Purpose |
|-------|---------|
| `GET /api/weather/latest` | **One row per NCR station, newest observation each** (`GET /api/weather/latest` — implemented this layer; declared before the `{station_name}` route so `latest` is never captured as a station name) |
| `GET /api/weather/{station}` | Latest observation for one station |
| `GET /api/weather/{station}/history?hours=N` | Historical window, N ∈ [1, 720] hours, newest-first |

Response schema: `WeatherDetailResponse` (station identity + lat/lon + reading
lat/lon + all required variables + PBL height).

## 5. Error handling

| Failure | Behaviour |
|---------|-----------|
| Open-Meteo archive unreachable / non-200 | Logs warning, falls back to the live forecast API for the next 48 h (`_get_weather_df`) |
| Forecast supplement fails | Logs warning; vertical-pressure backfill is skipped, hourly surface fields unaffected |
| Response missing `hourly.time` | Returns empty frame; station is cleanly skipped (no partial rows) |
| Unknown station / no data | `HTTP 404` from the API layer |
| `hours` out of [1, 720] | FastAPI `422 Unprocessable Entity` |
| Transient DB errors | SQLAlchemy transaction rolls back; refresh reports the count actually inserted |

## 6. Refresh cadence

`refresh_weather(db)` runs per station against a 3-day lookback window. It is
invoked by the scheduled `refresh_loop` (default every 3 h) or on demand via
`run_refresh_once()` / the `aerocast-refresh` CLI. Idempotent by timestamp, so
frequent runs are safe.

## 7. Verification (this session, real end-to-end)

| Stage | Result |
|-------|--------|
| Real source | Open-Meteo forecast HTTP 200; 24/24 hourly rows with all 7 variables incl. real PBL `boundary_layer_height` (m) |
| → PostgreSQL | `refresh_weather()` inserted NCR station-hour rows into `weather_observations` (values above verified in the DB) |
| → API | `GET /api/weather/latest`, `/api/weather/{station}`, `/api/weather/{station}/history` returned the ingested readings with PBL height present |
| Tests | backend suite passes (count in session report) |