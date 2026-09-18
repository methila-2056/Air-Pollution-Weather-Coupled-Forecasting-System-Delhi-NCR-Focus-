# WRF-Chem adapter (R6 / WS-4)

AeroCast-NCR consumes **genuine** WRF-Chem output as its second CTM engine
(priority after HYSPLIT). This page states the contract precisely.

## What the adapter does

`ml/ctm/wrfchem_adapter.py` maps a directory of real WRF-Chem `wrfout_d01_*.nc`
NetCDF files onto the NCR grid:

- Reads the ground-level PM2.5 field (preference order `PM2_5_DRY`, `PM2_5`,
  `PM25`, `PM2_5_DRY_ANTHRO`) with `xarray`/`netCDF4`.
- Resamples onto the caller's `lat_min..lat_max / lon_min..lon_max / grid_step`
  axes by nearest-grid-cell selection using the file's own `XLAT`/`XLONG`.
- Returns a `CtmResult` whose `units` are taken **verbatim from the file**
  (default `ug/m3`) — no artificial normalization.

## Honesty gates

`is_available()` is `True` only when **all** of these hold:

1. `WRF_OUTPUT_DIR` / `wrf_output_dir` points at an existing directory with
   `wrfout_d01_*` files,
2. the NetCDF stack (`netCDF4` + `xarray`) is importable, and
3. at least one PM2.5 variable is present in the first file.

Otherwise `unavailable_reasons()` enumerates the missing ingredient and `run()`
raises `CtmUnavailable`; the analytic surrogate remains active. **WRF-Chem
itself is never executed or simulated by this project** — it is heavy HPC
Fortran that an external operator runs; this adapter only *consumes* its real
output.

## Operational notes

- Install the reader stack when you want to absorb WRF-Chem output:
  `pip install netCDF4 xarray`.
- Place output as `wrfout_d01_YYYY-MM-DD_HH:MM:SS.nc` files in one directory and
  set it in `.env` (`wrf_output_dir=...`) or via `WRF_OUTPUT_DIR`.
- The adapter stops assembling frames once it has `hours` frames.

## Integration

Through `ml/ctm/ctm_interface.py` (`register` + `run_best_engine`), the
dispersion service tries WRF-Chem *before* HYSPLIT and *only* uses it when
genuinely available; its plume pattern is composited with the coupled forecast
surface exactly as described in `docs/hysplit.md` ("Wiring"), with engine and
units disclosed in the response `ctm` block.

## Tests

`backend/tests/unit/test_ctm_engines.py` asserts the registry contains exactly
one `WRF-Chem` entry and that the engine is honestly unavailable (and
`run_best_engine` falls back) when no NetCDF stack / no genuine output files are
configured.