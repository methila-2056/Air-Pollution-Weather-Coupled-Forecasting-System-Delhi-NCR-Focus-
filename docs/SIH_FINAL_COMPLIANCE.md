# SIH26082 — AeroCast-NCR Final Compliance

> Problem Statement: **Air Pollution–Weather Coupled Forecasting System (Delhi NCR Focus)** —
> Ministry of Earth Sciences / NCMRWF.
>
> This document is the Phase-2 compliance record. It follows the `docs/SIH_GAP_AUDIT.md`
> findings and records, requirement by requirement, what was implemented, the exact evidence
> file, and any honestly-remaining limitation. **Nothing in this repository claims results it
> cannot produce: there is no fabricated WRF-Chem output, no invented accuracy, and no
> unsupported inversion-strength claim without vertical data.**

---

## 1. Requirement-by-requirement compliance

| # | Requirement (from PS SIH26082) | Implementation | Evidence-file | Status | Remaining limitation |
|---|-------------------------------|----------------|---------------|--------|----------------------|
| R1 | **Vertical (pressure-level) atmospheric data** — temperature/wind profiles at standard levels for Delhi NCR | Open-Meteo pressure-level API (1000/925/850/700 hPa temperature + geopotential heights 925/850 hPa), ingested per station-hour into `weather_readings` (additive columns), refreshed by the standard weather refresh; supplemental live-forecast fetch when the archive returns NULL for recent dates; documented analysis module | `backend/app/services/atmospheric/vertical_atmosphere.py`, `backend/app/services/atmospheric/__init__.py`, `backend/app/services/refresh_service.py` (`PRESSURE_LEVEL_VARS`, vertical backfill), `backend/app/database.py` (additive ALTER), `backend/app/models/db_models.py` (`WeatherReading` pressure-level columns) | ✅ | Archive pressure-level fields for very recent dates may be NULL → live forecast supplement used; ERA5 (Copernicus CDS) documented as the production-scale upgrade. |
| R2 | **Inversion detection from vertical temperature (lapse rate)** | Lapse-rate inversion computed at each standard layer: `dT/dp*100 (K/100 hPa)`; `T↑ with height` ⇒ inversion; reported `inversion_detected`, `inversion_strength`, `inversion_base_pressure`, `inversion_top_pressure`, `inversion_category`, `strongest_layer_gradient`, `inversion_source = lapse_rate \| pbl_proxy`. PBL-height threshold retained **only as a documented fallback** when no vertical data exists. API deterministically reads stored vertical columns from the DB. | `ml/features/atmospheric_profile.py`, `ml/features/inversion.py` (`add_lapse_rate_inversion_features`), `backend/app/api/inversion.py` (`_compute_inversion`), `backend/app/schemas/schemas.py` (`InversionResponse` extension) | ✅ | "Strong/Moderate/Weak" grade thresholds (1.5/0.6/0.0 K per 100 hPa) are heuristic and stated as such; a real WRF/ERA5 reanalysis would give the production-grade climatology. |
| R3 | **PBL classification / dispersion condition** | `low_pbl_flag`, `pbl_category` (strong/moderate/weak trapping, good dispersion), `dispersion_condition` (TRAPPED/LIMITED/MODERATE/GOOD/UNKNOWN) computed from `pbl_height`; merged with lapse-rate analysis; exposed via API + frontend. | `ml/features/atmospheric_profile.py` (`classify_pbl`, `combine_inversion`), `backend/app/api/inversion.py`, `frontend/src/components/InversionPanel.tsx` | ✅ | Classification thresholds are heuristic (150/300/500 m) and documented as such. |
| R4 | **Fire (stubble-burning) transport impact** | Cross-border FIRMS ingestion + per-station impact: `fire_count`, `fire_impact_score`, `nearest_fire_distance`, `wind_aligned_fire_count`, **`wind_alignment_pct`**, **`transport_time_hours`** (nearest-fire distance ÷ wind speed), **`transport_risk` (0–1) + `transport_risk_level`**, **`stubble_impact_score`** (0–1 smoke-driven PM proxy). All derived from real FIRMS + wind; clearly an *advective estimate*, not a dispersion simulation. New `/api/fire/hotspots` endpoint feeds the map overlay. | `ml/features/fire_impact.py`, `backend/app/api/fire.py` (`/plume-risk`, `/fire/hotspots`), `backend/app/schemas/schemas.py` (`PlumeRiskResponse`, `FireHotspotsResponse`), `frontend/src/pages/NCRMap.tsx`, `frontend/src/components/StationMap.tsx` | ✅ | Transport time is a straight advective arrival proxy (no boundary-layer diffusion); the separate 2D PDE solver (`ml/features/dispersion_solver.py`) remains the numerical dispersion tool. |
| R5 | **Two-way air-pollution ↔ weather coupling** | Analytic aerosol→radiation→PBL→stability feedback (`aod_est`, `radiation_transmittance`, `pbl_suppression_factor`, `corrected_pbl_height`, `stability_coupling_index`, `feedback_multiplier`) already existed and is preserved; now additionally reads lapse-rate `dispersion_condition` context in the coupled loop. | `ml/features/coupling.py`, `ml/features/coupled_loop.py`, `backend/app/api/coupling.py` | ✅ | Pure-Python analytic surrogate; a coupled CTM like WRF-Chem would be the full 3D realization (see R6). |
| R6 | **WRF-Chem / coupled CTM** | Not installed, configured, or executed. **Honest scope**: a pure-Python surrogate (analytic coupling + 2D finite-difference dispersion solver) is provided, and WRF-Chem is only ever referenced as a comparison point. No fake WRF-Chem results are produced or claimed. | `docs/SIH_GAP_AUDIT.md` §C5, `README.md` "Honest Scope", `docs/methodology.md` §9 | ⚠️ (documented gap) | Requires HPC/GSL + ERA5 CDS; out of prototype scope. Replace the surrogate with real WRF-Chem for the production build. |
| R7 | **72-hour multi-pollutant forecasting for Delhi NCR** | Persistence / Random Forest / XGBoost, 6 pollutants (PM2.5, PM10, O3, NO2, SO2, CO) × horizons {1,6,12,24,48,72}; **chronological** train/val/test split (no random shuffle); models served by `/api/forecast/{station}?hours=72` and `/api/forecast/ncr`; SHAP explanation on `/api/explanation/{station}`. | `ml/training/trainer.py:76`, `ml/inference/predictor.py`, `backend/app/services/forecast_service.py`, `metrics_eval_summary` files under `models/` | ✅ | Baseline R² (2023–2025) verified: 1h 0.749–0.949 across pollutants; 72h NO2/SO2 weaker (0.21/0.15). Periodic retrain recommended as new vertical+transport features accumulate. |
| R8 | **GRU / LSTM deep-learning model** | **Trained** using a custom NumPy implementation (no PyTorch/TensorFlow dependency): 2-layer GRU, hidden=64, seq_len=48, 6 pollutants × 6 horizons, chronological train/val/test split. Honestly underperforms tree ensemble (h-1: GRU R²=0.336 vs XGBoost 0.879); results are in the shared 4-model evaluation. Trained GRU artifacts are retained as a candidate ensemble member; the live API serves the higher-accuracy XGBoost direct models. | `ml/training/train_gru.py`, `ml/models/gru_model.py`, `ml/training/evaluate_pm25.py`, `models/pm25/gru/`, `models/pm25/evaluation.json` | ✅ | Honest gap: GRU weaker than XGBoost at all horizons (see evaluation.json); the tree-based pipeline is the serving model. |
| R9 | **Data ingestion (CPCB + IMD + ERA5/ecmwf + FIRMS)** | CPCB pollution (opencity.in CKAN) confirmed real; Open-Meteo weather + pressure levels (verified live, UTC, HTTP 200); NASA FIRMS fires; IMD radar is referenced via Open-Meteo precipitation proxy (documented). | `scripts/download_*.py`, `backend/app/services/refresh_service.py` | ✅ | IMD raw radar not directly consumed; ERA5 optional via CDS. |
| R10 | **Validated / backtested forecasts (chronological)** | Evaluation machinery with chronological holdout; metrics persisted to `model_metrics` and `models/*.json`. | `ml/training/evaluator.py`, `backend/app/api/model_metrics.py`, `backend/tests/integration/test_full_pipeline.py` | ✅ | Re-run evaluation when retraining with new features; 72h smoke/NO2 remain the weakest horizons. |
| R11 | **Indian AQI (CPCB breakpoints)** | Breakpoint AQI calculator produces `aqi`, `aqi_category`, `dominant_pollutant` on current + forecast data. | `backend/app/services/aqi_calculator.py`, `backend/app/api/current.py` | ✅ | — |
| R12 | **Explainability** | Real `shap.TreeExplainer` when a tree model is loaded; honest fallback when not. | `backend/app/services/explanation_service.py`, `frontend/src/pages/AIExplanation.tsx` | ✅ | SHAP on tree models only (not persistence). |
| R13 | **Alerts (INFO→WATCH→WARNING→SEVERE)** | Alerts computed from actual forecast/weather/fire AQI and hazard values: `INFO`, `WATCH`, `WARNING`, `SEVERE`. | `backend/app/services/alert_service.py`, `backend/app/api/alerts.py`, `frontend/src/pages/Alerts.tsx` | ✅ | Alert thresholds are configurable constants. |
| R14 | **Dashboard with map layers (FIRMS hotspots, wind, transport)** | Leaflet NCR map now renders FIRMS hotspots (FRP-sized/colored circles) + stations, with live plume-transport summary card (headline risk, wind-aligned %, smoke arrival time). Wind vector shown via transport-direction labeling; standalone Inversion/PBL panel added. | `frontend/src/pages/NCRMap.tsx`, `frontend/src/components/StationMap.tsx`, `frontend/src/components/StubblePlume.tsx`, `frontend/src/pages/Atmosphere.tsx` | ✅ | Wind *vectors* (per-station arrows) not yet drawn; direction labels + hotspot overlay provided. |
| R15 | **Direct PM2.5 forecast engine (multi-horizon, conformal intervals)** | XGBoost model trained per pollutant per horizon with conformal prediction intervals; GRU available as optional model variant. Endpoints: `/api/forecast/pm25`, `/api/forecast/pm25/model-card`, `/api/forecast/pm25/explanation`. | `ml/training/train_pm25.py`, `ml/inference/pm25_forecaster.py`, `models/pm25/`, `backend/app/api/pm25_forecast.py` | ✅ | Conformal intervals are distribution-free; coverage degrades at longer horizons. |
| R16 | **Pollution event detection (surge / relief / sustained high-risk)** | Statistical event detection from time-series anomalies: z-score surge, sustained episodes, relief transitions. Endpoint: `/api/events/current`. | `backend/app/services/events_service.py`, `backend/app/api/events.py`, `docs/events.md` | ✅ | Thresholds heuristic; documented as analytical overlays, not regulatory alerts. |
| R17 | **Scenario analysis (what-if engine)** | Read-only perturbation engine: wind speed/direction, PBL height, fire activity, inversion strength adjustments propagated through the coupled model. Endpoint: `/api/scenario/analysis`. | `backend/app/services/scenario_service.py`, `backend/app/api/scenario.py`, `docs/scenario_analysis.md` | ✅ | Purely analytical; not a policy simulator. |
| R18 | **Model performance dashboard** | Persisted cross-model performance comparison (persistence / RF / XGBoost / GRU) across horizons with MAE/RMSE/R² metrics. Endpoint: `/api/model/performance`. | `backend/app/api/model_performance.py`, `frontend/src/pages/ModelPerformancePage.tsx`, `frontend/src/components/ModelPerformance.tsx` | ✅ | Metrics are from the most recent chronological evaluation run. |
| R19 | **4-model evaluation (persistence / RF / XGBoost / GRU)** | Full evaluation suite in `models/pm25/evaluation.json` and `evaluation.csv`: persistence, RF, XGBoost, and GRU across all 6 horizons. | `ml/training/evaluate_pm25.py`, `models/pm25/evaluation.json`, `models/pm25/evaluation.csv` | ✅ | GRU honestly underperforms tree ensemble; results not inflated. |

