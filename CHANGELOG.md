# Changelog

All notable changes to **AeroCast-NCR** are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/) and semantic versioning.

## [1.8.6] - 2026-09

### Fixed (developer tooling)
- **`make clean-data` no longer fails.** The target referenced a missing
  `scripts/clean_generated.py`; the script now exists and is documented in
  `scripts/README.md`. It removes only regenerable artifacts (Python/tooling
  caches, runtime logs, local `*.db`, `frontend/dist`, engineered datasets and
  ML byproducts), never source CSVs or committed model weights. Dry-run is the
  default; pass `--exec` to apply. Virtualenv-internal caches are excluded.
- **Pytest coverage artifacts are now gitignored** (`.coverage`, `.coverage.*`),
  keeping `git status` clean after `pytest --cov` runs.

## [1.8.5] - 2026-09

### Fixed (demo panels on warm databases + honest status badge)
- **Demo panels no longer stay empty on a database that already has live
  observations.** The demo hydration previously skipped *everything* when the
  last 24 h already contained pollution+weather, so a warm DB never gained the
  seeded alerts, model metrics, fire archive or persisted forecasts — stations
  showed "No forecast stored", "Forecast engine not available" and missing
  metrics. Hydration now runs an idempotent auxiliary pass on **every** boot
  (`_ensure_auxiliary_demo_data`) that seeds metrics/alerts/24 h fires and
  persists vanilla 72 h forecast rows for every station missing them.
- **Status badge stops crying "API offline" through a cold start.** A single
  failed `GET /summary` (the first request on a waking Render instance) no
  longer flips the header pill to red; it only reports offline after two
  consecutive exhausted loads (~>2 min), by which time the instance is truly
  unresponsive.

## [1.8.4] - 2026-09

### Fixed (cold-start resilience for live demo)
- **Every panel now self-heals through a Render cold start.** The axios client
  retries idempotent `GET`s up to 4 times (8 s apart) on transient gateway
  502/503/504 or network-timeout failures, so the first page loaded right after
  the free-tier backend wakes no longer strands panels on "API offline",
  "Loading…", "No forecast stored" or "No active hotspots".
- **Keepalive workflow** (`.github/workflows/keepalive.yml`) pings the Render
  `/health` endpoint every 5 min (and on demand via `workflow_dispatch`), so
  the backend never idles to sleep mid-demo.

## [1.8.3] - 2026-09

### Fixed (cold-start session + deploy wiring)
- **Boot-time `getMe()` no longer logs the analyst out while the Render
  free-tier backend is still waking up from idle.** A transient 502/503/504 or
  network timeout now keeps the stored session (user + token) so panels can
  retry instead of kicking the analyst back to sign-in mid-demo — matching the
  login page's existing cold-start retry from 1.8.1.
- **`render.yaml` `FRONTEND_URL` corrected** to the live Vercel deployment
  (`air-pollution-weather-coupled-forecasting-system-methila.vercel.app`) so
  `GET /` on the Render backend 307-redirects to the real frontend.
- **`frontend/.gitignore` added** so Vercel build artifacts (`.vercel`,
  `.env*`) are never committed.

## [1.8.2] - 2026-09

### Fixed (deployed frontend UX)
- **`GET /` on the deployed backend no longer answers `{"detail": "Not Found"}`**
  �?" a browser hit on `https://air-pollution-weather-coupled.onrender.com` now
  307-redirects to the Vercel frontend (`FRONTEND_URL`, already set in
  `render.yaml` and `.env`). Local dev with no `FRONTEND_URL` gets a small
  landing JSON pointing at `/docs` and `/health` instead of a bare 404.
- New `backend/tests/unit/test_root.py` (2 tests) locking both behaviours.

## [1.8.1] - 2026-09

