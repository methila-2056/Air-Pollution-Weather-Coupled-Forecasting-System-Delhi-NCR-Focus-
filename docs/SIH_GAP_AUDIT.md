# SIH26082 — AeroCast-NCR Gap Audit

> Problem Statement: **Air Pollution–Weather Coupled Forecasting System (Delhi NCR Focus)** — Ministry of Earth Sciences / NCMRWF.
>
> This audit was produced **before** Phase-2 implementation so that existing working code is preserved and only the missing SIH-critical functionality is added.

---

## A. Already implemented (verified, working)

| Capability | Implementation | Evidence |
|-----------|----------------|----------|
| Data acquisition | CPCB pollution (opencity.in CKAN), Open-Meteo weather, NASA FIRMS fire | `scripts/download_{pollution,weather,fire,atmosphere}.py`, `backend/app/services/refresh_service.py` |
| Dataset fusion | weather + pollution + fire → coupled_dataset → featured_dataset | `scripts/build_dataset.py`, `ml/preprocessing/*`, `ml/features/feature_engineering.py` |
| ML training | Persistence / Random Forest / XGBoost, 6 pollutants × 6 horizons, **chronological** train/val/test split | `ml/training/trainer.py:76` |
| Trained artifacts | `.joblib` + `.json` for all pollutant×horizon combos | `models/` |
| Two-way coupling | analytic aerosol→radiation→PBL→stability feedback | `ml/features/coupling.py` |
| Numerical dispersion | 2D finite-difference advection–diffusion–deposition PDE solver (~2.2 km grid) | `ml/features/dispersion_solver.py` |
| Coupled 72h loop | time-stepped ML + feedback correction | `ml/features/coupled_loop.py` |
| Fire impact scoring | fire_count, fire_impact_score, nearest_fire_distance, wind_aligned_fire_count | `ml/features/fire_impact.py` |
| API | 80+ endpoints incl. all PS-required routes | `backend/app/api/*`, `backend/app/main.py` |
| Indian AQI | CPCB breakpoint AQI calculator | `backend/app/services/aqi_calculator.py` |
| SHAP explainability | real `shap.TreeExplainer` when tree model loads + honest fallback | `backend/app/services/explanation_service.py:62` |
| Alerts | computed from actual forecast/weather/fire values (WATCH/ADVISORY/WARNING/SEVERE) | `backend/app/services/alert_service.py` |
| Dashboard | 9 routes: Overview, 72h Forecast, NCR Map, Spatial, Atmosphere, Stubble Plume, AI Explanation, Alerts, Model Performance | `frontend/src/App.tsx` |
| Tests | 200+ unit + integration tests | `backend/tests/*` |

## B. Partially implemented

1. **Weather ↔ pollution coupling** — physics-informed analytic surrogate exists and is wired into the coupled forecast loop, but is **not** tied to vertical meteorology (no lapse-rate inversion, no vertical stability).
2. **72-hour validation / backtesting** — evaluation machinery exists; needs re-run after retraining with new atmospheric features.
3. **Fire plume transport** — heuristic transport-risk + 2D dispersion solver exist, but full transport feature set (transport_time, transport_risk, stubble_impact_score, wind_alignment_%) is incomplete, and fires are **not** rendered on the Leaflet NCR map.
4. **Dashboard** — no standalone Inversion/PBL status panel; inversion/PBL shown as panels inside Atmosphere only.

## C. Missing (SIH-critical gaps)

| # | Requirement | Status | Detail |
|---|-------------|--------|--------|
| C1 | **Vertical (pressure-level) atmospheric data** | ❌ | `data/atmosphere/` is empty. ERA5 downloader only requests *single-level* fields. No 1000/925/850/700 hPa temperature/geopotential. No `metpy`/`xarray`/`cfgrib`. |
| C2 | **Inversion from vertical temperature (lapse rate)** | ❌ | Inversion is inferred purely from a PBL-height threshold proxy, not from a vertical temperature profile. |
| C3 | **PBL category / dispersion condition** | ⚠️ | `pbl_height` exists but only as a raw value; no `low_pbl_flag`, `pbl_category`, `dispersion_condition`. |
| C4 | **Full fire-transport feature set** | ⚠️ | Missing `wind_alignment_%`, `transport_time`, `transport_risk`, `stubble_impact_score`. |
| C5 | **WRF-Chem or a coupled CTM** | ❌ | Not installed / configured / executed anywhere. Referenced 24× only as a *comparison point*. Documented as a pure-Python surrogate. |
| C6 | **GRU / LSTM model** | ✅ | Custom NumPy GRU trained: 2-layer, hidden=64, seq_len=48; honestly underperforms XGBoost at all horizons (h-1 R²: GRU 0.336 vs RF/XGB 0.879); retained as a candidate ensemble member while the live API serves the higher-accuracy XGBoost direct models. See `models/pm25/evaluation.json`. |
| C7 | **FIRMS fire + wind + transport layers on the Leaflet map** | ✅ | Leaflet NCR map renders FIRMS hotspots (FRP-sized/colored circles) + stations; StubblePlume summary card shows headline risk, wind-aligned %, smoke arrival time. Transport risk fetched from `/api/transport-risk/current`. |

