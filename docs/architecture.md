# Architecture

## Overview

AeroCast-NCR is a multi-layered system that fuses air quality, meteorological, fire, and atmospheric data to produce 72-hour forecasts of particulate matter (PM2.5, PM10) and gaseous pollutants (O3, NO2) with AI-based explainability for Delhi NCR.

## System Layers

### 1. Data Acquisition Layer
- **CPCB** pollution observations (real-time + historical)
- **Open-Meteo** weather forecasts and reanalysis
- **NASA FIRMS** active fire hotspots (VIIRS/MODIS)
- **Copernicus ERA5** atmospheric boundary layer reanalysis

### 2. Data Processing & Feature Engineering Layer
- Cleaning, gap-filling, and temporal alignment of observations
- Feature engineering: lagged pollutants, diurnal/seasonal cycles, inversion indicators, fire-impact scores, PBL metrics

### 3. ML Forecasting Layer
- Baseline: persistence model
- Traditional: Random Forest
- Primary: XGBoost per pollutant per horizon hour (1h, 6h, 12h, 24h, 48h, 72h)

### 4. AQI & Interpretation Layer
- CPCB AQI aggregation engine
- SHAP-based feature attribution
- Natural language explanation generation

### 5. Presentation Layer
- React + TypeScript dashboard
- Recharts visualizations
- Leaflet NCR map
- Alert / recommendation engine

## Component Diagram

```
[Database] <-> [FastAPI backend] <-> [React frontend]
     ^               ^
     |               |
[ML models (joblib)]  [SHAP explanation service]
```

## Backend Structure

- `app/api/` — REST endpoints per domain (stations, forecast, weather, inversion, fire, explanation, alerts, metrics)
- `app/services/` — business logic (AQI calculation, forecasting, explanation, alerts)
- `app/models/` — SQLAlchemy ORM models
- `app/schemas/` — Pydantic response/request models
