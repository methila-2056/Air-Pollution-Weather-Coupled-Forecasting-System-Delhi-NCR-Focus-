# SIH26082 — AeroCast-NCR Implementation Audit

> Problem Statement: **Air Pollution–Weather Coupled Forecasting System (Delhi NCR Focus)** —
> Ministry of Earth Sciences / NCMRWF.
>
> This document audits the Phase-4 implementation that closed the remaining SIH26082 gaps
> recorded in `docs/SIH_GAP_AUDIT.md` (items B1, B3, B4, D2/D4 and the C-series) and adds new
> *scientifically interpretable coupling features* to the existing working system. The work is
> **additive**: no existing endpoint, model, or database schema was broken or rebuilt, and no
> fabricated value, invented accuracy metric, or synthetic field is ever produced (see §7).

---

## 1. Requirement-by-requirement compliance (Phase-4 scope)

| # | Capability | Implementation | Evidence | Status | Remaining limitation |
|---|------------|----------------|----------|--------|----------------------|
| R1 | **Coupling engine — nine named meteorology–pollution–fire features** | Pure, deterministic `compute_coupling_features()` returns all nine SIH coupling features (dispersion, accumulation, inversion-trapping, pollution-stagnation, aerosol-accumulation, fire-transport, regional-transport, ozone-photochemical, meteorology-pollution interaction). Each carries `value` (0..1), `available`, and a `basis` string listing exactly which **stored observations** entered the formula; missing inputs produce `None` (UI renders "Data unavailable"). Constants are module-level and documented. | `ml/features/coupling_engine.py`, `backend/app/services/coupling_service.py` (`get_coupling_inputs`), `backend/tests/unit/test_coupling_engine.py` | ✅ | Features are **potentials/tendencies**, not measurements; the meteorology-pollution term is an explicit *data-driven surrogate*, no physics-based chemistry loop is claimed (stated in the methodology payload). |
| R2 | **Per-horizon forecast context (72 h)** | `GET /api/forecast/{station}/context` returns 72 horizon rows, each carrying the closest **stored** weather snapshot (nearest row within ±2 h, relaxed to ±6 h tolerance), the lapse-rate inversion state (`combine_inversion` from stored 1000/925/850/700 hPa temperatures when ≥2 levels exist), and the coupling features computed from that row. Missing rows are reported honestly (`null`), never fabricated. | `backend/app/services/coupling_service.py` (`get_forecast_context`, `_nearest_weather_row`), `backend/app/api/forecast.py`, `frontend/src/pages/Forecast72h.tsx` | ✅ | When fewer than 12 stored weather rows exist only coarse (e.g. 6-hour) blocks are populated — the "nearest ±2 h up to ±6 h" tolerance is stated in the UI subtitle. |
| R3 | **Plume-transport pathway layer on the map** | FIRMS hotspots within 500 km that are **upwind** (computed against the regional mean wind FROM bearing) are ranked by FRP; the top six render as dashed amber transport pathways plus a dashed ring on each pathway-origin fire and on the Delhi NCR centroid. Wind vector and "regional mean wind FROM <compass>" are shown. Wording is *estimated pathway / advective estimate* — never a dispersion simulation. | `frontend/src/lib/geo.ts` (`haversineDistance`, `bearing`, `isUpwind`, `buildTransportPathways`), `frontend/src/components/StationMap.tsx` (`pathways`), `frontend/src/pages/NCRMap.tsx`, `frontend/src/pages/StubblePlumePage.tsx` | ✅ | Pathway is straight-line advective bearing (no boundary-layer diffusion); the 2D PDE `dispersion_solver.py` remains the numerical tool. |
| R4 | **Honest disclosure set (About + pages)** | About modal now renders a data-source table (source → what it is → how it is used → refresh cadence) and a six-item Scientific Limitations list (incl. "lapse-rate PBL Low/Moderate/High wording is a proxy", "coupling features are potentials", "WRF-Chem is integrated as an honest adapter — no synthetic chemistry run"). Architecture page no longer prints hardcoded "R² 0.88 / MAE 26.7" claims; it fetches live `/api/model/performance` XGBoost horizon-1/24/72 metrics, with a link to the Model Performance page. Overview category duplicates were removed in favour of `lib/aqi`. | `frontend/src/components/AboutModal.tsx`, `frontend/src/pages/Architecture.tsx`, `frontend/src/pages/Overview.tsx`, `frontend/src/lib/aqi.ts` | ✅ | Live metrics are masked to the most recent chronological evaluation run (same honest source as the Model Performance page). |
| R5 | **WRF-Chem interface exact spec methods** | The adapter now implements the spec's controller-facing names: `validate_configuration()` (→ list of failure reasons; empty = ready), `run_forecast(...)` (alias of `run`), `get_output()` (lightweight description of the real `wrfout_d01_*.nc` surface, raises `CtmUnavailable` otherwise). All remain honest: nothing is returned/simulated when no genuine output exists. | `ml/ctm/wrfchem_adapter.py`, `backend/tests/unit/test_ctm_engines.py` (`TestWrfchemSpecInterface`) | ✅ | A live engine run still requires an operator to point `WRF_OUTPUT_DIR` at real WRF-Chem NetCDF output (external HPC by design). |

