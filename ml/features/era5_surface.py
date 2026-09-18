"""Gated reader for genuine ERA5 single-level reanalysis over Delhi NCR (WS-2).

The offline feature pipeline can absorb real Copernicus-CDS ERA5 reanalysis for
the NCR stations:

- ``scripts/download_atmosphere.py`` fetches ``reanalysis-era5-single-levels``
  (``2m_temperature``, ``surface_pressure``, ``boundary_layer_height``) and
  writes CDS NetCDF files under ``data/atmosphere/era5_atmosphere_*.nc``.
- This module samples those grids at the 17 curated NCR stations (nearest grid
  cell), converts to the familiar units, and returns per-station, per-hour
  rows::

      time, station, era5_temperature (degC), era5_surface_pressure (hPa),
      era5_blh (m)

- ``scripts/build_dataset.py`` merges these columns into the coupled dataset.

Honesty contract:

- ``era5_reasons(path)`` / ``is_available(path)`` report exactly what is
  missing (no NetCDF file, no reader backend, ...); nothing synthetic is ever
  produced — an absent file yields an empty frame, and the pipeline keeps using
  Open-Meteo weather.
- The reader prefers ``netCDF4`` > ``xarray`` > ``scipy.io.netcdf_file`` (the
  latter reads the NetCDF3-classic files CDS emits with **zero extra
  dependencies**).
"""

from __future__ import annotations

import datetime as _dt
import os
import pathlib
import re
from collections.abc import Mapping
from typing import Any

import pandas as pd

# CDS short variable name -> AeroCast-NCR feature column.
VAR_MAP = {
    "blh": "era5_blh",
    "t2m": "era5_temperature",
    "sp": "era5_surface_pressure",
}
FEATURE_COLUMNS = ["time", "station", "era5_temperature", "era5_surface_pressure", "era5_blh"]

# Canonical 17-station NCR set (same coordinates as scripts/download_weather.py).
STATION_COORDS: dict[str, tuple[float, float]] = {
    "Anand_Vihar": (28.6492, 77.2918),
    "RK_Puram": (28.5601, 77.1835),
    "ITO": (28.6290, 77.2410),
    "Dwarka": (28.5921, 77.0460),
    "Punjabi_Bagh": (28.6692, 77.1285),
    "Lodhi_Road": (28.5866, 77.2268),
    "Sirifort": (28.5528, 77.2190),
    "Shadipur": (28.6542, 77.1489),
    "Okhla_Phase-2": (28.5230, 77.2680),
    "Ashok_Vihar": (28.6974, 77.1756),
    "Mundka": (28.6796, 77.0189),
    "Jahangirpuri": (28.7256, 77.1556),
    "Aya_Nagar": (28.4771, 77.1148),
    "Vivek_Vihar": (28.6727, 77.3169),
    "Teri_Gram": (28.4422, 77.0115),
    "Noida_Sector-62": (28.6227, 77.3615),
    "Faridabad": (28.4089, 77.3178),
}

_TIME_UNIT_RE = re.compile(
    r"(?P<unit>hours|days|seconds|minutes) since"
    r"\s*(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:[ T](?P<hour>\d{1,2}):(?P<minute>\d{1,2})(?::(?P<second>\d{1,2}))?)?"
)


def _backend() -> str | None:
    try:
        import netCDF4  # noqa: F401
        return "netCDF4"
    except Exception:
        pass
    try:
        import xarray  # noqa: F401
        return "xarray"
    except Exception:
        pass
    try:
        from scipy.io import netcdf_file  # noqa: F401
        return "scipy"
    except Exception:
        return None


def era5_reasons(path: str | os.PathLike | None) -> list[str]:
    """Human-readable reasons why real ERA5 is not currently consumed."""
    reasons: list[str] = []
    if path is None:
        reasons.append("no Data/atmosphere era5 NetCDF path configured")
        return reasons
    p = pathlib.Path(path)
    candidates = sorted(p.parent.glob(p.stem + "_*" + p.suffix)) if p.suffix == ".nc" else []
    if not p.exists() and not any(x.exists() for x in candidates):
        reasons.append(
            f"{p} not found — run scripts/download_atmosphere.py (needs a free "
            "Copernicus CDS account) or place real era5_atmosphere_*.nc files"
        )
    if _backend() is None:
        reasons.append(
            "no NetCDF reader backend (install netCDF4 or xarray, or ensure scipy "
            "is present for NetCDF3-classic CDS files)"
        )
    return reasons


def is_available(path: str | os.PathLike) -> bool:
    return not era5_reasons(path)


def _decode_time(values: Any, units: str) -> pd.Series:
    """Convert CDS time values (e.g. ``hours since 1900-01-01 00:00:00.0``)."""
    if isinstance(units, bytes):
        units = units.decode("ascii", errors="replace")
    m = _TIME_UNIT_RE.match(units or "")
    if not m:
        return pd.Series([pd.NaT] * len(values), dtype="datetime64[ns]")
    delta = {
        "hours": _dt.timedelta(hours=1),
        "days": _dt.timedelta(days=1),
        "minutes": _dt.timedelta(minutes=1),
        "seconds": _dt.timedelta(seconds=1),
    }[m.group("unit")]
    origin = _dt.datetime(
        int(m.group("year")), int(m.group("month")), int(m.group("day")),
        int(m.group("hour") or 0), int(m.group("minute") or 0),
        int(m.group("second") or 0),
    )
    out = [origin + delta * float(v) for v in values]
    return pd.Series(out)


