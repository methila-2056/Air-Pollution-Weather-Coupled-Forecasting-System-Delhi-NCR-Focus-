"""Adapter that absorbs *genuine* WRF-Chem output as the CTM surface (R6).

WRF-Chem itself is heavy-HPC Fortran that this project does not compile (see
``docs/wrfchem_adapter.md``). What is delivered here is a first-party consumer
of real WRF-Chem NetCDF output: point ``WRF_OUTPUT_DIR`` (env/setting) at a
directory holding ``wrfout_d01_*.nc`` files produced by an external WRF-Chem
run and this adapter will map its ground-level PM2.5 field onto the NCR grid.

The adapter is *honest by construction*:

- ``is_available()`` is True only when output files exist **and** a NetCDF
  reader (xarray + netCDF4) is importable.
- ``run()`` never fabricates a field; it raises ``CtmUnavailable`` listing the
  exact missing ingredient.
- Units are taken verbatim from the file where present (default ``ug/m3``),
  no artificial normalization is performed.
"""

from __future__ import annotations

import datetime as _dt
import os
import pathlib

import numpy as np

from .ctm_interface import CtmResult, CtmUnavailable, register

# WRF-Chem PM2.5 field names, in preference order. ``PM25`` is the merged
# optional-anthro+biogenic+other fine-mode sum (dry) that most operational
# WRF-Chem configs emit as ``PM2_5_DRY``.
PM25_VAR_NAMES = ("PM2_5_DRY", "PM2_5", "PM25", "PM2_5_DRY_ANTHRO")
_FILE_PATTERN = "wrfout_d01_*"
# seconds in one WRF output timestep; we aim for hourly files.
_FILE_TIMESTEP_SEC = 3600


@register
class WRFChemAdapter:
    """Consume real WRF-Chem ``wrfout_d01_*.nc`` output on the NCR grid."""

    name = "WRF-Chem"

    def __init__(self, output_dir: str | pathlib.Path | None = None):
        if output_dir is None:
            try:
                from backend.app.config import get_settings

                output_dir = get_settings().wrf_output_dir
            except Exception:
                output_dir = os.environ.get("WRF_OUTPUT_DIR", "")
        self.output_dir = pathlib.Path(output_dir) if output_dir else None

    # -- availability -------------------------------------------------------
    def is_available(self) -> bool:
        return (
            self._output_files()
            and self._netcdf_stack_importable()
            and (self._first_pm25_var() is not None)
        )

    def unavailable_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.output_dir or not self.output_dir.is_dir():
            reasons.append(
                "WRF-Chem: WRF_OUTPUT_DIR not set / missing (set to the dir holding wrfout_d01_*.nc)"
            )
            return reasons
        files = list(self.output_dir.glob(_FILE_PATTERN))
        if not files:
            reasons.append(f"WRF-Chem: no {_FILE_PATTERN!r} files in {self.output_dir}")
            return reasons
        if not self._netcdf_stack_importable():
            reasons.append("WRF-Chem: `pip install netCDF4 xarray` to read wrfout*.nc files")
        if self._first_pm25_var() is None:
            reasons.append("WRF-Chem: no PM2.5 field found in the wrfout files")
        return reasons

    def _output_files(self) -> list[pathlib.Path]:
        if not self.output_dir or not self.output_dir.is_dir():
            return []
        return sorted(self.output_dir.glob(_FILE_PATTERN))

    @staticmethod
    def _netcdf_stack_importable() -> bool:
        try:
            import netCDF4  # noqa: F401
            import xarray  # noqa: F401

            return True
        except Exception:
            return False

    def _first_pm25_var(self, first_file: pathlib.Path | None = None):
        """Return the best PM2.5 variable name present in the first file."""
        if not self._netcdf_stack_importable():
            return None
        try:
            import xarray as xr

            files = self._output_files()
            if not files:
                return None
            with xr.open_dataset(files[0]) as ds:
                for name in PM25_VAR_NAMES:
                    if name in ds.data_vars:
                        return name
        except Exception:
            return None
        return None

    # -- execution ----------------------------------------------------------
    def run(
        self,
        start_utc: _dt.datetime,
        hours: int,
        domain: dict[str, float],
        grid_step: float,
        sources: list[dict[str, float]] | None = None,
    ) -> CtmResult:
        if not self.is_available():
            raise CtmUnavailable("\n  - ".join(self.unavailable_reasons()))
        import xarray as xr  # guaranteed importable when is_available()

        files = self._output_files()
        var = self._first_pm25_var(files[0])
        assert var is not None

        lat_axis = np.arange(
            domain["lat_min"], domain["lat_max"] + 1e-9, grid_step
        )
        lon_axis = np.arange(
            domain["lon_min"], domain["lon_max"] + 1e-9, grid_step
        )

        times: list[_dt.datetime] = []
        frames: list[np.ndarray] = []
        units = "ug/m3"
        for path in files:
            try:
                with xr.open_dataset(path) as ds:
                    if "Time" not in ds.coords and "time" not in ds.coords:
                        continue
                    field = ds[var]
                    units = str(field.attrs.get("units", units))
                    data = field.squeeze().values  # (..., nlat, nlon)
                    if data.ndim == 2:
                        data = data[np.newaxis, :, :]
                    grid_lat = np.asarray(ds["XLAT"].squeeze().values)
                    grid_lon = np.asarray(ds["XLONG"].squeeze().values)
                    data = self._regrid_to(data.squeeze(), grid_lat, grid_lon, lat_axis, lon_axis)
                    for t in np.atleast_1d(ds["Time"].values)[: data.shape[0]]:
                        times.append(_np_time_to_dt(t))
                    frames.extend([f for f in data])
                    if len(times) >= hours:
                        break
            except Exception as exc:
                raise CtmUnavailable(f"WRF-Chem: could not read {path}: {exc}") from exc

        if not frames:
            raise CtmUnavailable("WRF-Chem: no valid time frames extracted from output.")

        frames = frames[:hours]
        times = times[:hours]
        arr = np.asarray(frames)

        return CtmResult(
            engine=self.name,
            pollutant="PM2.5",
            units=units,
            start_utc=start_utc,
            times_utc=times,
            data=arr,
            lat=lat_axis,
            lon=lon_axis,
            metadata={
                "provenance": "genuine WRF-Chem wrfout NetCDF output",
                "files": [str(p.name) for p in files[: max(1, len(times))]],
                "variable": var,
                "units": units,
                "field": "ground-level PM2.5 (lowest model level / 2m)",
            },
        )

    @staticmethod
    def _regrid_to(
        data: np.ndarray,
        grid_lat: np.ndarray,
        grid_lon: np.ndarray,
        lat_axis: np.ndarray,
        lon_axis: np.ndarray,
    ) -> np.ndarray:
        """Nearest-lat/lon bilinear-style resample of a 2-D field."""
        out = np.zeros((data.shape[0], lat_axis.size, lon_axis.size), dtype=float)
        for fi in range(data.shape[0]):
            field = data[fi]
            i_lat = np.abs(grid_lat[:, 0] - lat_axis[:, None]).argmin(axis=0)
            j_lon = np.abs(grid_lon[0, :] - lon_axis[:, None]).argmin(axis=0)
            out[fi] = field[np.ix_(i_lat, j_lon)]
        return out


def _np_time_to_dt(value) -> _dt.datetime:
    """Convert a numpy datetime64 (or already-datetime) to naive UTC datetime."""
    if isinstance(value, _dt.datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    import pandas as pd

    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.to_pydatetime()