---

## 2. New vertical-atmosphere method (exact definition)

Given standard-level temperatures `T(p)` (degC, Open-Meteo, UTC) for levels 1000/925/850/700 hPa:

1. Layer gradient (linear in pressure, transparent units):

       ∇T_layer = (T_top − T_base) / (p_base − p_top) × 100   [K / 100 hPa]

   `p_base > p_top`. `∇T > 0` ⇒ temperature increases with height ⇒ **inversion over that layer**.
2. Classify the strongest (max) layer gradient:

       category (∇T·max)            detected
       ≤ 0.0   K/100hPa   none       No
       (0, 0.6]           weak       Yes
       (0.6, 1.5]         moderate   Yes
       > 1.5              strong     Yes

3. `inversion_strength` (0–1) = min(1, (∇T−0)/(∇T_max_threshold−0)) clipped, where the cite-able
   max is 4.0 K/100 hPa; `%` shown is score×100.
4. Report `inversion_base_pressure` / `inversion_top_pressure` as the strongest layer.
5. PBL classification (used in combination, and as fallback when <2 levels exist):

       pbl_height (m)   pbl_category          dispersion_condition
       < 150            strong_trapping       TRAPPED
       [150, 300)       moderate_trapping     LIMITED
       [300, 500)       weak_trapping         MODERATE
       ≥ 500            good_dispersion       GOOD
       missing          unknown               UNKNOWN