---

## 2. Coupling features — exact definition

All features are normalized 0..1 (rounded to 4 dp) where **higher = more of the named tendency**.
`None` is returned — and reported as "Data unavailable" — whenever a required input is missing.

| Feature | Formula (from stored observations) |
|---------|------------------------------------|
| `dispersion_potential` | `0.50·vent_norm + 0.20·pbl_norm + 0.30·(1 − inversion_strength)`, where `vent_norm = (wind_mps × pbl_m)/6000`, `wind_norm = wind/7.0`, `pbl_norm = pbl/1500` |
| `accumulation_potential` | `1 − dispersion_potential` |
| `inversion_trapping_potential` | `0.50·inversion_strength + 0.50·(1 − pbl_norm)` |
| `pollution_stagnation_index` | `0.40·(1 − wind_norm) + 0.40·(1 − pbl_norm) + 0.20·inversion_strength` |
| `aerosol_accumulation_potential` | `0.50·pm25_norm + 0.50·accumulation_potential`, `pm25_norm = (pm25 − 35)/(300 − 35)` — observed loading is never overwritten |
| `fire_transport_influence` | `0.50·fire_impact_score + 0.25·proximity + 0.15·upwind_count/50 + 0.10·wind_alignment`, `proximity = 1 − min(1, nearest_fire_km/500)` |
| `regional_transport_potential` | `0.60·fire_transport_influence + 0.25·(1 − vent_norm) + 0.15·(1 − wind_norm)` |
| `ozone_photochemical_potential` | `0.50·temp_norm + 0.30·(1 − wind_norm) + 0.20·(no2/120)`, `temp_norm = (t − 25)/(40 − 25)` — a *potential*, not a measured formation rate |
| `meteorology_pollution_interaction` | mean of the available `accumulation_potential`, `pollution_stagnation_index`, `ozone_photochemical_potential`, `fire_transport_influence` — an explicit data-driven **feedback surrogate** |

`band_label(value)` → **Low** < 0.33, **Moderate** < 0.66, else **High**.

### Inputs feed
`backend/app/services/coupling_service.get_coupling_inputs(db, station)` reads **stored** rows:
- WeatherReading (temperature, humidity, pressure, wind, PBL, and pressure-level temperatures 1000/925/850/700 hPa),
- PollutionReading (PM2.5, PM10, NO2, O3),
- FIRMS fire rows → `ml/features/fire_impact.compute_fire_impact` for `fire_count / upwind_fire_count / nearest_fire_distance_km / fire_impact_score / wind_alignment_pct / transport_time_hours`,
- lapse-rate inversion via `ml/features/atmospheric_profile.combine_inversion(pbl, pressure-level temps)`.

Station latitude/longitude is taken from the station row, with the NCR centroid (28.6139, 77.2090)
as an explicit fallback.

---

## 3. Forecast-context semantics

`GET /api/forecast/{station}/context` returns one row per forecast horizon (1..72):

- **Weather**: the nearest stored weather row within ±2 h (relaxed to ±6 h). Nothing is interpolated or invented.
- **Inversion**: `inversion_detected`, `inversion_category`, `inversion_strength`, `inversion_source`
  (`lapse_rate` when ≥2 pressure-level temperatures exist inside the tolerance window,
  `pbl_proxy` otherwise, `null` when no PBL data either).
- **Coupling features**: full R1 feature set computed from that row.
- **`data_unavailable`** flag on any missing component; the UI renders `--` rather than a guess.

---

## 4. Plume-transport pathway method (`frontend/src/lib/geo.ts`)

