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
