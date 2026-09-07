"""Unit tests for the numerical dispersion transport core (SIH26082 PS #3)."""

import numpy as np
import pytest

from ml.features.dispersion_solver import (
    DispersionSolver,
    aqi_to_conc,
    build_wind_fields,
    conc_to_aqi,
    run_dispersion_forecast,
)

LAT0, LAT1, LON0, LON1, STEP = 28.2, 28.9, 76.6, 77.5, 0.02


def _uniform_aqi(value: int = 120) -> np.ndarray:
    nl = int(round((LAT1 - LAT0) / STEP)) + 1
    nlon = int(round((LON1 - LON0) / STEP)) + 1
    return np.full((nl, nlon), value, dtype=float)


class TestConcAqiRoundTrip:
    def test_breakpoints_map_correctly(self):
        assert conc_to_aqi(np.array([0.0]))[0] == 0
        assert conc_to_aqi(np.array([30.0]))[0] == 50
        assert conc_to_aqi(np.array([60.0]))[0] == 100

    def test_aqi_to_conc_inverts(self):
        assert aqi_to_conc(np.array([50.0]))[0] == pytest.approx(30.0, abs=0.01)
        assert aqi_to_conc(np.array([400.0]))[0] == pytest.approx(250.0, abs=0.01)

    def test_round_trip_conserves_aqi_value(self):
        aqi_in = np.array([12.0, 88.0, 150.0, 340.0])
        conc = aqi_to_conc(aqi_in)
        aqi_out = conc_to_aqi(conc)
        np.testing.assert_allclose(aqi_out, aqi_in, atol=1)

    def test_negative_conc_clamped_to_zero(self):
        assert conc_to_aqi(np.array([-5.0]))[0] == 0


class TestAdvection:
    def test_peak_advects_downwind_with_west_wind(self):
        solver = DispersionSolver(LAT0, LAT1, LON0, LON1, STEP)
        center = np.zeros(solver.C.shape)
        ci, cj = solver.nlat // 2, 3
        center[ci, cj] = 1.0
        solver.set_background(center + 0.0)

        u_field, v_field = build_wind_fields(2.0, 90.0, solver.nlat, solver.nlon)
        for _ in range(20):
            solver.advance(u_field, v_field, pbl_height=900.0, dt=100.0,
                           emission_active=False, coupled=False)

        mass_cols = solver.C.sum(axis=0)
        old_cols = center.sum(axis=0)
        new_cog = float(np.sum(np.arange(solver.nlon) * mass_cols) / max(1e-9, mass_cols.sum()))
        old_cog = float(np.sum(np.arange(solver.nlon) * old_cols) / max(1e-9, old_cols.sum()))
        assert new_cog > old_cog, "plume should drift eastward under a westerly wind"

    def test_constant_field_stays_nearly_constant_without_emissions(self):
        solver = DispersionSolver(LAT0, LAT1, LON0, LON1, STEP)
        init = np.full(solver.C.shape, 80.0)
        solver.set_background(init)

        u_field, v_field = build_wind_fields(1.0, 180.0, solver.nlat, solver.nlon)
        for _ in range(10):
            solver.advance(u_field, v_field, pbl_height=900.0, dt=100.0,
                           emission_active=False, coupled=False)

        # exact conservation is broken only by tiny boundary-face rounding
        assert float(np.nanmax(solver.C)) - float(np.nanmin(solver.C)) < 1.0
        assert float(np.mean(solver.C)) == pytest.approx(80.0, abs=0.5)