Thresholds are heuristic, stated in the code, and never presented as reanalysis climatology.

---

## 3. Fire-transport features (exact definition)

From real NASA FIRMS detections within 500 km of each station and live surface wind:

```
wind_alignment_pct   = 100 × upwind_fires / fires_in_radius          [%]
transport_time_hours = nearest_fire_km / (wind_speed_mps × 3.6)      [h]   (≈0 when wind ≤ 0.5 m/s)
transport_risk       = 0.4·fire_impact + 0.3·proximity + 0.2·alignment + 0.1·time  ∈ [0,1]
stubble_impact_score = fire_impact × (0.5 + 0.5·alignment)           ∈ [0,1]  (PM2.5 fraction proxy)
```

These are **advective transport estimates**, not dispersion simulations. The 2D PDE
`dispersion_solver.py` is the actual numerical dispersion module.

---

## 4. Verification runs performed (this session)

| Check | Command | Result |
|-------|---------|--------|
| Full backend test suite | `python -m pytest backend/tests -q` | **225 passed** |
| Lint (changed files) | `python -m ruff check <files> --config pyproject.toml` | **All checks passed** |
| Frontend TypeScript + build | `cd frontend && npm run build` | **build succeeds** (tsc + vite) |
| Live pressure-level fetch | Open-Meteo `temperature_{1000,925,850,700}hPa` + `geopotential_height_{925,850}hPa` | HTTP 200, real values |
| Lapse-rate examples | normal / weak / strong / missing-data | correct category + source selection |
| Inversion API (live) | `GET /api/inversion/{station}` | `inversion_source: lapse_rate` when vertical data present, `pbl_proxy` fallback otherwise |
| Fire endpoints (live) | `/api/fire-activity`, `/api/plume-risk`, `/api/fire/hotspots`, `/api/fire/transport` | HTTP 200, real FIRMS+wind data |
| Migration | `apply_migrations()` / additive ALTER | weather_readings gained 6 pressure-level columns, existing rows preserved |