## D. Incorrect or scientifically weak

1. **Inversion strength from PBL threshold only** (`ml/features/inversion.py:1-14`, `backend/app/api/inversion.py:10-20`) — does not use vertical temperature gradients; cannot claim exact inversion strength without vertical data.
2. **`docs/dataset.md:22`** claims "temperature profile, wind profile, inversion indicators" under the Atmosphere source — these data do **not** exist in the repository (aspirational documentation).
3. **`ml/preprocessing/atmosphere_processor.py`** is labeled "atmospheric" but only handles PBL height.
4. The API duplicates the inversion logic (`classify_inversion`) instead of reusing the `ml` module, causing drift between training-time and API-time inversion features.

## E. Recommended implementation (Phase-2 scope)

1. **Vertical atmospheric ingestion** — add a reusable processor under `backend/app/services/atmospheric/` (and mirror it for the ML pipeline under `ml/`) that ingests pressure-level temperature + geopotential from **Open-Meteo's pressure-level API** (free, no key) at 1000/925/850/700 hPa, with **graceful offline fallback** (PBL-threshold proxy) when network data is unavailable. Document ERA5 as the production-scale option.
2. **Lapse-rate inversion** — rewrite inversion detection to compute vertical temperature gradient: detect `T ↑ with height` over the layer → `inversion_detected`, `inversion_strength`, `inversion_base`, `inversion_top`, `inversion_category`, `inversion_duration`. Keep PBL-threshold as a documented fallback.
3. **PBL classification** — add `low_pbl_flag`, `pbl_category`, `dispersion_condition`.
4. **Fire transport** — extend `fire_impact.py` with `wind_alignment_%`, `transport_time`, `transport_risk`, `stubble_impact_score`. Use "estimated transport risk" wording.
5. **Wire features** into `feature_engineering.py` and `forecast_service.build_features_from_db`, and make `backend/app/api/inversion.py` reuse `ml/features/inversion.py`.
6. **GRU/LSTM** — optional; heavy deep-learning dependency. Only add if the existing 3-model ensemble is deemed insufficient (see recommendation C6: keep it as an optional module).
7. **Frontend** — add Inversion + PBL panels and a FIRMS/wind/transport overlay on the NCR map.
8. **Tests** — vertical-data processing, lapse-rate inversion (normal / weak / strong / missing data), PBL classification, fire-transport features.
9. **Documentation** — this audit + `docs/SIH_FINAL_COMPLIANCE.md`.

## F. Files that will be modified / created

**Created**
- `docs/SIH_GAP_AUDIT.md` (this file)
- `docs/SIH_FINAL_COMPLIANCE.md`
- `backend/app/services/atmospheric/__init__.py`
- `backend/app/services/atmospheric/vertical_atmosphere.py`
- `backend/app/services/atmospheric/inversion.py`
- `ml/features/vertical_atmosphere.py` (shared ML-side logic)
- `scripts/download_atmosphere_pressure_levels.py` (optional; Open-Meteo pressure-level pull)
- `tests/` for new modules

**Modified**
- `ml/features/inversion.py` — add lapse-rate detection (backward compatible)
- `ml/features/fire_impact.py` — add transport features
- `ml/features/feature_engineering.py` — add new features
- `ml/features/PBL classification` (new small module or in inversion.py)
- `backend/app/api/inversion.py` — reuse ml module + add vertical/lapse-rate fields
- `backend/app/services/forecast_service.py` — include new features
- `backend/app/schemas/schemas.py` — extend inversion response (if adding fields)
- `frontend/src/` — inversion/PBL panel + map overlay

## G. Files that must NOT be modified unnecessarily

- `ml/features/dispersion_solver.py` (numerical core — working)
- `ml/features/coupling.py` (analytic coupling — working)
- `ml/preprocessing/*` (data cleaning pipeline)
- `backend/app/database.py` & `backend/app/models/db_models.py` (schema — avoid destructive changes; use additive/alembic if required)
- `aerocast_ncr.db` (do not drop/recreate)
- `backend/app/api/{forecast,stations,alerts,explanation,weather,grid}.py` (existing working endpoints)
- Trained `.joblib` models
- Frontend routes already present

---

## Verification of key SIH concerns

| Concern | Verified status |
|---------|-----------------|
| WRF-Chem integrated? | **No** — not installed/configured/executed; only a documented pure-Python surrogate. (Matches "do not fake WRF-Chem results" requirement.) |
| Vertical atmospheric data exists? | **No** — `data/atmosphere/` empty; only single-level PBL. |
| PBL height exists? | **Yes (single value)** — from Open-Meteo archive, ~16.6% missing, not independently validated. |
| Inversion strength exists? | **Partial** — PBL-threshold proxy, not vertical lapse-rate analysis. |
| Plume transport exists? | **Partial** — heuristic risk + 2D dispersion solver; transport feature set incomplete, map lacks fire overlay. |
