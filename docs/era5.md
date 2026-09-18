# ERA5 reanalysis ingestion (WS-2)

## Purpose

The offline feature pipeline can absorb **genuine** ERA5 single-level
reanalysis over Delhi NCR into the coupled dataset used for training and
explanation. This is the Copernicus-CDS pathway referenced by problem-statement
R9 ("CPCB + IMD + ERA5/ecmwf + FIRMS").

## Honesty gates

ERA5 is **never fabricated**:

- `ml/features/era5_surface.era5_reasons(path)` reports exactly what is
  missing (no NetCDF file, no reader backend) and
  `ml/features/era5_surface.load_era5_surface(path)` returns an *empty
  DataFrame* when real data is absent.
- `scripts/build_dataset.py::load_atmosphere` then prints
  "WARNING: ERA5 atmosphere unavailable (...); using Open-Meteo weather only"
  so the built dataset stays honest and provenance-aware.
- Only per-station rows derived from downloaded CDS NetCDF files enter the
  dataset — every value is a real reanalysis sample, never a placeholder.

## Data flow

```text
Copernicus CDS (reanalysis-era5-single-levels)
  2m_temperature, surface_pressure, boundary_layer_height
   – download_atmosphere.py (~/.cdsapirc + cdsapi; one NetCDF per year)
        |
        v
data/atmosphere/era5_atmosphere_<YYYY>.nc      (real ERA5 grids)
        |
        v  ml.features.era5_surface.load_era5_surface()  — nearest grid cell
      at the 17 curated NCR stations, units converted (K→°C, Pa→hPa)
        |
        v
data/atmosphere/era5_atmosphere.csv
  columns: time, station, era5_temperature, era5_surface_pressure, era5_blh
        |
        v
scripts/build_dataset.py  → merged into the coupled dataset as era5_* features
```

NetCDF reading prefers `netCDF4` > `xarray` > `scipy.io.netcdf_file`. The
last works with **zero extra dependencies** because CDS ships NetCDF3-classic
files (`format: netcdf`). CDS files spanning 1940+ contain an `expver`
dimension; the reader keeps the last (reanalysis) entry.

## Usage

```powershell
# Requires a free CDS account: https://cds.climate.copernicus.eu/how-to-api
# ~/.cdsapirc  (key: UID header: UID   key: API key   url: https://cds.climate.copernicus.eu/api/v2)
# pip install cdsapi

python -m scripts.download_atmosphere --start-date 2023-01-01 --end-date 2024-12-31
python -m scripts.download_atmosphere --no-download          # preview the request(s)
python -m scripts.download_atmosphere --force                # re-download existing years
```

When CDS is unreachable/unauthorised the script writes an *empty*
`era5_atmosphere.csv` placeholder and explains why; `build_dataset.py`
detects the empty source and continues with Open-Meteo weather.

## SQL/frontend impact

None. ERA5 feeds the offline model-training/explanation dataset
(`scripts/build_dataset.py`) and is orthogonal to the live refresh path, which
uses Open-Meteo archive + forecast (verified live) for the hourly API.

## Tests

`backend/tests/unit/test_era5_surface.py` (8 tests): missing-file reasons and
empty frames; multi-year globbing; nearest-grid-cell sampling with exact
values + unit conversions; descending-latitude grids; `expver`-dimension
handling; empty-placeholder vs real CSV loading; `build_dataset.py` glue
(prefers CSV, warns when absent).