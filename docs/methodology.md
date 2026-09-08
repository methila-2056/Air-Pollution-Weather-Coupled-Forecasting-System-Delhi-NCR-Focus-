# Methodology

## 1. AQI Calculation

CPCB AQI is the maximum Sub-Index (IAQI) across pollutants. Each pollutant concentration is mapped through breakpoint tables to a 0–500 sub-index, then the maximum becomes the overall AQI with a category band (Good → Severe).

## 2. Feature Engineering

- **Lagged variables:** PM2.5 at t-1, t-3, t-6, t-12, t-24
- **Meteorological features:** temperature, humidity, wind components (u/v), pressure tendency
- **Inversion metrics:** PBL height, temperature gradient, stability classification
- **Fire impact:** aggregated FRP-weighted fire counts within upwind sectors, distance-weighted nearest-fire index
- **Cyclic features:** hour-of-day, day-of-week, month sinusoidal encodings

## 3. Modeling

- **Persistence Baseline:** PM2.5(t+h) = PM2.5(t). Serves as sanity check for ML gains.
- **Random Forest:** Nonlinear baselines with feature importance.
- **XGBoost (primary):** Gradient-boosted trees; one model per pollutant per horizon (1, 6, 12, 24, 48, 72h).

### Evaluation
- Metrics: MAE, RMSE, R², MAPE
- Temporal holdout split (train on past, test on recent season) to avoid leakage
- Rolling window backtesting for horizon robustness

## 4. Explainability (SHAP)

SHAP TreeExplainer attributes each prediction to input features with magnitude and direction. Top contributing features are rendered as natural-language statements explaining why AQI is elevated (e.g., low wind, inversion, fire plumes).

## 5. Alerts

Rule-based alert generation combines:
- Forecast AQI category thresholds
- Low wind speed (poor dispersion)
- Low PBL height (trapping)
- Regional fire density / plume risk

Each alert carries level (WATCH / WARNING / SEVERE), factors, and recommendations.

## 6. Plume Transport Risk

Risk score estimates the likelihood that regional stubble fires impact Delhi NCR, based on fire count, distance, FRP intensity, and prevailing wind direction (NW → SE during the post-monsoon/winter season).

## 7. Two-Way Weather–Chemistry Coupling Feedback

A core requirement of SIH26082 is the coupled feedback between meteorology and
chemistry. The system encodes the aerosol–radiation–boundary-layer feedback loop
(`ml/features/coupling.py`):

**Forward path (meteorology → chemistry):** PBL height, temperature, wind,
humidity, and inversion strength drive pollutant dispersion / accumulation.
These already feed the ML forecasters as features.

**Backward path (chemistry → meteorology):**
- AOD is estimated from surface PM2.5 loading.
- Aerosols attenuate incoming solar radiation (Beer–Lambert transmittance).
- Reduced surface heating suppresses daytime PBL growth (PBL suppression factor).
- A suppressed PBL + light winds → elevated stability coupling index.
- High stability → higher pollutant retention → further PM2.5 accumulation
  (positive feedback), captured by the feedback multiplier.

The module exposes these corrections (`corrected_pbl_height`,
`pbl_suppression_factor`, `radiation_transmittance`, `aod_est`,
`stability_coupling_index`, `feedback_multiplier`) as engineered features at
training time AND in live inference, so the ML forecasters can learn the coupled
dynamics. A dedicated `/api/coupling/{station}` endpoint reports the diagnostics with a natural-language narrative, surfaced in the dashboard's Weather↔Chemistry panel.

### 7.1 Online Time-Stepped Coupled Forecast Loop

Beyond the single-pass coupling diagnostics, the system runs a **sequential
two-way coupled forecasting simulation** (`ml/features/coupled_loop.py`) that
advances meteorology and chemistry together, hour by hour:

```
for each hour step h:
    1. predict next-hour PM2.5/PM10/O3/NO2/SO2/CO from current features        (meteo -> chemistry)
    2. derive aerosol radiative forcing from the freshly forecast PM2.5
       (AOD, transmittance, PBL suppression, stability)                        (chemistry -> meteo)
    3. correct PBL height, temperature, inversion strength, stability index
    4. persist the corrected meteorology + advanced pollution lags
       and re-enter the loop with the corrected fields                         (two-way feedback)
```

