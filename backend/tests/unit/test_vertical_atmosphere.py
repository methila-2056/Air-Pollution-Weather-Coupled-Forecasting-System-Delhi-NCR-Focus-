"""Unit tests for vertical-atmosphere features (SIH26082).

Covers lapse-rate inversion from pressure-level temperatures, PBL
classification, and fire smoke transport features.
"""

import pandas as pd
import pytest

from ml.features.atmospheric_profile import (
    classify_gradient,
    classify_pbl,
    combine_inversion,
    compute_lapse_rates,
)
from ml.features.fire_impact import add_fire_features, compute_fire_impact
from ml.features.inversion import add_lapse_rate_inversion_features


class TestComputeLapseRates:
    def test_normal_lapse_is_negative(self):
        # Temperature decreases with height: gradient negative -> no inversion.
        temps = {1000: 20.0, 925: 15.0, 850: 10.0, 700: 5.0}
        grades = compute_lapse_rates(temps)
        assert grades
        # 1000->925 layer: (15-20)/(1000-925)*100 = -6.67
        assert grades[(1000, 925)] == pytest.approx(-6.67, abs=0.02)
        assert all(g < 0 for g in grades.values())

    def test_inversion_layer_is_positive(self):
        temps = {1000: 12.0, 925: 10.0, 850: 14.0, 700: 8.0}
        grades = compute_lapse_rates(temps)
        # 925->850 layer: (14-10)/(925-850)*100 = +5.33 (inversion)
        assert grades[(925, 850)] > 0
        assert grades[(925, 850)] == pytest.approx(5.3333, abs=0.02)

    def test_missing_levels_return_empty(self):
        assert compute_lapse_rates({1000: 20.0}) == {}
        assert compute_lapse_rates(None) == {}
        assert compute_lapse_rates({}) == {}


class TestClassifyGradient:
    def test_strong_inversion(self):
        temps = {1000: 12.0, 925: 10.0, 850: 14.0, 700: 8.0}
        res = classify_gradient(compute_lapse_rates(temps))
        assert res["inversion_detected"] is True
        assert res["inversion_category"] == "strong"
        assert res["inversion_base_pressure"] == 925
        assert res["inversion_top_pressure"] == 850

    def test_normal_lapse_no_inversion(self):
        temps = {1000: 20.0, 925: 15.0, 850: 10.0}
        res = classify_gradient(compute_lapse_rates(temps))
        assert res["inversion_detected"] is False
        assert res["inversion_category"] == "none"

    def test_isothermal_is_not_inversion(self):
        res = classify_gradient(compute_lapse_rates({1000: 25.0, 925: 25.0}))
        assert res["inversion_category"] == "none"


class TestClassifyPbl:
    def test_trapped(self):
        r = classify_pbl(120.0)
        assert r["low_pbl_flag"] is True
        assert r["pbl_category"] == "strong_trapping"
        assert r["dispersion_condition"] == "TRAPPED"

    def test_good_dispersion(self):
        r = classify_pbl(1200.0)
        assert r["low_pbl_flag"] is False
        assert r["pbl_category"] == "good_dispersion"
        assert r["dispersion_condition"] == "GOOD"

    def test_unknown(self):
        r = classify_pbl(None)
        assert r["pbl_category"] == "unknown"
        assert r["dispersion_condition"] == "UNKNOWN"


class TestCombineInversion:
    def test_lapse_rate_wins_when_vertical_data_present(self):
        r = combine_inversion(250.0, {1000: 12.0, 925: 10.0, 850: 14.0, 700: 8.0})
        assert r["inversion_source"] == "lapse_rate"
        assert r["profile_available"] is True
        assert r["inversion_detected"] is True

    def test_pbl_proxy_fallback(self):
        r = combine_inversion(250.0, None)
        assert r["inversion_source"] == "pbl_proxy"
        assert r["profile_available"] is False
        # PBL 250m -> moderate trapping
        assert r["inversion_detected"] is True
        assert r["pbl_category"] == "moderate_trapping"


class TestAddLapseRateInversionFeatures:
    def test_columns_added_only_when_levels_present(self):
        df = pd.DataFrame({
            "pbl_height": [250.0, 1200.0],
            "temperature_1000hPa": [12.0, 25.0],
            "temperature_925hPa": [10.0, 22.0],
            "temperature_850hPa": [14.0, 20.0],
            "temperature_700hPa": [8.0, 10.0],
        })
        out = add_lapse_rate_inversion_features(df)
        assert "inversion_source" in out.columns
        assert out["inversion_source"].tolist() == ["lapse_rate", "lapse_rate"]

    def test_no_vertical_data_returns_pbl_proxy(self):
        df = pd.DataFrame({"pbl_height": [250.0]})
        out = add_lapse_rate_inversion_features(df)
        assert out["inversion_source"].tolist() == ["pbl_proxy"]


class TestFireTransport:
    STATION_LAT = 28.6139
    STATION_LON = 77.2090

    def _fires(self):
        return pd.DataFrame([
            {"lat": 29.2, "lon": 76.5, "frp": 40.0},  # NW ~100km, upwind for 315
            {"lat": 28.7, "lon": 77.6, "frp": 6.0},   # E  close, crosswind
        ])

    def test_transport_metrics_computed(self):
        r = compute_fire_impact(
            self._fires(), self.STATION_LAT, self.STATION_LON,
            wind_dir=315, wind_speed=3.0,
        )
        assert r["fire_count"] == 2
        assert r["wind_aligned_fire_count"] == 1
        assert r["wind_alignment_pct"] == 50.0
        assert r["transport_time_hours"] > 0
        assert 0.0 <= r["transport_risk"] <= 1.0
        assert r["transport_risk_level"] in {"low", "moderate", "high", "severe"}
        assert 0.0 <= r["stubble_impact_score"] <= 1.0

    def test_no_fires_returns_defaults(self):
        r = compute_fire_impact(
            pd.DataFrame(), self.STATION_LAT, self.STATION_LON,
            wind_dir=315, wind_speed=3.0,
        )
        assert r["fire_count"] == 0
        assert r["transport_risk"] == 0.0
        assert r["transport_risk_level"] == "none"
        assert r["stubble_impact_score"] == 0.0

    def test_aligned_fire_higher_risk_than_crosswind(self):
        aligned = compute_fire_impact(
            pd.DataFrame([{"lat": 29.2, "lon": 76.5, "frp": 80.0}]),
            self.STATION_LAT, self.STATION_LON, wind_dir=315, wind_speed=3.0,
        )
        crosswind = compute_fire_impact(
            pd.DataFrame([{"lat": 28.7, "lon": 77.6, "frp": 80.0}]),
            self.STATION_LAT, self.STATION_LON, wind_dir=315, wind_speed=3.0,
        )
        assert aligned["stubble_impact_score"] > crosswind["stubble_impact_score"]

    def test_add_fire_features_adds_transport_columns(self):
        ts = pd.Timestamp("2025-11-01T12:00:00Z")
        df = pd.DataFrame([{
            "timestamp": ts,
            "station": "Anand_Vihar",
            "latitude": self.STATION_LAT,
            "longitude": self.STATION_LON,
            "wind_direction": 315.0,
            "wind_speed": 3.0,
        }])
        fires = self._fires()
        fires["acq_timestamp"] = pd.to_datetime([ts, ts])
        out = add_fire_features(df, fires_df=fires)
        row = out.iloc[0]
        assert row["wind_alignment_pct"] == 50.0
        assert row["transport_time_hours"] is not None and row["transport_time_hours"] > 0
        assert row["transport_risk"] >= 0.0
        assert row["stubble_impact_score"] >= 0.0