### Fixed (deployed demo stability)
- **OOM crash-loop on Render free-tier** — the startup demo self-hydration
  read the ~131k-row coupled dataset and ~383k-row FIRMS archive fully into
  pandas on a 512 MB instance, OOM-killing the container every boot (the
  intermittent **502** that made demo sign-in fail). The loaders
  (`backend/scripts/load_data.py`) now **stream CSV in chunks (25k/50k rows)
  and insert in small resilient batches** (2k rows each) with `gc.collect()`
  between chunks — a Neon-free-tier statement/connection hiccup skips one batch
  instead of aborting the whole hydration; the hydration task
  (`demo_hydration.py`) is deferred by a 45 s boot-grace so it never competes
  with Render's health-check window.
- **Demo sign-in resilient to cold starts** — the login page auto-retries once
  (~12 s) after a transient 502/503/504 or network timeout (Render free back-
  ends sleep after ~15 min idle), showing "server is waking up …" instead of an
  immediate "Demo sign-in failed".
- New `backend/tests/unit/test_load_data.py` (6 tests) locking chunked insert,
  idempotency and missing-file behaviour.

## [1.8.0] - 2026-09

### Added
- **Gated IMD official weather API adapter (WS-3, R9).**
  - `backend/app/services/imd_weather.py`: fetches genuine 7-day city forecasts
    from `api.imd.gov.in/api/v1/cityforecast` (station `42182`
    Delhi/Safdarjung, the NCR anchor). The gateway authenticates via key/IP
    whitelist and returns **HTTP 401 otherwise** — verified live with urllib in
    this environment; `imd_reasons()`/`IMDApiUnavailable` report exactly that,
    and nothing is ever fabricated.
  - `backend/app/api/imd.py` — `GET /api/imd/forecast` returns `{available,
    station, days:[7d max/min/condition], reasons}` (registered in `main.py`);
    schemas `ImdForecastDay`/`ImdForecastResponse`; config `imd_api_key`,
    `imd_station_id`, `imd_api_base`.
  - `scripts/fetch_imd_weather.py` — offline CLI writing
    `data/imd/imd_forecast.csv` (empty placeholder + honest reason on failure);
    `scripts/build_dataset.py` gains `load_imd()` and merges `imd_*` columns
    into the coupled dataset when real rows exist, warning + Open-Meteo
    fallback otherwise.
  - New `docs/imd.md`; `SIH_FINAL_COMPLIANCE.md` R9 note; 13 new unit tests
    (`backend/tests/unit/test_imd_weather.py`: 401/no-key reasons, real-shape
    parsing, malformed/non-JSON/HTTP-error rejection, router response,
    dataset glue).

## [1.7.0] - 2026-09

### Added
- **Real ERA5 reanalysis ingestion (WS-2, R9 subset).**
  - New gated reader `ml/features/era5_surface.py`: samples genuine
    Copernicus-CDS `reanalysis-era5-single-levels` NetCDF grids (`blh`, `t2m`,
    `sp`) at the 17 curated NCR stations (nearest grid cell), converts units
    (K→°C, Pa→hPa), and returns per-station, per-hour rows
    (`time, station, era5_temperature, era5_surface_pressure, era5_blh`).
    Reads NetCDF3-classic via `scipy.io.netcdf_file` with **zero extra
    dependencies** (prefers netCDF4/xarray if installed); handles the CDS
    `expver` split; reports honest `era5_reasons()` and returns an empty frame
    when no real file exists — nothing is ever fabricated.
  - `scripts/download_atmosphere.py` rewritten: proper CDS request (one NetCDF
    per archive year, idempotent, `--no-download`/`--force`), then extracts the
    station CSV through the shared reader; unreachable/unauthorised CDS writes
    a clearly-empty placeholder so `build_dataset.py` keeps using Open-Meteo.
  - `scripts/build_dataset.py::load_atmosphere` now consumes the real NetCDF
    samples via the shared reader (previously the NetCDF path was
    non-functional — downloaded `blh/t2m/sp` grids never became `era5_*`
    columns), with an honest "ERA5 atmosphere unavailable" warning + reason.
  - New `docs/era5.md`; `SIH_FINAL_COMPLIANCE.md` R9 note + 8 new unit tests
    (`backend/tests/unit/test_era5_surface.py`: gating, multi-year glob,
    nearest-cell sampling/units, descending latitude, expver, CSV glue).