The result is a genuine online coupling simulation rather than a one-pass
statistical forecast. The `/api/forecast/coupled` endpoint returns both the
**coupled** series and the direct (**uncoupled**) series for skill comparison,
plus the hour-by-hour `feedback_path` showing how the effective PBL height and
stability index evolve as aerosol loading feeds back into the meteorology.

### 7.2 Complete Criteria-Pollutant Forecast (SO2 + CO)

The forecast now covers **all six CPCB criteria pollutants** — PM2.5, PM10, O3,
NO2, SO2 and CO — each modelled across all horizons (1h–72h) and all model
families (persistence, random forest, XGBoost). SO2/CO use their own lag,
wind-dispersion and precipitation-washout physics in the coupled propagation.

## 8. High-Resolution Spatial Forecasting

`backend/app/services/grid_service.py` constructs a **~2.2 km gridded AQI
surface** over the Delhi NCR domain (28.2–28.9°N, 76.6–77.5°E) at 0.02°
resolution. Per-station coupled forecasts for a chosen horizon are interpolated
by **inverse-distance weighting (IDW)**, then optionally biased downwind by the
prevailing transport wind (`advective_shift`), so the plume surface reflects
advection of transported pollution. The `/api/grid/forecast` endpoint returns
GeoJSON-style cells (lat/lon/AQI/category) rendered as a colour-coded heatmap
with the monitoring stations overlaid (`/spatial` dashboard page).

## 9. Numerical Dispersion Transport Core (WRF-Chem-style dynamical surrogate)

Where §8 is *statistical* (interpolation of station forecasts), the
**numerical core** (`ml/features/dispersion_solver.py`, service
`backend/app/services/dispersion_service.py`) solves the actual transport
equation on the same 36×46 NCR grid by **finite differences**, explicitly
addressing the PS requirement to *"predict how stubble-burning plumes will
disperse under prevailing weather"* and to dynamically interlink meteorology
with pollution:

```
dC/dt = -u·dC/dx - v·dC/dy      wind advection (upwind flux, open lateral inflow)
        + K_h·∇²C                horizontal turbulent diffusion
        - (λ_dep + λ_wet)·C      dry deposition + wet scavenging
        + E(x,y,t)               point (stubble fire FRP) + urban area sources
```

pipeline (`GET /api/dispersion/forecast?horizon_hours=72`):

1. **Lateral boundary condition** — the latest persisted station AQI forecast
   (IDW) seeds the initial field; the domain-time-mean concentration continuously
   re-enters at the upwind boundary, keeping regional burden realistic over 72h.
2. **Sources** — live VIIRS-scale stubble fires inside the NCR box are injected
   as Gaussian point plumes proportional to `FRP`; the Delhi metro + NCR belt
   receives a persistent urban emission rate balancing deposition/outflow.
3. **Meteorology** — live PBL/wind/precipitation from `weather_readings` drive a
   diurnal PBL cycle (shallow night, deep solar-noon) and per-hour advection.
4. **Two-way coupling** — the resolved aerosol loading feeds back via
   `corrected_pbl_height` / `boundary_stability_index` (coupling module):
   elevated PM₂.₅ suppresses PBL growth and raises the stability-coupling index,
   reducing lateral mixing and strengthening retention (chemistry → meteorology);
   the resulting shallow, stable layer then increases pollutant trapping
   (meteorology → chemistry).
5. Output per hour: AQI grid frames, fire plume positions, PBL/stability/precip
   + the four coupling diagnostics.

Numerics: explicit upwind advection with CFL-safe adaptive step
(`dt = 0.5·dx/max_wind`, ≈277 s at 4 m/s), 5-point diffusive operator with
reflecting interior + open outflow boundaries, non-negativity preserving
(120+ test-green). The solver integrates a full 72-hour horizon in <1 s
(pure vectorised numpy), so the `/spatial` dashboard can switch between the
statistical grid and the live numerical field, overlaying fire plumes.

