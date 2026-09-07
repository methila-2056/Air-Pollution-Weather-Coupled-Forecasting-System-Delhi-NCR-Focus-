# Changelog

All notable changes to **AeroCast-NCR** are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/) and semantic versioning.

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