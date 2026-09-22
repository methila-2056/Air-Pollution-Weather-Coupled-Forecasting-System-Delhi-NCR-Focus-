# scripts/ — Developer & Data-Pipeline Utilities

Command-line utilities for downloading real data, building the coupled
training dataset, refreshing the live database, and sanity-checking the local
environment. **Every script is run from the repository root** so `ml/`,
`models/`, `data/` and `backend/` resolve correctly.

## Data acquisition

| Script | Purpose |
|--------|---------|
| `download_pollution.py` | CPCB air-quality readings via the opencity.in CKAN mirror (real CPCB-sourced Delhi data) |
| `download_weather.py` | Historical Open-Meteo weather for the Delhi-NCR stations |
| `download_fire.py` | NASA FIRMS active-fire (VIIRS) detections for the Punjab/Haryana domain |
| `download_atmosphere.py` | Era5 atmospheric data via the Copernicus CDS API (single-level temperatures, pressure, BLH) |
| `download_hysplit_gdas.py` | NOAA ARL GDAS1 meteorological input files from `ready.noaa.gov` for real HYSPLIT runs |
| `fetch_imd_weather.py` | Official IMD `api.imd.gov.in` city forecasts into `data/imd/` (gated on key/IP whitelist) |
| `generate_fire_data.py` | Seasonally-realistic demo fire readings for the 2023–2024 training window (no API key needed) |

## Dataset & model build

| Script | Purpose |
|--------|---------|
| `build_dataset.py` | Merge weather, pollution, fire and atmosphere into the coupled feature dataset |
| `build_training_dataset.py` | Build the leak-free, chronologically-split training panel from the backend DB (CSV + Parquet + summary JSON) |
| `evaluate_models.py` | Re-evaluate every trained model from its persisted predicted-vs-actual CSV and recompute held-out metrics |

## Database & operations

| Script | Purpose |
|--------|---------|
| `seed_stations.py` | Seed the database with the 17 stations + historic weather from CSV |
| `backfill_pollution.py` | Backfill historical CPCB pollution for the 17 NCR stations |
| `refresh_once.py` | Run a one-shot live data refresh (weather / fire / pollution) against the configured DB |
| `run_dev.py` | Launch the local stack in one command: seed DB → backend → (optional) frontend |
| `clean_generated.py` | Remove regenerable build/data artifacts (caches, logs, local DBs, `frontend/dist`, engineered datasets); backs the `make clean-data` target. Dry-run by default, `--exec` to apply |
| `environment_check.py` | Sanity-check dependencies, model artifacts and DB connectivity before running anything |

## Wrappers

| Script | Purpose |
|--------|---------|
| `fetch_all.sh` / `fetch_all.ps1` | One-shot convenience wrapper that runs the full download pipeline (bash / PowerShell) |

## Examples

```bash
# Build the coupled training dataset
python -m scripts.build_dataset

# Sanity-check your environment first
python -m scripts.environment_check

# One-shot live refresh (requires DATABASE_URL in .env)
python -m scripts.refresh_once

# Pull official IMD forecast into data/imd/imd_forecast.csv
python -m scripts.fetch_imd_weather --station-id 42182

# Fetch GDAS1 met files for the default weekly windows (HYSPLIT input)
python -m scripts.download_hysplit_gdas --start 2025-10-01 --days 7 --out-dir data/met --no-download  # dry-run first

# Boot the full local stack (DB seed + API + optional frontend)
python -m scripts.run_dev --port 8000 --frontend

# Preview what `make clean-data` would remove (add --exec to apply)
python -m scripts.clean_generated
```