### 9.1 Surrogate vs. literal WRF-Chem (honest-scope tradeoff)

The PS names "WRF-Chem or similar coupled frameworks". AeroCast-NCR ships a
physics-informed **dynamical surrogate**, not compiled WRF-Chem. This section
makes that tradeoff explicit, states how the surrogate is validated, and lists
exactly what a literal deployment would require.

| Dimension | AeroCast-NCR surrogate | Literal WRF-Chem |
|-----------|------------------------|------------------|
| Transport core | Vectorised finite-difference advection–diffusion–deposition (`dispersion_solver.py`) | Compiled Fortran (WPS + real-data WRF + CHEM), GNU/Intel compilers |
| Two-way coupling | Aerosol AOD → transmittance → PBL suppression → stability index, applied per time-step in the Python loop | Online chemistry–radiation–PBL feedback inside the WRF time-integration |
| Chemistry | Parametric criteria-pollutant mass (PM2.5/PM10/O3/NO2/SO2/CO) with deposition + wet scavenging rates | Full gas/aerosol schemes (e.g. MOZART / GOCART), hundreds of species |
| Emissions | FRP-based fire point sources + steady urban area rates | Full gridded inventories (e.g. EDGAR, SAFAR, GFAS biomass) with diurnal profiles |
| Initial/BC | IDW of nearest observed station AQI | 3-D meteorological reanalysis (ERA5/GFS) interpolation + chemical IC/BC |
| Runtime | ≈1 s per 72 h horizon on a laptop | Hourly–minutes per day-forecast on HPC / many-core clusters |
| Footprint | Pure Python + numpy, no compilation | Fortran toolchain, WPS/WRF/CHEM builds, MPI, ≥10s GB input data |

**Validation strategy (surrogate).** The surrogate is treated as a statistical–
physical forecasting model and validated three ways:

1. **Forecast skill vs. baseline.** Persistence vs. RF vs. XGBoost across all
   six pollutants and horizons {1,6,12,24,48,72}, reported in
   `/api/model-metrics` (MAE/RMSE/R²/MAPE) from held-out test splits
   (`ml/training/evaluator.py`). This measures the *statistical* quality of the
   ML layer on real CPCB/fire data.
2. **Physical-plausibility invariants.** The dispersion solver's numerical
   behaviour is pinned by unit tests: non-negativity, mass non-increasing under
   pure deposition, upwind transport of a Gaussian puff, reflecting/outflow
   boundary handling, and CFL stability (`ml/features/dispersion_solver.py`,
   `TestDispersionForecast`).
3. **Consistency with observational constraints.** Forecast AQI is classified
   into CPCB AQI categories and compared against live station readings via
   `/api/data-quality` and forecast-vs-actual deltas (`/api/forecast/comparison`).
   Directional agreement (plume sector vs. prevailing wind, downwind retention)
   is checked against the injected FIRMS fire locations.

A literal WRF-Chem run would additionally allow quantitative process-level
validation against, e.g., observed ozone photochemistry or aerosol optical depth
— which the surrogate does not attempt to reproduce.

**What a literal WRF-Chem deployment would require.** If the project were scaled
to true WRF-Chem, one would need: (a) a WPS/WRF/CHEM toolchain (Fortran, MPI,
netCDF) with domain/namelist configuration for the NCR domain; (b) ERA5/GFS
meteorological initial/boundary conditions; (c) gridded chemical initial/boundary
conditions and a gas/aerosol chemistry option; (d) SAFAR/EDGAR/GFAS emission
inventories processed for the same grid; (e) HPC resources with real-time
turnaround; and (f) an operational data-acquisition + archiving pipeline. That is
a multi-month, HPC-scale effort outside a student hackathon — hence the honest
surrogate, which preserves the *mechanistic outcomes* the PS asks for (plume
dispersion prediction, meteorological interlink, 72 h AQI, NCR-wide spatial
coverage) while remaining reproducible in minutes on commodity hardware.

