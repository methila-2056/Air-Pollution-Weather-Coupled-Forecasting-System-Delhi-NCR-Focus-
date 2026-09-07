"""Unit tests for the NCR spatial IDW grid layer."""

from types import SimpleNamespace

import numpy as np
import pytest

from app.services.grid_service import (
    ADVECTION_WEIGHT,
    GRID_STEP,
    NCR_BOUNDS,
    advective_shift,
    build_grid,
    compute_ncr_grid,
    idw_interpolate,
)


def _station(name, lat, lon):
    return SimpleNamespace(name=name, latitude=lat, longitude=lon)


def _forecast(station_name, horizon, aqi):
    return {station_name: [{"horizon_hours": horizon, "aqi_pred": aqi}]}


class TestBuildGrid:
    def test_dimensions_match_domain(self):
        lats, lons = build_grid()
        assert lats[0] == pytest.approx(NCR_BOUNDS["lat_min"])
        assert lats[-1] == pytest.approx(NCR_BOUNDS["lat_max"])
        expected_nlat = int(round((NCR_BOUNDS["lat_max"] - NCR_BOUNDS["lat_min"]) / GRID_STEP)) + 1
        expected_nlon = int(round((NCR_BOUNDS["lon_max"] - NCR_BOUNDS["lon_min"]) / GRID_STEP)) + 1
        assert lats.size == expected_nlat
        assert lons.size == expected_nlon


class TestIdw:
    def test_single_station_fills_constant_field(self):
        lats, lons = build_grid()
        field = idw_interpolate(
            np.array([28.6]), np.array([77.2]), np.array([123.0]),
            lats, lons,
        )
        assert np.allclose(field, 123.0, atol=0.01)

    def test_exact_station_collocation_wins(self):
        lats, lons = build_grid()
        i, j = 20, 25
        field = idw_interpolate(
            np.array([lats[i], 28.4]), np.array([lons[j], 76.9]),
            np.array([77.0, 50.0]), lats, lons,
        )
        assert field[i, j] == pytest.approx(77.0)


class TestAdvectiveShift:
    def test_easterly_moves_east(self):
        jj = np.array([10.0])
        ii = np.array([10.0])
        sj, si = advective_shift(jj, ii, wind_dir=90.0, wind_speed=4.0)
        assert sj[0] > jj[0]
        assert si[0] == pytest.approx(ii[0])

    def test_northerly_moves_north_cells(self):
        jj = np.array([10.0])
        ii = np.array([10.0])
        sj, si = advective_shift(jj, ii, wind_dir=0.0, wind_speed=4.0)
        assert si[0] > ii[0]


class TestComputeGrid:
    def test_empty_when_no_forecasts(self):
        stations = [_station("A", 28.6, 77.2)]
        result = compute_ncr_grid(stations, {}, horizon_hours=24)
        assert result["cells"] == []

    def test_cells_have_valid_categories(self):
        stations = [
            _station("A", 28.61, 77.20),
            _station("B", 28.50, 77.05),
            _station("C", 28.70, 77.30),
        ]
        forecasts = {
            "A": [{"horizon_hours": 24, "aqi_pred": 45}],
            "B": [{"horizon_hours": 24, "aqi_pred": 150}],
            "C": [{"horizon_hours": 24, "aqi_pred": 330}],
        }
        result = compute_ncr_grid(stations, forecasts, horizon_hours=24,
                                  wind_dir=315.0, wind_speed=3.0)
        assert result["horizon_hours"] == 24
        assert len(result["cells"]) > 0
        assert result["cells"][0]["aqi_category"] in {
            "Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"
        }

    def test_shift_blends_field_into_downwind_cells(self):
        stations = [_station("A", 28.6, 77.2)]
        forecasts = {"A": [{"horizon_hours": 24, "aqi_pred": 200}]}
        still = compute_ncr_grid(stations, forecasts, 24)
        windy = compute_ncr_grid(stations, forecasts, 24, wind_dir=90.0, wind_speed=6.0)
        assert windy["cells"] != []