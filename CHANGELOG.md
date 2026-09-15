# Changelog

All notable changes to **AeroCast-NCR** are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/) and semantic versioning.

## [1.4.0] - 2026-09

### Added
- **Institutional light-theme UI redesign (full frontend overhaul).** The dark
  developer dashboard is replaced with a credible government/NGO atmospheric-
  services portal: deep institutional blue (`inst` palette) + white/light
  surfaces, national header with SIH26082 badge, secondary section navigation,
  breadcrumb-ready pages, footer disclaimer, `Inter`/Noto Sans font stack,
  WCAG-aware focus rings, and `prefers-reduced-motion` support.
  - New reusable components: `PageHeader`, `KpiCard`, `LoadingState` (skeleton),
    `ErrorState` (retry), `EmptyState`, `AQIBadge`.
  - Light CARTO basemap + light-themed Leaflet overrides; canonical CPCB AQI
    colour table centralised in `frontend/src/lib/aqi.ts`.
  - Legacy science pages (Overview, Spatial Forecast, AI Explanation, Data
    Tools) preserved and reachable under their original routes.
- **Portal authentication layer (additive, zero new dependencies).**
  - Backend: `hashlib.scrypt` password hashing + hand-rolled HS256 JWT (stdlib
    only) in `backend/app/security.py`; new `users` table (alembic
    `a1b2c3d4e5f6` + SQLite `apply_migrations`); idempotent demo-user seeding at
    startup; endpoints `POST /api/auth/login`, `GET /api/auth/me`,
    `POST /api/auth/logout`, `GET /api/auth/demo`. All data APIs remain public.
  - Frontend: `AuthContext`, `ProtectedRoute` guard, `/login` page with
    password visibility toggle + demo autofill, `/profile` page, user menu with
    avatar initials and sign-out. Credentials fully env-driven (`SECRET_KEY`,
    `DEMO_USER_*`).

### Changed
- `docs/UI_REDESIGN_AUDIT.md` — frontend/UX + authentication audit and plan.

## [1.3.0] - 2026-09

### Added
- **Expanded monitoring network: 5 → 17 stations.** Added Delhi sites (Lodhi
  Road, Sirifort, Shadipur, Okhla Phase-2, Ashok Vihar, Mundka, Jahangirpuri,
  Aya Nagar, Vivek Vihar), Gurugram (Teri Gram), Noida (Sector-62) and
  Faridabad — wired across `DEFAULT_STATIONS`, the live refresh service
  (`refresh_service.STATIONS`), `scripts/download_weather.py` and
  `backend/scripts/load_data.py`.
- **Historic weather for all new stations** — full Open-Meteo archive history
  (2023-01-01 → present) downloaded and loaded into the running database.
- **`scripts/seed_stations.py`** — idempotent seeding of stations + historic
  weather CSVs (`data/weather/*_weather.csv`), skipping already-loaded
  timestamps.
- **CSV import / export ("Data Tools").** New `GET /api/export/weather.csv` and
  `GET /api/export/pollution.csv` (alongside the existing
  `GET /api/export/forecast.csv`) download persisted observations per station,
  and new `POST /api/import/weather` / `POST /api/import/pollution` accept the
  same formats back as `text/csv`, so series round-trip cleanly. Imports are
  idempotent (keyed on `(station, timestamp)`, existing rows updated only when
  they changed), timestamps are stored per the app-wide IST-naive convention,
  blank `aqi` is recomputed from the six criteria pollutants, and unknown (non
  curated) stations are skipped and reported. New `frontend DataTools` page
  (`/data`) provides export buttons, CSV upload, templates and import summaries.

### Changed
- The `/api/forecast/ncr` aggregate, station list, grid overview, summary and
  data-quality reports now span all 17 stations; tests assert counts against
  `DEFAULT_STATIONS` instead of hard-coded five.
- **Live CPCB pollution now covers all 17 stations.** The data.gov.in ingestion
  maps the platform's monitor display names onto the curated canonical stations
  (`_STATION_ALIASES`: e.g. `IMD Lodhi Road` -> `Lodhi Road`, `R K Puram` ->
  `RK Puram`, `Dwarka-Sector 8` -> `Dwarka`, `Sector - 62` ->
  `Noida Sector-62`, `Sector 11` -> `Faridabad`). Ingestion no longer
  auto-creates ad-hoc stations — unknown monitors are skipped and counted as
  `station_skipped`, keeping the network exactly at the curated 17.
- `DATA_GOV_API_KEY` is configured with the shared public demo key; for stable
  scheduled ingestion register a free personal key at data.gov.in and replace
  it in `.env` (the demo key is rate-limited and intermittently returns 429s).

## [1.2.0] - 2026-09

### Added
- **Graded Response Action Plan (GRAP)** — CAQM stage matrix (Oct-2024
  revision: Stage I ≥201, Stage II ≥301, Stage III ≥401, Stage IV >450) as a
  pure service (`grap_service.py`), three API endpoints, and a dashboard panel.
  - `GET /api/grap/stages` — full referential matrix (incl. not-invoked).
  - `GET /api/grap/current` — live NCR assessment from persisted 24-hour
    average AQI, shallowest-PBL inversion proxy and FIRMS mean FRP, with
    rationale and an actionable measures list.
  - `GET /api/grap/{station}` — per-station assessment.
- Dashboard section 4 "Graded Response Action Plan" with stage badge, advisory,
  measures and why-this-stage rationale (`GrapPanel`).

## [1.1.1] - 2026-09

### Added
- **Command dashboard** — new `/` route (`frontend/src/pages/Dashboard.tsx`)
  aggregating the direct PM2.5 forecast with conformal bands, atmospheric
  conditions, regional fire intelligence + transport risk, SHAP
  explainability, cross-model performance and a wind-arrow station map.