---

## 5. Files changed / created in Phase-2 + Phase-3

**Created (Phase-2)**
- `docs/SIH_GAP_AUDIT.md`
- `docs/SIH_FINAL_COMPLIANCE.md` (this file)
- `backend/app/services/atmospheric/__init__.py`
- `backend/app/services/atmospheric/vertical_atmosphere.py`
- `ml/features/atmospheric_profile.py`
- `backend/tests/unit/test_vertical_atmosphere.py`

**Created (Phase-3)**
- `ml/training/train_gru.py` — custom NumPy GRU implementation
- `ml/models/gru_model.py` — 2-layer GRU forward/backward pass
- `models/pm25/gru/` — trained GRU model weights
- `models/pm25/evaluation.json` — full 4-model evaluation (persistence / RF / XGBoost / GRU)
- `backend/app/services/events_service.py` — pollution event detection
- `backend/app/api/events.py` — `/api/events/current`
- `backend/app/services/scenario_service.py` — what-if scenario engine
- `backend/app/api/scenario.py` — `/api/scenario/analysis`
- `backend/app/api/pm25_forecast.py` — `/api/forecast/pm25` + model-card + explanation
- `backend/app/api/model_performance.py` — `/api/model/performance`
- `frontend/src/pages/ModelPerformancePage.tsx`
- `frontend/src/components/ModelPerformance.tsx`
- `docs/events.md`, `docs/scenario_analysis.md`