class TestDepositionAndEmissions:
    def test_rain_removes_mass(self):
        solver = DispersionSolver(LAT0, LAT1, LON0, LON1, STEP)
        solver.set_background(np.full(solver.C.shape, 100.0))
        before = solver.C.sum()

        solver.advance(*build_wind_fields(0.0, 0.0, solver.nlat, solver.nlon),
                       pbl_height=900.0, precip_mm=8.0, dt=300.0,
                       emission_active=False, coupled=False)
        assert solver.C.sum() < before

    def test_urban_emission_increases_domain_mean(self):
        solver = DispersionSolver(LAT0, LAT1, LON0, LON1, STEP)
        solver.set_background(np.full(solver.C.shape, 10.0))
        solver.add_areal_emission(28.40, 28.75, 76.90, 77.35, 3.0e-3)
        before = float(np.mean(solver.C))
        for _ in range(4):
            solver.advance(*build_wind_fields(0.0, 0.0, solver.nlat, solver.nlon),
                           pbl_height=900.0, dt=300.0, coupled=False)
        assert float(np.mean(solver.C)) > before

    def test_dry_deposition_stronger_in_shallow_pbl(self):
        solver = DispersionSolver(LAT0, LAT1, LON0, LON1, STEP)
        shallow = solver.dry_deposition(200.0)[0, 0]
        deep = solver.dry_deposition(1200.0)[0, 0]
        assert shallow > deep

    def test_wet_removal_zero_for_clear_skies(self):
        solver = DispersionSolver(LAT0, LAT1, LON0, LON1, STEP)
        assert solver.wet_removal(0.0).sum() == 0.0
        assert solver.wet_removal(5.0)[0, 0] > 0.0


class TestCouplingDiag:
    def test_advance_records_coupling_diagnostics(self):
        solver = DispersionSolver(LAT0, LAT1, LON0, LON1, STEP)
        solver.set_background(np.full(solver.C.shape, 60.0))
        solver.advance(*build_wind_fields(3.0, 45.0, solver.nlat, solver.nlon),
                       pbl_height=700.0, dt=300.0, hour=4, wind_speed=3.0)
        assert 0.0 <= solver.coupling_diag["stability_coupling_index"] <= 1.0
        assert solver.coupling_diag["corrected_pbl_height"] > 0.0
        assert solver.coupling_diag["mean_pm25"] > 0.0

    def test_night_is_more_stable_than_noon(self):
        from ml.features.coupling import boundary_stability_index
        night = boundary_stability_index(pm25=120.0, pbl_height=600.0, wind_speed=3.0, hour=3)
        day = boundary_stability_index(pm25=120.0, pbl_height=600.0, wind_speed=3.0, hour=13)
        assert night >= day


class TestRunForecast:
    def test_returns_requested_hours(self):
        result = run_dispersion_forecast(
            _uniform_aqi(150), LAT0, LAT1, LON0, LON1, STEP,
            wind_speed=2.0, wind_dir_deg=90.0, pbl_height=800.0,
            hours=24, urban_emission=1.0e-3,
        )
        assert len(result["frames"]) == 24
        assert [f["hour"] for f in result["frames"]] == list(range(1, 25))

    def test_fields_nonnegative(self):
        fires = [{"lat": 30.0, "lon": 76.0, "frp": 100.0},
                 {"lat": 29.5, "lon": 76.5, "frp": 220.0}]
        result = run_dispersion_forecast(
            _uniform_aqi(90), LAT0, LAT1, LON0, LON1, STEP,
            wind_speed=2.0, wind_dir_deg=45.0, pbl_height=800.0,
            fires=fires, hours=48, urban_emission=1.0e-3,
            wind_hourly=[2.0] * 48, pbl_hourly=[800.0] * 48,
            precip_hourly=[0.0] * 48, dir_hourly=[45.0] * 48,
        )
        last = result["frames"][-1]
        assert float(last["concentration"].min()) >= 0.0
        assert float(last["aqi"].min()) >= 0.0
        assert last["aqi"].max() <= 500

    def test_hourly_met_series_override_scalar(self):
        result = run_dispersion_forecast(
            _uniform_aqi(100), LAT0, LAT1, LON0, LON1, STEP,
            wind_speed=3.0, wind_dir_deg=0.0, pbl_height=900.0,
            hours=12, urban_emission=0.0, dt=600.0,
            wind_hourly=[1.0] * 12,
        )
        assert result["frames"][0]["wind_speed"] == pytest.approx(1.0)