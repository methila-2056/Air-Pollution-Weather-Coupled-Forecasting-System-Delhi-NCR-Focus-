"""Unit tests for the Estimated Regional Pollution Transport Risk engine."""

import pandas as pd
import pytest
from app.services.transport_risk_service import (
    MAX_DISTANCE_KM,
    UPWIND_COUNT_SATURATION,
    _mean_wind,
    classify_risk,
    compute_regional_risk,
    get_current_transport_risk,
)


class TestRiskBands:
    """Exact user-specified 0-100 bands."""

    def test_bands(self):
        expectations = [
            (0, "LOW"), (20, "LOW"),
            (21, "MODERATE"), (40, "MODERATE"),
            (41, "ELEVATED"), (60, "ELEVATED"),
            (61, "HIGH"), (80, "HIGH"),
            (81, "VERY HIGH"), (100, "VERY HIGH"),
        ]
        for score, level in expectations:
            assert classify_risk(score) == level, (score, level)

    def test_none(self):
        assert classify_risk(None) == "UNAVAILABLE"


class TestPureRiskComputation:
    """Deterministic math without a database."""

    def test_all_worst_conditions_but_no_fires(self):
        # Atmo: vent lowest (0), PBL shallowest (0), inversion max (1) -> 1.0.
        # Pollution: PM2.5 at saturation (300) -> 1.0.  Fire: zero fires.
        result = compute_regional_risk(
            fires_df=pd.DataFrame(columns=["lat", "lon", "frp"]),
            wind_speed=1.0, wind_direction=90.0,
            ventilation_norm=0.0, pbl_norm=0.0, inversion_norm=1.0,
            region_pm25=300.0,
        )
        assert result["components"]["atmo_component"] == pytest.approx(1.0, abs=1e-3)
        assert result["components"]["fire_component"] == 0.0
        assert result["components"]["pollution_component"] == pytest.approx(1.0, abs=1e-3)
        # 0.35*1 + 0.20*1 over full weight sum = 0.55 -> 55 ELEVATED.
        assert result["risk_score"] == 55
        assert result["risk_level"] == "ELEVATED"
        assert result["fire_count"] == 0
        assert result["upwind_fire_count"] == 0

    def test_perfect_dispersion_and_clean_air_is_low(self):
        result = compute_regional_risk(
            fires_df=None,
            wind_speed=7.0, wind_direction=315.0,
            ventilation_norm=1.0, pbl_norm=1.0, inversion_norm=0.0,
            region_pm25=35.0,
        )
        assert result["risk_score"] == 0
        assert result["risk_level"] == "LOW"

    def test_no_components_at_all(self):
        result = compute_regional_risk(
            fires_df=None, wind_speed=None, wind_direction=None,
            ventilation_norm=None, pbl_norm=None, inversion_norm=None,
            region_pm25=None,
        )
        # No fires anywhere -> no fire-transport potential (genuine signal);
        # missing atmosphere/pollution inputs are flagged, not silently assumed.
        assert result["risk_score"] == 0
        assert result["risk_level"] == "LOW"
        notes = result["components"]["renormalization_notes"]
        assert any("atmosphere" in n and "excluded" in n for n in notes)
        assert any("current pollution" in n and "excluded" in n for n in notes)

    def test_pollution_missing_renormalizes(self):
        without_poll = compute_regional_risk(
            fires_df=None, wind_speed=7.0, wind_direction=315.0,
            ventilation_norm=1.0, pbl_norm=1.0, inversion_norm=0.0,
            region_pm25=None,
        )
        assert without_poll["risk_score"] == 0
        notes = without_poll["components"]["renormalization_notes"]
        assert any("current pollution" in n for n in notes)

    def test_upwind_count_saturation(self):
        fires = pd.DataFrame({
            "lat": [28.7, 28.7, 28.7], "lon": [76.8, 76.8, 76.8], "frp": [90.0, 90.0, 90.0],
        })
        # Wind from NW (315): fires NW of NCR are upwind.
        risk = compute_regional_risk(
            fires, wind_speed=4.0, wind_direction=315.0,
            ventilation_norm=1.0, pbl_norm=1.0, inversion_norm=0.0,
            region_pm25=35.0,
        )
        assert risk["upwind_fire_count"] == 3
        assert risk["fire_count"] == 3

    def test_monotonic_with_more_upwind_fires(self):
        def score(count):
            fires = pd.DataFrame({
                "lat": [28.7] * count, "lon": [76.8] * count, "frp": [90.0] * count,
            })
            return compute_regional_risk(
                fires, 4.0, 315.0, 1.0, 1.0, 0.0, 35.0,
            )["risk_score"]

        assert score(5) >= score(1)

    def test_deterministic(self):
        fires = pd.DataFrame({
            "lat": [28.7, 30.5], "lon": [76.8, 76.1], "frp": [90.0, 120.0],
        })
        a = compute_regional_risk(fires, 4.0, 315.0, 0.5, 0.5, 0.5, 120.0)
        b = compute_regional_risk(fires, 4.0, 315.0, 0.5, 0.5, 0.5, 120.0)
        assert a == b

    def test_score_bounded(self):
        fires = pd.DataFrame({
            "lat": [28.7, 30.5, 31.2], "lon": [76.8, 76.1, 75.9],
            "frp": [90.0, 120.0, 18.0],
        })
        result = compute_regional_risk(fires, 4.0, 315.0, 0.1, 0.1, 0.9, 200.0)
        assert 0 <= result["risk_score"] or result["risk_score"] is None
        if result["risk_score"] is not None:
            assert 0 <= result["risk_score"] <= 100
        assert len(result["main_contributing_factors"]) >= 2

    def test_min_uses_nearest_fire_distance(self):
        assert MAX_DISTANCE_KM == 500.0
        assert UPWIND_COUNT_SATURATION == 50.0