**Modified (Phase-2)**
- `ml/features/inversion.py` — added lapse-rate inversion features (`add_lapse_rate_inversion_features`, `_extract_temp_by_level`); legacy `detect_inversion`/`add_inversion_features` preserved (backward compatible).
- `ml/features/fire_impact.py` — added `wind_alignment_pct`, `transport_time_hours`, `transport_risk(+level)`, `stubble_impact_score`.
- `ml/features/feature_engineering.py` — wire lapse-rate inversion features; FEATURE_DOCUMENTATION extended.
- `backend/app/api/inversion.py` — reuse `ml/features/atmospheric_profile`; adds source/layer/PBL/dispersion fields; deterministic from DB.
- `backend/app/api/fire.py` — `/plume-risk` returns transport metrics; new `/fire/hotspots`.
- `backend/app/schemas/schemas.py` — extended `InversionResponse`, `PlumeRiskResponse`, added `FireHotspot(s)Response`.
- `backend/app/database.py` — additive migrations for pressure-level columns.
- `backend/app/models/db_models.py` — additive `WeatherReading` columns.
- `backend/app/services/refresh_service.py` — pressure-level fetch + forecast supplement + vertical backfill.
- `backend/app/services/forecast_service.py` — vertical temps + lapse-rate features in `build_features_from_db`.
- `frontend/src/types/index.ts`, `frontend/src/api/client.ts`, `frontend/src/components/InversionPanel.tsx`, `frontend/src/components/StationMap.tsx`, `frontend/src/components/StubblePlume.tsx`, `frontend/src/pages/NCRMap.tsx`

**Preserved (not modified unnecessarily)** — `dispersion_solver.py`, `coupling.py`, `ml/preprocessing/*`,
existing API endpoints, trained `.joblib` models, `aerocast_ncr.db`.

---

## 6. How to run / retrain / verify

```powershell
# 1. Full stack (frontend + backend, one command)
python -m scripts.run_dev --port 8000 --frontend

# 2. Manual (alternative)
python -m alembic upgrade head            # run from project root
cd backend; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
cd frontend; npm run dev

# 3. Refresh live vertical/weather data (network required)
python -c "import sys; sys.path.insert(0,'backend'); from app.database import SessionLocal; from app.services.refresh_service import refresh_weather; db=SessionLocal(); print(refresh_weather(db)); db.commit()"

# 4. Retrain (chronological split, 6 pollutants × 6 horizons)
python -m ml.training.trainer

# 5. Tests + lint
python -m pytest backend/tests -q
python -m ruff check ml backend --config pyproject.toml

# 6. Train GRU (custom NumPy, no PyTorch required)
python -m ml.training.train_gru

# 7. Full PM2.5 evaluation (persistence / RF / XGBoost / GRU)
python -m ml.training.evaluate_pm25
```