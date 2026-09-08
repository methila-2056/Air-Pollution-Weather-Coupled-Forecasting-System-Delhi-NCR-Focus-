# AeroCast-NCR

**AI-Powered 72-Hour Air Quality & Pollution-Plume Forecasting for Delhi NCR**

> Problem Statement: **SIH26082** · Ministry of Earth Sciences · NCMRWF

[![CI](https://github.com/aerocast-ncr/aerocast-ncr/actions/workflows/ci.yml/badge.svg)](https://github.com/aerocast-ncr/aerocast-ncr/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Tests](https://img.shields.io/badge/tests-208%20passed-green)

AeroCast-NCR fuses **real CPCB monitoring, Open-Meteo weather, NASA FIRMS active
fires and ERA5 meteorology** into a machine-learning 72-hour pollutant forecast
for every station in the Delhi NCR belt — with an explicit **two-way
weather–chemistry coupling** module, a **high-resolution gridded spatial
surface**, and a **numerical advection–diffusion dispersion core** that models
how stubble-burning plumes disperse under prevailing weather.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Data Pipeline](#data-pipeline)
- [Quick Start — Docker](#quick-start--docker)
- [Quick Start — Bare Metal](#quick-start--bare-metal)
- [API Summary](#api-summary)
- [Frontend Pages](#frontend-pages)
- [Testing](#testing)
- [Deployment](#deployment)
- [Documentation](#documentation)
- [Honest Scope](#honest-scope)
- [License](#license)

---

## Features

| Capability | How it works | Verify |
|------------|--------------|--------|
| **Two-way weather–chemistry coupling** | Aerosol AOD → solar attenuation → PBL suppression → stability feedback (`ml/features/coupling.py`, `coupled_loop.py`) | `GET /api/coupling/{station}`, `POST /api/forecast/coupled` |
| **72-hour AQI forecast** | Persistence / Random Forest / XGBoost, all **six criteria pollutants** × horizons {1,6,12,24,48,72} | `POST /api/forecast/generate`, `GET /api/forecast/{station}` |
| **Stubble-plume dispersion** | Finite-difference advection–diffusion–deposition solver with FRP fire point sources, wind/PBL/rain forcing | `GET /api/dispersion/forecast`, `ml/features/dispersion_solver.py` |
| **Inversion trapping** | Stability index couples inversion directly to PBL height | `GET /api/inversion/{station}` |
| **NCR-wide spatial mapping** | ~2.2 km gridded AQI surface (IDW + downwind advection) plus live numerical field | `GET /api/grid/forecast`, `/spatial` page |
| **All criteria pollutants** | PM2.5, PM10, O3, NO2, SO2, CO | `predict_pollutants`; `TestForecastCompletePollutantSet` |
| **Actionable alerts & explainability** | Alert engine + SHAP feature attribution + natural-language explanations | `GET /api/alerts`, `GET /api/explanation/{station}` |
| **Live data refresh** | Scheduler + one-shot CLI pulls weather/fire/pollution automatically | `make refresh-data`, `LIVE_REFRESH_ENABLED=true` |

See [`docs/ps_mapping.md`](docs/ps_mapping.md) for the requirement-by-requirement
mapping to the official problem statement.

## Architecture

```
CPCB (Pollution) · Open-Meteo (Weather) · NASA FIRMS (Fire) · ERA5 (Atmosphere)
        │
        ▼
 Data Fusion & Feature Engineering        ┌───────────────────────────────┐
        │                                 │   backend/app  FastAPI +      │
        ▼                                 │   SQLAlchemy + Alembic        │
 XGBoost / ML Forecasting                 │   api · services · models     │
        │                                 │                               │
        ▼                                 │   React + TS + Vite frontend  │
 72-Hour Pollutant Forecast  ───────────► │   (nginx reverse-proxy)       │
        │                                 │                               │
        ▼                                 │   PostgreSQL (prod) /         │
 AQI Engine → Dashboard → Alerts → SHAP   │   SQLite (dev)                │
 → Coupling → Grid → Dispersion           └───────────────────────────────┘
```

**Stack** — *Backend:* Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL
(prod) / SQLite (dev). *Frontend:* React, TypeScript, Vite, Tailwind CSS,
Recharts, Leaflet. *ML:* XGBoost, Scikit-learn, SHAP, NumPy, Pandas.

## Data Pipeline

1. **Acquire** — real data via `scripts/download_*.py` (CPCB poll, Open-Meteo
   weather, NASA FIRMS fire, Copernicus ERA5 atmosphere) or the live refresh
   service (`backend/app/services/refresh_service.py`).
2. **Build** — `scripts/build_dataset.py` fuses raw readings into time-aligned
   station series with engineered features.
3. **Train** — `python -m ml.training.trainer` fits per-pollutant, per-horizon
   models; `scripts/evaluate_models.py` re-scores them.
4. **Serve** — FastAPI loads the persisted `.joblib` models and forecasts on
   demand, feeding AQI, alerts, coupling, grid and dispersion endpoints.

## Quick Start — Docker

```bash
# 1. Clone and configure
cp .env.example .env            # local defaults
cp docs/deploy.env.example deploy.env   # (optional) production overrides

# 2. Build and start the full stack (Postgres + API + frontend)
docker compose up -d --build

# 3. Boot applies Alembic migrations automatically; seed + live refresh run in-app

# 4. Access
#    Frontend : http://localhost:5173
#    API docs  : http://localhost:8000/docs
#    Health    : http://localhost:8000/health
```

Stop with `docker compose down` (add `-v` to also drop the `pgdata` volume).

## Quick Start — Bare Metal

```bash
# Backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
python -m alembic upgrade head                       # create/migrate the schema
uvicorn app.main:app --host 0.0.0.0 --port 8000      # run from backend/

# Frontend (separate terminal)
cd frontend && npm install && npm run dev            # http://localhost:5173
```

Download data and build the dataset with
`scripts/fetch_all.{sh,ps1}` or `python scripts/build_dataset.py`.

## API Summary

All endpoints live under `/api` (interactive docs at `/docs`):

| Area | Endpoints |
|------|-----------|
| Station & current AQI | `GET /stations`, `GET /stations/{station}`, `GET /current/{station}` |
| Forecast | `POST /forecast/generate`, `GET /forecast/{station}`, `GET /forecast/ncr`, `GET /forecast/comparison/{station}`, `POST /forecast/coupled` |
| Weather | `GET /weather/{station}`, `GET /weather/{station}/history` |
| Inversion / Fire | `GET /inversion/{station}`, `GET /fire-activity`, `GET /fire/transport`, `GET /plume-risk` |
| Spatial | `GET /grid/forecast`, `GET /grid/overview`, `GET /dispersion/forecast` |
| Coupling & explainability | `GET /coupling/{station}`, `GET /explanation/{station}` |
| Alerts & metrics | `GET /alerts`, `GET/ POST /model/metrics` |
| Summary & export | `GET /summary`, `GET /export/forecast.csv`, `GET /health` |

Request/response schemas are described in
[`docs/api.md`](docs/api.md) and introspectable at `/docs`.

## Frontend Pages

`/overview` (NCR KPIs) · `/forecast-72h` (multi-horizon charts) · `/ncr-map`
(Leaflet station map) · `/spatial` (grid + dispersion heatmap) ·
`/atmosphere` · `/alerts` · `/ai-explanation` (SHAP) · `/model-performance` ·
`/stubble-plume`

## Testing

```bash
python -m pytest backend/tests -q      # 200+ unit + integration tests
python -m ruff check backend/app backend/tests   # lint (scoped)
cd frontend && npm run build           # type-check + production build
```

`make test`, `make test-unit`, `make test-integration`, `make build` and
`make refresh-data` are provided as convenience targets — see the `Makefile`.

## Deployment

- **Compose runbook** — `docs/deployment.md` (migration flow, live refresh,
  reverse-proxy/HTTPS, `pgdata` backup/restore, first-boot checks).
- **Production env template** — `docs/deploy.env.example`.
- **CI** — `.github/workflows/ci.yml`: ruff + pytest on the backend job, a
  dedicated Alembic-on-PostgreSQL migration job, and a frontend tsc/vite build.

## Documentation

| Doc | Contents |
|-----|----------|
| [`docs/methodology.md`](docs/methodology.md) | AQI, features, models, SHAP, coupling, dispersion (§9 surrogate vs. WRF-Chem) |
| [`docs/architecture.md`](docs/architecture.md) | System layers & component diagram |
| [`docs/ps_mapping.md`](docs/ps_mapping.md) | Requirement → implementation mapping |
| [`docs/deployment.md`](docs/deployment.md) | Deploy runbook & environment reference |
| [`docs/api.md`](docs/api.md) | API reference |
| [`docs/dataset.md`](docs/dataset.md) | Data sources & schema |
| [`docs/reproducibility.md`](docs/reproducibility.md) | Reproducible build/train pipeline |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |

## Honest Scope

The problem statement names "WRF-Chem or similar coupled frameworks". Shipping
compiled WRF-Chem is an HPC-scale effort (Fortran toolchain, MOZART/GOCART
chemistry, full emission inventories). AeroCast-NCR therefore implements a
**physics-informed numerical surrogate** — a vectorised finite-difference
transport core with explicit two-way coupling — that delivers the PS's
*functional* outcomes (plume dispersion prediction, meteorological interlink,
72 h AQI, NCR-wide coverage) reproducibly on commodity hardware. See
[`docs/methodology.md` §9.1](docs/methodology.md) for the tradeoff table,
validation strategy and what a literal WRF-Chem deployment would require.

## License

MIT — see [`LICENSE`](LICENSE).