def _read_grid(path: pathlib.Path) -> dict[str, Any]:
    """Load lat/lon/time and the three fields from a CDS-era5 NetCDF file."""
    backend = _backend()
    if backend == "netCDF4":
        import netCDF4

        def get(name):
            with netCDF4.Dataset(str(path)) as ds:
                return {k: ds.variables[k][:] for k in name}

        arrays = get(["latitude", "longitude", "time", "blh", "t2m", "sp"])
        units_t = get(["time"])["time"]
        units_t = units_t.units if hasattr(units_t, "units") else "hours since 1900-01-01 00:00:00.0"
        arrays["time"] = _decode_time(arrays["time"], str(units_t))
        return arrays
    if backend == "xarray":
        import xarray as xr

        with xr.open_dataset(path) as ds:
            arrays = {
                "latitude": ds["latitude"].values,
                "longitude": ds["longitude"].values,
                "time": pd.to_datetime(ds["time"].values),
                "blh": ds["blh"].values,
                "t2m": ds["t2m"].values,
                "sp": ds["sp"].values,
            }
        return arrays
    from scipy.io import netcdf_file

    with netcdf_file(str(path), mmap=False) as f:
        units_attr = getattr(f.variables["time"], "units", "")
        if isinstance(units_attr, bytes):
            units_attr = units_attr.decode("ascii", errors="replace")
        arrays = {
            "latitude": f.variables["latitude"][:].copy(),
            "longitude": f.variables["longitude"][:].copy(),
            "time": _decode_time(f.variables["time"][:].copy(), units_attr),
            "blh": f.variables["blh"][:].copy(),
            "t2m": f.variables["t2m"][:].copy(),
            "sp": f.variables["sp"][:].copy(),
        }
    return arrays


def _sample_station(field: Any, axis_i: int, axis_j: int) -> Any:
    arr = field
    if arr.ndim >= 4:
        arr = arr[..., -1, :, :, :] if arr.ndim == 5 else arr[-1, ...]
    if arr.ndim == 3:  # (time, nlat, nlon)
        return arr[:, axis_i, axis_j]
    raise ValueError(f"unsupported ERA5 field rank {arr.ndim}")


def load_era5_surface(
    path: str | os.PathLike,
    stations: Mapping[str, tuple[float, float]] | None = None,
    suffix: str = "*",
) -> pd.DataFrame:
    """Return per-station-hour ERA5 surface rows, or an empty frame when absent.

    Falls back to ``load_era5_csv`` semantics for real files already extracted
    to CSV (column names identical).
    """
    p = pathlib.Path(path)
    stations = stations or STATION_COORDS
    if not p.exists():
        matches = sorted(p.parent.glob(p.stem + suffix + p.suffix)) if suffix else []
        if not matches:
            return pd.DataFrame()
        frames = [load_era5_surface(m, stations=stations, suffix="") for m in matches]
        out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return out.sort_values(["time", "station"]).reset_index(drop=True) if len(out) else out

    if p.suffix.lower() == ".csv":
        return load_era5_csv(p, stations=stations)
    try:
        grid = _read_grid(p)
    except (AttributeError, KeyError, OSError, IndexError, ValueError):
        return pd.DataFrame()

    lat = grid["latitude"]
    lon = grid["longitude"]
    time_vals = grid["time"]
    rows: list[dict[str, Any]] = []
    for name, (slat, slon) in stations.items():
        i = int(abs(lat - slat).argmin())
        j = int(abs(lon - slon).argmin())
        blh = _sample_station(grid["blh"], i, j)
        t2m = _sample_station(grid["t2m"], i, j)
        sp = _sample_station(grid["sp"], i, j)
        for t, b, t2, s in zip(time_vals, blh, t2m, sp, strict=True):
            rows.append({
                "time": pd.Timestamp(t).to_pydatetime() if isinstance(t, _dt.datetime) else t,
                "station": name,
                "era5_temperature": float(t2) - 273.15,  # K -> degC
                "era5_surface_pressure": float(s) / 100.0,  # Pa -> hPa
                "era5_blh": float(b),
            })
    out = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    return out.sort_values(["time", "station"]).reset_index(drop=True)


def load_era5_csv(
    path: str | os.PathLike,
    stations: Mapping[str, tuple[float, float]] | None = None,
) -> pd.DataFrame:
    """Read an already-extracted era5 station CSV (or filter to known stations)."""
    stations = stations or STATION_COORDS
    try:
        df = pd.read_csv(path, parse_dates=["time"])
    except Exception:
        return pd.DataFrame()
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing or df.empty:
        return pd.DataFrame()
    df = df[df["station"].isin(stations)] if "station" in df.columns else df
    return df.sort_values(["time", "station"]).reset_index(drop=True)
