# Dataset

## Data Sources

### 1. Pollution (CPCB / data.gov.in)
- **Parameters:** PM2.5, PM10, O3, NO2, SO2, CO, AQI
- **Stations:** Key Delhi NCR monitors (Anand Vihar, ITO, Punjabi Bagh, Dwarka, etc.)
- **Frequency:** Hourly, refreshed
- **Access:** CPCB real-time API / historical CSV dumps via data.gov.in

### 2. Weather (Open-Meteo)
- **Parameters:** Temperature, relative humidity, MSL pressure, surface pressure, 10m wind speed & direction, precipitation, cloud cover, planetary boundary layer height
- **Area:** Gridded over Delhi NCR (28.4°N–28.9°N, 76.8°E–77.4°E)
- **Frequency:** Hourly; both historical and forecast

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
