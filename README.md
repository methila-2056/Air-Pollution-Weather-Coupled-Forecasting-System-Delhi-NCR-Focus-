# AeroCast-NCR

**AI-Powered 72-Hour Air Quality & Pollution-Plume Forecasting for Delhi NCR**

> Problem Statement: **SIH26082** · Ministry of Earth Sciences (MoES) · NCMRWF

[![CI](https://github.com/methila-2056/Air-Pollution-Weather-Coupled-Forecasting-System-Delhi-NCR-Focus-/actions/workflows/ci.yml/badge.svg)](https://github.com/methila-2056/Air-Pollution-Weather-Coupled-Forecasting-System-Delhi-NCR-Focus-/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-501%20passed-green)](backend/tests)
[![Docker](https://img.shields.io/badge/docker-compose%20ready-2496ED?logo=docker&logoColor=white)](docker-compose.yml)

AeroCast-NCR fuses **official CPCB real-time monitoring (data.gov.in)**,
**Open-Meteo weather**, **NASA FIRMS active fires** and **ERA5 meteorology**
into a machine-learning 72-hour pollutant forecast for every station in the
Delhi NCR belt — with an explicit **two-way weather–chemistry coupling**
module, a **high-resolution gridded spatial surface**, and a **numerical
advection–diffusion dispersion core** that models how stubble-burning plumes
disperse under prevailing weather.

---

## Table of Contents

- [Overview](#overview)
- [Key Capabilities](#key-capabilities)
- [Architecture](#architecture)
- [Data & Machine-Learning Pipeline](#data--machine-learning-pipeline)
- [Repository Layout](#repository-layout)
- [Quick Start — Docker](#quick-start--docker)
- [Quick Start — Bare Metal](#quick-start--bare-metal)
- [API Summary](#api-summary)
- [Frontend Pages](#frontend-pages)
- [Testing & Quality Gates](#testing--quality-gates)
- [Deployment & CI/CD](#deployment--cicd)
- [Documentation](#documentation)
- [Honest Scope](#honest-scope)
- [Contributing & Security](#contributing--security)
- [License](#license)

---

## Overview

Delhi NCR experiences among the worst air quality episodes in the world,
driven by vehicular emissions, construction dust, thermal power, and
agricultural stubble burning transported into the region by north-westerly
winds. Forecasting these episodes requires more than statistical
extrapolation — it requires coupling **meteorology with chemistry**.

AeroCast-NCR delivers a production-grade, containerised forecasting system
that:

1. Ingests **real, official observations** (CPCB via data.gov.in, Open-Meteo,
   NASA FIRMS, monthly ERA5) through an idempotent, deduplicated refresh
   pipeline.
2. Trains and serves **per-pollutant, per-horizon ML models** (XGBoost,
   Random Forest, Persistence, plus a lazy-import PyTorch GRU trained and
   evaluated as a candidate ensemble member) for all six criteria pollutants.
3. Provides a **direct PM2.5 forecast engine** with split-conformal prediction
   intervals and SHAP explanations.
4. **Couples weather and chemistry** in a feedback loop — aerosol optical
   depth attenuates solar radiation, suppressing the boundary layer and
   reinforcing stability.
5. **Numerically simulates plume dispersion** on a ~2.2 km NCR grid, with
   stubble-fire point sources, boundary inflow, and wet/dry scavenging.
6. Detects **pollution events**, runs read-only **what-if scenarios**, and
   surfaces everything through a **real-time command dashboard** and a suite of
   REST APIs.

## Key Capabilities

| Capability | How it works | Verify |
|------------|--------------|--------|
| **Real-time command dashboard** | One-screen station picker, PM2.5 forecast with conformal bands, atmospheric conditions, fire intelligence, transport risk, model performance, wind-arrow map | `GET /api/forecast/pm25`, `/` page |
| **Two-way weather–chemistry coupling** | Aerosol AOD → solar attenuation → PBL suppression → stability feedback (`ml/features/coupling.py`, `coupled_loop.py`) | `GET /api/coupling/{station}`, `POST /api/forecast/coupled` |
| **72-hour AQI forecast** | Persistence / Random Forest / XGBoost (GRU trained & evaluated), all **six criteria pollutants** × horizons {1,6,12,24,48,72} | `POST /api/forecast/generate`, `GET /api/forecast/{station}` |
| **Direct PM2.5 forecast engine** | Dedicated multi-horizon XGBoost with split-conformal prediction intervals | `GET /api/forecast/pm25` + model-card + explanation |
| **Pollution event detection** | Statistical surge / relief / sustained high-risk episode detection with atmospheric attribution | `GET /api/events/current`, `docs/events.md` |
| **Scenario (what-if) analysis** | Read-only perturbation engine across wind / PBL / fire / inversion | `POST /api/scenario/analysis`, `docs/scenario_analysis.md` |
| **Cross-model performance** | 4-model evaluation (persistence / RF / XGBoost / GRU) with MAE/RMSE/R² | `GET /api/model/performance`, `/performance` page |
| **Stubble-plume dispersion** | Finite-difference advection–diffusion–deposition solver with FRP fire point sources, wind/PBL/rain forcing | `GET /api/dispersion/forecast`, `ml/features/dispersion_solver.py` |
| **Inversion trapping** | Stability index couples inversions directly to PBL height | `GET /api/inversion/{station}` |
| **NCR-wide spatial mapping** | ~2.2 km gridded AQI surface (IDW + downwind advection) + live numerical field | `GET /api/grid/forecast`, `/spatial` page |
| **All criteria pollutants** | PM2.5, PM10, O₃, NO₂, SO₂, CO | `predict_pollutants`; `TestForecastCompletePollutantSet` |
| **Actionable alerts & explainability** | Alert engine + SHAP feature attribution + natural-language explanations | `GET /api/alerts`, `GET /api/explanation/{station}` |
| **Graded Response Action Plan** | CAQM stage matrix (I-IV) with live NCR assessment from AQI + inversion + fire context | `GET /api/grap/current` |
| **Live data refresh** | Scheduler + one-shot CLI pulls weather / fire / pollution idempotently (tz-aware dedup + DB-unique guards) | `make refresh-data`, `LIVE_REFRESH_ENABLED=true` |
| **Official CPCB ingestion** | data.gov.in-backed idempotent upsert with per-station+timestamp uniqueness | `POST /api/pollution/ingest`, `docs/api.md` |

See [`docs/ps_mapping.md`](docs/ps_mapping.md) for the requirement-by-requirement
mapping to the official problem statement, and
[`docs/SIH_GAP_AUDIT.md`](docs/SIH_GAP_AUDIT.md) / [`docs/SIH_FINAL_COMPLIANCE.md`](docs/SIH_FINAL_COMPLIANCE.md)
for audit and compliance evidence.

## Architecture

```
 Official data sources
 ┌──────────────────────┐   ┌─────────────────┐   ┌──────────────────┐
 │ CPCB · data.gov.in   │   │ Open-Meteo      │   │ NASA FIRMS / ERA5│
 │ (pollution)          │   │ (weather / PBL) │   │ (fire / atmos)   │
 └──────────┬───────────┘   └────────┬────────┘   └────────┬─────────┘
            │                        │                     │
            ▼                        ▼                     ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │              Refresh & Feature Engineering pipeline                  │
 │   idempotent ingest  →  dedup (naive-UTC)  →  AQI engine            │
 │   time-aligned features  →  training dataset                         │
 └──────────────────────────────────────────────────────────────────────┘
            │                                        │
            ▼                                        ▼
 ┌────────────────────────────┐      ┌─────────────────────────────────┐
 │   ML forecasters           │      │   Numerical & physics modules   │
 │   XGBoost / RF / Persist.  │      │   coupling · grid · dispersion  │
 │   GRU (candidate)          │      │   events · scenarios · SHAP     │
 └────────────┬───────────────┘      └────────────────┬────────────────┘
              ▼                                        ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │                      FastAPI backend (backend/app)                  │
 │   api · services · models · SQLAlchemy · Alembic migrations          │
 └───────────────┬──────────────────────────────────────┬──────────────┘
                 ▼                                      ▼
       ┌─────────────────────┐               ┌─────────────────────────┐
       │  React + TS + Vite  │   nginx ◄──►  │ PostgreSQL (prod) /     │
       │  Recharts · Leaflet │   /api proxy  │ SQLite (dev)            │
       └─────────────────────┘               └─────────────────────────┘
```

**Stack**

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic v2 |
| Frontend | React, TypeScript, Vite, Tailwind CSS, Recharts, Leaflet |
| Machine Learning | XGBoost, Scikit-learn, SHAP, NumPy, Pandas |
| Data Stores | PostgreSQL (prod) / SQLite (dev) |
| Orchestration | Docker Compose (backend · frontend · nginx · Postgres) |

## Data & Machine-Learning Pipeline

1. **Acquire** — real data: the official Government of India CPCB feed
   (`backend/app/services/cpcb_service.py`, resource
   [`3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69`](https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69)),
   Open-Meteo weather, NASA FIRMS fires, and Copernicus ERA5 atmosphere — or
   the live refresh service (`backend/app/services/refresh_service.py`).
2. **Build** — `scripts/build_dataset.py` fuses raw readings into time-aligned
   station series with engineered features.
3. **Train** — `python -m ml.training.trainer` fits per-pollutant,
   per-horizon models; `scripts/evaluate_models.py` re-scores them.
   `python -m ml.training.train_pm25` builds the direct PM2.5 conformal engine.
4. **Serve** — FastAPI loads the persisted model artifacts and forecasts on
   demand, feeding AQI, alerts, coupling, grid, dispersion, events and
   scenario endpoints.

### Official CPCB pollution feed (data.gov.in)

The pollution cursor points at the **official** Government dataset "Real time
Air Quality Index from various locations" (`CPCB/DPCC`). Readings are upserted
idempotently into `stations` / `pollution_observations`, enforced by a
`(station_id, timestamp)` unique constraint.

```bash
# 1. Get a free API key: https://api.data.gov.in → register → MyAccount
# 2. Configure it:
DATA_GOV_API_KEY=your_key_here
# 3. Trigger the official CPCB ingestion:
curl -X POST http://localhost:8000/api/pollution/ingest
# 4. Verify:
curl http://localhost:8000/api/pollution/latest
```

Ingestion fetches paginated, per-city records for
`Delhi, Gurugram, Noida, Ghaziabad, Faridabad` (configurable via
`DATA_GOV_NCR_CITIES`), normalizes one row per pollutant per timestamp into
single observations, and upserts them idempotently. Without a key the ingest
endpoint returns `400` (`DATA_GOV_API_KEY is not set`) rather than inventing
data.

## Repository Layout

```
aerocast-ncr/
├── backend/
│   ├── app/                   # FastAPI application
│   │   ├── api/               #   REST route modules
│   │   ├── services/          #   domain logic (refresh, events, coupling…)
│   │   ├── models/            #   SQLAlchemy models (db_models.py)
│   │   ├── main.py            #   app factory + health
│   │   └── database.py        #   engine/session + SQLite apply_migrations
│   └── tests/                 # unit + integration pytest suites
├── ml/
│   ├── features/              # coupling, coupled_loop, dispersion_solver, grid…
│   ├── models/                # xgboost, random_forest, persistence, gru
│   ├── preprocessing/         # weather/pollution/fire/atmosphere processors
│   ├── training/              # trainer, train_pm25, train_gru, evaluate
│   └── evaluation/            # metrics
├── frontend/src/              # React + TS SPA (pages/, components/, hooks/)
├── alembic/versions/          # versioned schema migrations
├── data/                      # processed datasets (gitignored large exports)
├── models/                    # trained artifacts (joblib / JSON model cards)
├── docs/                      # methodology, API, events, scenarios, deploy…
├── scripts/                   # CLI tools (download*, build_dataset, refresh_once)
├── tests/                     # top-level integration tests
├── docker-compose.yml         # full-stack compose
├── Makefile                   # developer command centre
└── pyproject.toml             # packaging + ruff/pytest/cov config
```

## Quick Start — Docker

```bash
# 1. Clone and configure
git clone https://github.com/methila-2056/Air-Pollution-Weather-Coupled-Forecasting-System-Delhi-NCR-Focus-.git
cd aerocast-ncr
cp .env.example .env            # local defaults
cp docs/deploy.env.example deploy.env   # (optional) production overrides

# 2. Build and start the full stack (Postgres + API + frontend + nginx)
docker compose up -d --build

# 3. Boot applies Alembic migrations automatically; seeding + live refresh run in-app

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
`scripts/fetch_all.{sh,ps1}` or `python scripts/build_dataset.py`. For local
development against SQLite, `backend/app/database.py` `apply_migrations()`
keeps the schema in sync with the Alembic chain (including the
`uq_weather_station_ts` unique index).

## API Summary

All endpoints live under `/api` (interactive docs at `/docs`):

| Area | Endpoints |
|------|-----------|
| Station & current AQI | `GET /stations`, `GET /stations/{station}`, `GET /current/{station}` |
| Official CPCB pollution | `POST /pollution/ingest`, `GET /pollution/latest`, `GET /pollution/stations`, `GET /pollution/{station_id}/history` |
| Forecast | `POST /forecast/generate`, `GET /forecast/{station}`, `GET /forecast/ncr`, `GET /forecast/comparison/{station}`, `POST /forecast/coupled` |
| Weather | `GET /weather/{station}`, `GET /weather/{station}/history` |
| Inversion / Fire / Transport | `GET /inversion/{station}`, `GET /fire-activity`, `GET /fire/transport`, `GET /plume-risk`, `GET /fire/hotspots`, `GET /fires/latest`, `GET /transport-risk/current` |
| Spatial & dispersion | `GET /grid/forecast`, `GET /grid/overview`, `GET /dispersion/forecast` |
| Atmosphere & coupling | `GET /atmosphere/current`, `GET /coupling/{station}` |
| PM2.5 forecast engine | `GET /forecast/pm25`, `GET /forecast/pm25/model-card`, `GET /forecast/pm25/explanation` |
| Events & scenarios | `GET /events/current`, `POST /scenario/analysis` |
| Explainability | `GET /explanation/{station}` |
| Alerts & metrics | `GET /alerts`, `GET / POST /model/metrics`, `GET /model/performance` |
| Summary & export | `GET /summary`, `GET /export/forecast.csv`, `GET /health` |
| Graded Response Action Plan | `GET /grap/stages`, `GET /grap/current`, `GET /grap/{station}` |

Request/response schemas are described in [`docs/api.md`](docs/api.md) and are
introspectable at `/docs`.

## Frontend Pages

| Route | Page |
|-------|------|
| `/` | **Command Dashboard** — station picker, PM2.5 forecast + conformal band, atmospheric conditions, fire intelligence & transport risk, SHAP explainability, model performance, wind-arrow station map |
| `/overview` | NCR KPIs & regional summary |
| `/forecast` | 72-hour multi-horizon forecast charts |
| `/map` | Leaflet station map + FIRMS hotspots + plume transport |
| `/spatial` | Gridded/dispersion heatmap with hour scrubber |
| `/atmosphere` | Per-station atmospheric conditions (wind, PBL, ventilation, inversion, trapping) |
| `/explanation` | SHAP feature attribution |
| `/alerts` | Alert centre |
| `/performance` | 4-model (persistence / RF / XGBoost / GRU) evaluation comparison |
| `/stubble` | Stubble plume / stubble-burning activity |

## Testing & Quality Gates

```bash
python -m pytest backend/tests -q            # 422 unit + integration tests
python -m ruff check backend/app backend/tests   # lint (CI-scoped)
cd frontend && npm run build                 # tsc type-check + production build
```

Convenience targets: `make test`, `make test-unit`, `make test-integration`,
`make build`, `make refresh-data`, `make pip-audit` — see the `Makefile`.

## Deployment & CI/CD

- **Compose runbook** — [`docs/deployment.md`](docs/deployment.md) (migration
  flow, live refresh, reverse-proxy/HTTPS, `pgdata` backup/restore,
  first-boot checks).
- **Production env template** — [`docs/deploy.env.example`](docs/deploy.env.example).
- **CI** — `.github/workflows/ci.yml`:
  1. *Backend:* ruff + full pytest suite.
  2. *Migrations:* `alembic upgrade head` against a fresh Postgres 16,
     then integration/API tests against it.
  3. *Frontend:* `tsc` + `vite build`.

## Documentation

| Doc | Contents |
|-----|----------|
| [`docs/methodology.md`](docs/methodology.md) | AQI, features, models, SHAP, coupling, dispersion (§9 surrogate vs. WRF-Chem) |
| [`docs/architecture.md`](docs/architecture.md) | System layers & component diagram |
| [`docs/ps_mapping.md`](docs/ps_mapping.md) | Requirement → implementation mapping |
| [`docs/SIH_FINAL_COMPLIANCE.md`](docs/SIH_FINAL_COMPLIANCE.md) | Final compliance evidence for the problem statement |
| [`docs/SIH_GAP_AUDIT.md`](docs/SIH_GAP_AUDIT.md) | Gap audit vs. a literal WRF-Chem deployment |
| [`docs/deployment.md`](docs/deployment.md) | Deploy runbook & environment reference |
| [`docs/api.md`](docs/api.md) | API reference (incl. PM2.5 engine, events, scenario) |
| [`docs/events.md`](docs/events.md) | Pollution event detection specification |
| [`docs/scenario_analysis.md`](docs/scenario_analysis.md) | What-if scenario engine methodology |
| [`docs/dataset.md`](docs/dataset.md) | Data sources & schema |
| [`docs/weather_data_source.md`](docs/weather_data_source.md) | Weather/ERA5 sourcing details |
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
validation strategy, and [`docs/SIH_GAP_AUDIT.md`](docs/SIH_GAP_AUDIT.md) for
what a literal WRF-Chem deployment would require.

## Contributing & Security

- See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development workflow,
  conventions and how to report issues.
- See [`SECURITY.md`](SECURITY.md) for the responsible-disclosure policy.

## License

MIT — see [`LICENSE`](LICENSE).