- **Client + types wiring** — `getPm25Forecast`, `getAtmosphereCurrent`,
  `getTransportRisk` in `frontend/src/api/client.ts` with full response
  typings; `StationMap` renders flow-direction wind arrows.

### Fixed
- **Weather-ingestion dedup** — the pre-insert lookup compared tz-aware
  PostgreSQL datetimes against naive-UTC source timestamps (always unequal),
  so duplicate weather rows accumulated. Existing timestamps are now normalized
  to naive-UTC before the set-membership check.
- **Weather uniqueness enforced** — Alembic migration
  `f6a2e7b3c8d9_weather_unique_ts` adds `(station_id, timestamp)` on
  `weather_observations` after deduplicating pre-existing rows; the same dedup +
  unique index is applied to SQLite dev DBs via `apply_migrations()`.
- **Junk pollution rows** — the CKAN feed occasionally returns rows with a
  valid timestamp but every sensor value NULL; these are now skipped instead of
  inserting empty observations.
- **Pollution-events 500** — the forecaster serialises timestamps as ISO-8601
  strings, which broke run-gap arithmetic (`str - str`) in the event rules;
  `_parse_ts` normalises them to naive-UTC datetimes (regression tests added).

## [1.1.0] - 2026-09

### Added
- **GRU deep-learning model** — custom NumPy 2-layer GRU (`ml/training/train_gru.py`,
  `ml/models/gru_model.py`) trained at all 6 horizons for all 6 pollutants
  (no PyTorch/TensorFlow dependency). Honestly underperforms XGBoost
  (h-1 R² 0.336 vs 0.879); retained as a candidate ensemble member while the
  live PM2.5 endpoint serves the higher-accuracy XGBoost direct models.
- **Direct PM2.5 forecast engine** — dedicated multi-horizon XGBoost with
  conformal prediction intervals, model-card and feature explanation
  endpoints (`GET /api/forecast/pm25`, `/api/forecast/pm25/model-card`,
  `/api/forecast/pm25/explanation`).
- **4-model evaluation** — persistence / RF / XGBoost / GRU across all
  horizons written to `models/pm25/evaluation.json` + `.csv`.
- **Pollution event detection** — surge / relief / sustained high-risk
  episodes with confidence and atmospheric contributors
  (`GET /api/events/current`, `docs/events.md`).
- **Scenario (what-if) analysis engine** — read-only perturbation of wind /
  PBL / fire / inversion propagated through the coupled model
  (`POST /api/scenario/analysis`, `docs/scenario_analysis.md`).
- **Cross-model performance dashboard** — `GET /api/model/performance` and
  a frontend page comparing MAE/RMSE/R² across models and horizons.
- **Fire hotspots endpoint** — `GET /api/fire/hotspots` feeding the Leaflet
  map overlay with FRP-sized markers, plus `GET /api/transport-risk/current`.

### Changed
- `docs/api.md` covers all new endpoints (PM2.5 engine, events, scenario,
  model performance, transport risk, atmosphere/current, fire hotspots).

### Fixed
- (none)

## [1.0.0] - 2026-09

### Added
- Numerical dispersion transport core (`ml/features/dispersion_solver.py`) —
  finite-difference advection–diffusion–deposition–emission surrogate of the
  WRF-Chem dynamical core for the NCR grid, with lateral inflow boundary
  conditions, stubble-fire FRP point sources, urban emission, and
  non-negativity-preserving explicit numerics.
- API endpoint `GET /api/dispersion/forecast` (72h hourly AQI frames,
  per-frame two-way coupling diagnostics) and `backend/app/services/dispersion_service.py`.
- Frontend `/spatial` toggle between the statistical IDW grid and the live
  numerical dispersion field, with fire-plume overlay and hour scrubber.
- Full containerization: backend and frontend Dockerfiles, nginx `/api`
  reverse proxy, build-context exclusions.
- GitHub Actions CI (backend pytest + frontend build) and Dependabot config.
- MIT license, contributor guide, changelog, and expanded documentation
  (API reference, PS-to-implementation mapping, reproducibility, deployment).
- Unit-test layer covering the dispersion solver, coupling, grid service,
  fire impact, feature engineering and inversion modules.

### Changed
- Online two-way coupled forecast loop (`ml/features/coupled_loop.py`) with a
  time-stepped feedback path; all six criteria pollutants (PM2.5, PM10, O3,
  NO2, SO2, CO) across horizons {1, 6, 12, 24, 48, 72}.
- NCR spatial grid (`backend/app/services/grid_service.py`) at ~2.2 km with
  wind-advected IDW interpolation.
- `data/processed/featured_dataset.csv` (120 MB, over GitHub's 100 MB push
  limit) committed as two verbatim halves — see `data/processed/SPLIT_NOTE.txt`.

### Removed
- (none)

### Fixed
- Numerical stability of the dispersion core: corrected upwind flux indexing,
  CFL-safe adaptive time step, per-second wet-scavenging rates, and domain
  re-population via lateral inflow boundary conditions.

## [0.3.0] - 2026-07
### Added
- Two-way weather–chemistry coupling module (`ml/features/coupling.py`) and
  `/api/coupling/{station}` diagnostics.

## [0.2.0] - 2026-06
### Added
- Live refresh scheduler, packaging via `pyproject.toml`, frontend robustness.

## [0.1.0] - 2026-05
### Added
- Initial XGBoost/random-forest/persistence forecasters, AQI engine,
  explainability (SHAP), alerts, plume-risk, inversion detection.