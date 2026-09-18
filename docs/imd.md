# IMD weather integration (WS-3)

## Purpose

The problem statement (R9) names IMD as a data source. This workstream adds a
**gated adapter** for the official India Meteorological Department API gateway
(`api.imd.gov.in`), surfacing *genuine* IMD city weather forecasts
(7-day max/min temperature + condition) for Delhi/Safdarjung — the anchor IMD
city for the NCR domain (all 17 curated monitors sit within ~30 km of it).

## The API reality (verified)

IMD do **not** publish an open keyless endpoint:

- `https://api.imd.gov.in/api/v1/cityforecast?id=42182` →
  **HTTP 401 Unauthorized** (registered + key/IP-whitelisted users only).
- `https://mausam.imd.gov.in/api/current_wx_api.php` → **HTTP 401 Unauthorized**.

A live unauthenticated probe (urllib, this repo's environment) returned 401 for
both endpoints. That is exactly what the adapter reports, rather than
pretending IMD data exists.

## Honesty gates

- `imd_weather.imd_reasons()` explains precisely what is missing: `IMD_API_KEY`
  not configured, 401 (need key/IP whitelist), network failure, or a malformed
  payload. Nothing synthetic is ever produced.
- `fetch_city_forecast()` parses the **real** IMD JSON using the public
  API-reference field names (`Todays_Forecast_Max_Temp`,
  `Day_2_Max_Temp`…) and raises `IMDApiUnavailable` otherwise.
- `scripts/fetch_imd_weather.py` writes an *empty* `data/imd/imd_forecast.csv`
  on failure, and `scripts/build_dataset.py::load_imd` then prints a warning
  and keeps using Open-Meteo.

## Data flow

```text
api.imd.gov.in (/api/v1/cityforecast?id=42182)     [needs IMD_API_KEY / IP whitelist]
   – fetch_imd_weather.py  (or the live API endpoint below)
        |
        v
data/imd/imd_forecast.csv
  columns: time, station, imd_max_temp_c, imd_min_temp_c, imd_condition, imd_source
        |
        v
scripts/build_dataset.py  → imd_* feature columns in the coupled dataset
```

## Usage

```powershell
# 1. Live API endpoint (backend up): GET /api/imd/forecast?station_id=42182
#    -> {available: true, station, days:[…]} when authorised,
#    -> {available: false, reasons:[…]} otherwise (honest 401).

# 2. Offline fetch into the dataset (needs IMD_API_KEY env var):
python -m scripts.fetch_imd_weather --station-id 42182
python -m scripts.fetch_imd_weather --no-download        # prints the planned request
```

Set `IMD_API_KEY` in `.env` (mapped by `backend/app/config.py` →
`Settings.imd_api_key`). The gateway also requires the calling IP to be
whitelisted by IMD.

## Files

- `backend/app/services/imd_weather.py` — fetch/parse/reasons/dataframe (gated).
- `backend/app/api/imd.py` — `GET /api/imd/forecast` (registered in `main.py`).
- `backend/app/schemas/schemas.py` — `ImdForecastDay`, `ImdForecastResponse`.
- `backend/app/config.py` — `imd_api_key`, `imd_station_id`, `imd_api_base`.
- `scripts/fetch_imd_weather.py` — offline CLI writing `data/imd/imd_forecast.csv`.
- `scripts/build_dataset.py` — `load_imd()` + `imd_*` merge (honest skip).
- `backend/tests/unit/test_imd_weather.py` — 13 tests (401/no-key reasons,
  parsing, malformed rejection, router available/unavailable, update glue).