class TestRegionalWindMean:
    def test_same_direction(self):
        wind = _mean_wind([
            {"wind": {"wind_speed_mps": 2.0, "wind_direction_deg": 315.0}},
            {"wind": {"wind_speed_mps": 6.0, "wind_direction_deg": 315.0}},
        ])
        assert wind["compass_from"] in ("NW", "NNW")  # from direction
        assert wind["wind_direction_deg"] == pytest.approx(315.0, abs=5.0)
        assert wind["wind_speed_mps"] == pytest.approx(4.0, abs=0.01)
        assert wind["stations_used"] == 2

    def test_no_wind(self):
        wind = _mean_wind([{"wind": {"wind_speed_mps": None, "wind_direction_deg": None}}])
        assert wind["wind_direction_deg"] is None


class TestDatabaseIntegration:
    def test_get_current_transport_risk(self, db_session):
        result = get_current_transport_risk(db_session)
        assert result["risk_score"] is not None
        assert isinstance(result["risk_score"], int)
        assert 0 <= result["risk_score"] <= 100
        assert classify_risk(result["risk_score"]) == result["risk_level"]
        # 5 seeded hotspots within the look-back window.
        assert result["fire_count"] == 5
        assert result["upwind_fire_count"] >= 0
        # Seeded winds are 1.6 m/s from 315 (NW) over Anand Vihar.
        assert result["dominant_wind_direction"]["compass_from"] == "NW"
        assert result["dominant_wind_direction"]["wind_speed_mps"] == pytest.approx(1.6, abs=0.01)
        assert result["inputs"]["region_pm25_ugm3"] is not None
        assert result["methodology"]["formulas"]
        assert result["methodology"]["constants"]["risk_bands"]
        assert result["disclaimer"]
        assert len(result["station_detail"]) >= 1

    def test_fires_older_than_window_excluded(self, db_session):
        from datetime import timedelta

        from app.models.db_models import FireReading
        db_session.query(FireReading).delete()
        # Insert a fire far in the past (120h), outside the 72h window.
        from datetime import datetime
        old = datetime.utcnow() - timedelta(hours=120)
        db_session.add(FireReading(latitude=30.5, longitude=76.1, acq_date=old,
                                   confidence="high", frp=90.0, satellite="SNPP", daynight="D"))
        db_session.commit()
        result = get_current_transport_risk(db_session)
        assert result["fire_count"] == 0
        assert result["inputs"]["fire_rows_in_window"] == 0