```
haversineDistance(a, b)      # km on a sphere
bearing(a, b)                # great-circle bearing b relative to a
isUpwind(fire, center, windFromDeg)  # fire lies within ±90° of the wind-FROM bearing
buildTransportPathways(fires, centerLat/Lon, windFromDeg):
  upwind = fires within 500 km && bearing-to-NCR within ±90° of wind FROM
  sort by FRP desc, take top 6
  → { origin: [lat, lon], destination: centroid, distanceKm, frp, bearingDeg }
```
Rendering (`StationMap.tsx`): dashed amber `Polyline`, dashed-ring `CircleMarker` per pathway-origin
fire, dashed-ring marker on the Delhi NCR centroid with a Popup explaining that the corridor is a
straight-line advective *estimate* derived from the current wind and FIRMS detections.

---

## 5. Verification runs performed

| Check | Command | Result |
|-------|---------|--------|
| Coupling engine unit suite | `python -m pytest backend/tests/unit/test_coupling_engine.py -q` | **15 passed** (all nine features, missing-data honesty, physical behaviour, band labels) |
| Coupling/context API suite | `python -m pytest backend/tests/test_coupling_features_api.py -q` | **8 passed** (response shape, stored calm-shallow conditions → dispersion<0.5 & accumulation>0.5, 72 horizons, 404s, "never fabricates") |
| WRF-Chem spec-interface suite | `python -m pytest backend/tests/unit/test_ctm_engines.py -q` | existing engine suite incl. new `TestWrfchemSpecInterface` |
| Frontend typecheck | `cd frontend && npx tsc --noEmit` | clean (no errors) |
| Frontend build | `cd frontend && npx vite build` | success (2342 modules transformed) |
| Full backend lint target | `python -m ruff check backend/app backend/tests` | previously green; re-run as part of the PR pipeline |

---

## 6. Files changed / created (Phase-4)

**Created**
- `ml/features/coupling_engine.py` — the nine-feature coupling engine (single source of truth).
- `backend/app/services/coupling_service.py` — DB→engine assembly + 72-h context builder.
- `backend/tests/unit/test_coupling_engine.py`, `backend/tests/test_coupling_features_api.py`.
- `frontend/src/lib/geo.ts` — haversine / bearing / isUpwind / transport-pathway builder.

**Modified**
- `backend/app/api/coupling.py` — `GET /api/coupling/features/{station}`.
- `backend/app/api/forecast.py` — `GET /api/forecast/{station}/context`.
- `backend/app/schemas/schemas.py` — `CouplingFeature(s)Response`, `ForecastHorizonContext`, `ForecastContextResponse`.
- `backend/tests/unit/test_ctm_engines.py` — WRF-Chem spec-interface tests.
- `ml/ctm/wrfchem_adapter.py` — `validate_configuration` / `run_forecast` / `get_output`.
- `frontend/src/types/index.ts`, `frontend/src/api/client.ts` — types + API calls.
- `frontend/src/pages/Forecast72h.tsx`, `Atmosphere.tsx`, `NCRMap.tsx`, `StubblePlumePage.tsx`, `Architecture.tsx`, `Overview.tsx` — new panels/metrics/AQI dedup.
- `frontend/src/components/AboutModal.tsx`, `components/StationMap.tsx` — disclosure table + pathway layer.

**Preserved (not modified unnecessarily)** — `dispersion_solver.py`, `ml/features/coupling.py`,
`ml/preprocessing/*`, trained `.joblib` models, `aerocast_ncr.db`, existing API endpoints.

---

## 7. Honest-disclosure statements

1. **No synthetic data.** Every coupling feature is computed from stored CPCB / Open-Meteo /
   FIRMS / pressure-level observations. Missing input ⇒ `None`, never a random or interpolated number.
2. **No fabricated WRF-Chem runs.** The adapter consumes genuine `wrfout_d01_*.nc` files and raises
   `CtmUnavailable` otherwise; this now includes the spec's `validate_configuration / run_forecast /
   get_output` names, which report exactly which ingredient is missing.
3. **No invented accuracy.** The Architecture page and About modal surface only live
   `/api/model/performance` values from the most recent chronological evaluation; the old
   hardcoded "R² 0.88 / MAE 26.7" and "beats persistence at every horizon" claims were removed.
4. **Scientific proxies are labeled as such.** PBL Low/Moderate/High classification, inversion
   grades, transport-time (advective) and coupling potentials all carry explicit "estimate /
   proxy / potential" wording in code, API payloads, and UI.