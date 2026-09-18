"""Unit tests for the gated ERA5 reanalysis surface reader (WS-2).

The reader must never fabricate data: with no real CDS NetCDF present it
returns an empty frame and ``era5_reasons`` explains exactly what is missing.
Synthetic CDS-style NetCDF3 files (as emitted by the Copernicus CDS via scipy)
exercise the nearest-grid-cell sampling and unit conversions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.io import netcdf_file

from ml.features.era5_surface import (
    FEATURE_COLUMNS,
    STATION_COORDS,
    era5_reasons,
    is_available,
    load_era5_csv,
    load_era5_surface,
)


def _write_cds_nc(
    path,
    *,
    latitudes=(28.0, 28.3, 28.6, 28.9),
    longitudes=(77.0, 77.2, 77.4, 77.6),
    ntime=2,
    t_offset_hours=0.0,
    blh=None,
    t2m=None,
    sp=None,
    t2m_shape="3d",
):
    lat = np.asarray(latitudes, dtype=np.float32)
    lon = np.asarray(longitudes, dtype=np.float32)
    if t2m is None:
        t2m = np.full((ntime, lat.size, lon.size), 288.15, dtype=np.float32)
    if t2m.ndim < 3:  # allow per-cell patterns
        t2m = np.tile(t2m[np.newaxis, :, :], (ntime, 1, 1))
    if blh is None:
        blh = np.full((ntime, lat.size, lon.size), 500.0, dtype=np.float32)
    if sp is None:
        sp = np.full((ntime, lat.size, lon.size), 98123.0, dtype=np.float32)

    with netcdf_file(str(path), "w") as f:
        f.createDimension("latitude", lat.size)
        f.createDimension("longitude", lon.size)
        f.createDimension("time", ntime)
        vlat = f.createVariable("latitude", "f", ("latitude",))
        vlat[:] = lat
        vlat.units = "degrees_north"
        vlon = f.createVariable("longitude", "f", ("longitude",))
        vlon[:] = lon
        vlon.units = "degrees_east"
        vtime = f.createVariable("time", "d", ("time",))
        vtime[:] = np.arange(ntime, dtype=float) * 6.0 + t_offset_hours
        vtime.units = "hours since 1900-01-01 00:00:00.0"
        dims = ("time", "latitude", "longitude")
        if t2m_shape == "expver":
            f.createDimension("expver", 2)
            dims = ("expver", "time", "latitude", "longitude")
            t2m = np.stack([t2m - 5.0, t2m])
            blh = np.stack([blh - 10.0, blh])
            sp = np.stack([sp - 100.0, sp])
        bt = f.createVariable("t2m", "f", dims)
        bt[:] = t2m
        bh = f.createVariable("blh", "f", dims)
        bh[:] = blh
        bs = f.createVariable("sp", "f", dims)
        bs[:] = sp
    return path


def test_missing_file_reports_honest_reasons(tmp_path):
    missing = tmp_path / "era5_atmosphere.nc"
    reasons = era5_reasons(missing)
    assert reasons, "expected at least one reason for a missing ERA5 file"
    assert "not found" in reasons[0]
    assert is_available(missing) is False
    assert load_era5_surface(missing).empty
    assert load_era5_surface(tmp_path / "nope").empty


def test_glob_multi_year_files(tmp_path):
    _write_cds_nc(tmp_path / "era5_atmosphere_2023.nc", ntime=1)
    _write_cds_nc(tmp_path / "era5_atmosphere_2024.nc", ntime=1, t_offset_hours=8760)
    df = load_era5_surface(tmp_path / "era5_atmosphere.nc")
    assert not df.empty
    assert len(df) == 2 * len(STATION_COORDS)
    assert df["time"].nunique() == 2  # both archive years sampled
    assert sorted(df["station"].unique()) == sorted(STATION_COORDS)


def test_nearest_cell_sampling_and_units(tmp_path):
    nc = tmp_path / "era5_atmosphere.nc"
    lat = np.array([28.0, 28.3, 28.6, 28.9], dtype=np.float32)
    lon = np.array([77.0, 77.2, 77.4, 77.6], dtype=np.float32)
    pattern = np.array(
        [[(i * 1000 + j) for j in range(len(lon))] for i in range(len(lat))],
        dtype=np.float32,
    )
    _write_cds_nc(
        nc, latitudes=lat, longitudes=lon, ntime=1,
        t2m=pattern + 273.15, blh=pattern, sp=pattern * 100.0,
    )

    df = load_era5_surface(nc)
    assert list(df.columns) == FEATURE_COLUMNS
    av = df[df["station"] == "Anand_Vihar"].iloc[0]
    # Anand_Vihar (28.6492, 77.2918) -> nearest cell (28.6, 77.2) == (i=2, j=1)
    # float32 storage introduces ~1e-3 rounding, so tolerate abs=0.05.
    assert av["era5_temperature"] == pytest.approx(2274.15 - 273.15, abs=0.05)
    assert av["era5_blh"] == pytest.approx(2001.0, abs=0.05)
    assert av["era5_surface_pressure"] == pytest.approx(200100.0 / 100.0, abs=0.05)
    assert str(av["time"]).startswith("1900-01-01")


def test_latitude_descending_order(tmp_path):
    nc = tmp_path / "era5_atmosphere.nc"
    _write_cds_nc(nc, latitudes=(28.9, 28.6, 28.4, 28.0), ntime=1)
    df = load_era5_surface(nc)
    assert len(df) == len(STATION_COORDS)
    assert not df[df["station"] == "Anand_Vihar"].empty


def test_expver_dimension_takes_last(tmp_path):
    nc = tmp_path / "era5_atmosphere.nc"
    _write_cds_nc(nc, ntime=1, t2m_shape="expver")
    df = load_era5_surface(nc)
    assert len(df) == len(STATION_COORDS)
    av = df[df["station"] == "Anand_Vihar"].iloc[0]
    # last expver carries the unshifted value -> K -> C
    assert av["era5_temperature"] == pytest.approx(288.15 - 273.15)
    assert av["era5_blh"] == pytest.approx(500.0)


def test_csv_placeholder_is_empty_and_real_csv_loads(tmp_path):
    empty = tmp_path / "era5_atmosphere.csv"
    pd.DataFrame(columns=FEATURE_COLUMNS).to_csv(empty, index=False)
    assert load_era5_csv(empty).empty

    real = tmp_path / "real.csv"
    rows = pd.DataFrame({
        "time": [pd.Timestamp("2023-01-01 00:00")] * 2,
        "station": ["Anand_Vihar", "Somewhere_Else"],
        "era5_temperature": [15.0, 20.0],
        "era5_surface_pressure": [981.23, 1000.0],
        "era5_blh": [500.0, 600.0],
    })
    rows.to_csv(real, index=False)
    df = load_era5_csv(real)
    assert list(df["station"]) == ["Anand_Vihar"]  # unknown stations filtered


def test_build_dataset_glue_prefers_csv(tmp_path, capsys):
    nc = tmp_path / "era5_atmosphere.nc"
    csv = tmp_path / "era5_atmosphere.csv"
    _write_cds_nc(nc, ntime=1)
    pd.DataFrame({
        "time": ["2023-01-01 00:00:00"],
        "station": ["Anand_Vihar"],
        "era5_temperature": [16.0],
        "era5_surface_pressure": [985.0],
        "era5_blh": [420.0],
    }).to_csv(csv, index=False)

    from scripts.build_dataset import load_atmosphere

    df = load_atmosphere(tmp_path)
    assert not df.empty
    assert "2023-01-01" in str(df["time"].iloc[0])
    assert "unavailable" not in capsys.readouterr().out


def test_build_dataset_glue_warns_when_absent(tmp_path, capsys):
    from scripts.build_dataset import load_atmosphere

    df = load_atmosphere(tmp_path)
    assert df.empty
    assert "ERA5 atmosphere unavailable" in capsys.readouterr().out