**528 tests pass** (was 520). No DB migration, no frontend change.

## [1.6.0] - 2026-09

### Added
- **Real chemical-transport engine layer — NOAA HYSPLIT + WRF-Chem (WS-4, R6).**
  - New `ml/ctm/` package: `ctm_interface.py` (`CtmResult`, `CtmUnavailable`,
    `register`, `run_best_engine` with deterministic WRFChem→HYSPLIT priority),
    `regrid.py` (IDW gridding for sparse plumes).
  - `hysplit_adapter.py`: renders a standard HYSPLIT CONTROL file (line layout
    mirrors NOAA ARL `utilhysplit`), runs the real `exec/hycs_std(.exe)`, and
    parses the binary `cdump` using ARL's own record layout — validated against
    the real `cdump.bin` archived in `noaa-oar-arl/utilhysplit` — then regrids
    the plume onto the NCR domain. Strictly gated on executable + genuine ARL
    met files; never simulates; `CtmUnavailable` otherwise.
  - `wrfchem_adapter.py`: consumes genuine external `wrfout_d01_*.nc` output
    (xarray/netCDF4), units taken verbatim from the file.
  - `scripts/download_hysplit_gdas.py`: idempotent GDAS1 ARL archive fetcher
    from the verified ready.noaa.gov file scheme (`gdas1.<mon><yy>.w<k>`).
  - `dispersion_service.py` now tries genuine engines first and, on success,
    composites the engine plume *pattern* 50/50 with the coupled forecast
    surface (`mode`, `composite`, and `ctm` blocks disclose engine/units; the
    analytic surrogate stays the documented fallback when no engine is
    runnable). `mode="numerical_advection_diffusion"` fallback unchanged.
  - New `docs/hysplit.md` and `docs/wrfchem_adapter.md`; `SIH_FINAL_COMPLIANCE.md`
    R6 now ✅ (engine-gated). 14 new unit tests (`test_ctm_engines.py`) covering
    CONTROL layout, cdump round-trip + malformed rejection, surface regrid,
    gating, registry order, and composite logic.

## [1.5.0] - 2026-09

### Added
- **Pollution coverage for all 17 curated NCR stations (WS-1).**
  - New careful aliases map every data.gov.in / CPSB station name to the 17
    canonical monitors (adds Lodhi Road, Sirifort, Shadipur, Okhla Phase-2,
    Ashok Vihar, Mundka, Jahangirpuri, Aya Nagar, Vivek Vihar, Teri Gram /
    Vikas Sadan, Noida Sector-62, Faridabad/Sector 11).
  - Provenance tagging: every `pollution_observations` row now carries
    `data_source` (`data_gov_in`, `opencity_ckan`, `cpcb_dataset`); additive
    schema change only (alembic `d3e5f7a4b8c2` + SQLite `apply_migrations`).
  - New `scripts/backfill_pollution.py`: keyless, idempotent historical AQI
    backfill from the community CPCB hourly-AQI dataset (Vonter/india-cpcb-aqi,
    ODbL) for all sparse/empty stations; network-gated, offline-safe, honest
    (hourly AQI only, never fabricated).
  - Sparse-station resilience in forecasting: when a station has fewer than 24
    local readings it falls back to a regional composited signal from the five
    core stations (Anand Vihar, RK Puram, ITO, Dwarka, Punjabi Bagh) so the
    72-hour model is never run on empty history.
  - New `GET /api/pollution/coverage` endpoint reporting per-station reading
    counts, first/last timestamps, source breakdown, and sufficiency status
    (adequate / limited / insufficient_history / stale / no_data); model
    responses for `/api/forecast/generate` and `/api/forecast/coupled` now
    surface `pooled_features`, `local_readings`, and `history_days`.
  - Unit + API tests for aliases, coverage endpoint, and pooled fallback (506
    passing).

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