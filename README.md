# AeroCast-NCR

**AI-Powered 72-Hour Air Quality & Pollution-Plume Forecasting for Delhi NCR**

> Problem Statement: SIH26082 | Ministry of Earth Sciences | NCMRWF

> Includes a physics-informed **two-way weather–chemistry coupling** module
> (aerosol AOD → solar attenuation → PBL suppression → stability feedback),
> exposed via `/api/coupling/{station}` and the Weather↔Chemistry dashboard panel.

## Architecture

```
CPCB (Pollution) + Open-Meteo (Weather) + NASA FIRMS (Fire) + ERA5 (Atmosphere)
        ↓
    Data Fusion & Feature Engineering
        ↓
    XGBoost / ML Forecasting
        ↓
    72-Hour Pollutant Forecast
        ↓
    AQI Engine → Dashboard → Alerts → Explainability → Coupling Feedback
```

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env

# 2. Start with Docker
docker-compose up -d

# 3. Download data
python scripts/download_weather.py
python scripts/download_pollution.py
python scripts/download_fire.py
python scripts/build_dataset.py

# 4. Train model
python -m ml.training.trainer

# 5. Access
# Backend: http://localhost:8000
# Frontend: http://localhost:5173
```

## Tech Stack

- **Backend:** Python, FastAPI, PostgreSQL, SQLAlchemy
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, Recharts, Leaflet
- **ML:** XGBoost, Scikit-learn, SHAP, Pandas
- **Data:** CPCB, Open-Meteo, NASA FIRMS, Copernicus ERA5

## Data Sources

| Source | Data | Access |
|--------|------|--------|
| CPCB / data.gov.in | PM2.5, PM10, O3, NO2, SO2, CO, AQI | API / CSV |
| Open-Meteo | Temperature, Humidity, Wind, Pressure, PBL | Free API |
| NASA FIRMS | Fire hotspots, FRP, confidence | API (MAP_KEY) |
| Copernicus ERA5 | Atmospheric reanalysis | CDS API |
