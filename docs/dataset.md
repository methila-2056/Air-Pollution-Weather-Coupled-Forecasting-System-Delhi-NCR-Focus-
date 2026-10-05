# Dataset

## Data Sources

### 1. Pollution (CPCB / data.gov.in — official)
- **Parameters:** PM2.5, PM10, O3, NO2, SO2, CO, AQI
- **Stations:** Key Delhi NCR monitors (Anand Vihar, ITO, Punjabi Bagh, Dwarka, etc.)
- **Frequency:** Hourly, refreshed
- **Access:** Official Government of India "Real time Air Quality Index from
  various locations" API (`api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69`).
  Ingestion via `POST /api/pollution/ingest` → `backend/app/services/cpcb_service.py`.

  ### 2. Weather (Open-Meteo)
  - **Parameters:** Temperature, relative humidity, MSL pressure, surface pressure, 10m wind speed & direction, precipitation, cloud cover, planetary boundary layer height
  - **Area:** Gridded over Delhi NCR (28.4A°N–28.9A°N, 76.8A°E–77.4A°E)
  - **Frequency:** Hourly; `weather_observations` holds archive (analysis) hours
    only, bounded at the current instant. Forecast hours are never persisted —
    they are fetched separately and served in memory by the forecast-context
    builder (`docs/weather_data_source.md` §5–§6).
  - **Provenance note (current schema):** `weather_observations` does **not** carry provenance columns (`data_source`, `re_stamped`/`is_re_stamped`) in the current schema. By contrast, `pollution_observations` carries `data_source` and `re_stamped`, and `fire_readings` carries `synthetic` and `source`. The `bootstrap_recent.py` script sets `re_stamped=True` when creating WeatherReading rows, but the `WeatherReading` model does not define a `re_stamped`/`is_re_stamped` column (schema drift). Any future addition of weather provenance requires a model + migration change.

### 3. Fire (NASA FIRMS)
- **Parameters:** Latitude, longitude, acquisition datetime, confidence (nominal/high), Fire Radiative Power (FRP), satellite, day/night
- **Area:** Punjab, Haryana, Rajasthan crop-residue burning belt (upwind of Delhi)
- **Frequency:** Near real-time (MODIS ~daily, VIIRS ~6h)

### 4. Atmosphere (Copernicus ERA5)
- **Parameters:** Planetary boundary layer height, temperature profile, wind profile, inversion indicators
- **Frequency:** Hourly reanalysis

## Data Flow

```
raw/ ──> processed/ ──> feature-engineered dataset ──> train/test split
```

## Directory Layout

- `ml/data/raw/` — downloaded source files
- `ml/data/processed/` — cleaned, merged tables
- `ml/data/external/` — static reference data (station metadata, grids)
- `data/` — application-level data mounted into containers

## Build Pipeline

1. `scripts/download_pollution.py` — fetch CPCB data
2. `scripts/download_weather.py` — fetch Open-Meteo data
3. `scripts/download_fire.py` — fetch NASA FIRMS data
4. `scripts/download_atmosphere.py` — fetch ERA5 data
5. `scripts/build_dataset.py` — merge all into training dataset
