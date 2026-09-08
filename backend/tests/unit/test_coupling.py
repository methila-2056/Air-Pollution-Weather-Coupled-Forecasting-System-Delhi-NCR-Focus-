"""Unit tests for the two-way weather-chemistry coupling module (SIH26082 PS #1)."""

import pandas as pd
import pytest

from ml.features.coupling import (
    add_coupling_features,
    boundary_stability_index,
    corrected_pbl_height,
    coupling_feedback_score,
    estimate_aod,
    pbl_suppression_factor,
    surface_radiation_attenuation,
    surface_temperature_damping,
)


class TestAod:
    def test_zero_pm25_yields_zero_aod(self):
        assert estimate_aod(0.0) == 0.0

    def test_aod_scales_with_pm25(self):
        assert estimate_aod(100.0) > estimate_aod(40.0)

    def test_aod_clamped_to_2_5(self):
        assert estimate_aod(1_000_000.0) == pytest.approx(2.5)

    def test_attenuation_is_in_unit_interval(self):
        for pm in (0, 50, 200, 800):
            t = surface_radiation_attenuation(pm)
            assert 0.0 < t <= 1.0


class TestPblSuppression:
    def test_bounded_between_0_8_and_1(self):
        for pm in (0, 100, 500):
            assert 0.8 <= pbl_suppression_factor(pm, hour=13) <= 1.0

    def test_stronger_at_noon_than_midnight(self):
        assert pbl_suppression_factor(300.0, hour=13) < pbl_suppression_factor(300.0, hour=2)

    def test_corrected_pbl_is_base_times_suppression(self):
        base = 700.0
        assert corrected_pbl_height(200.0, base, 12) == pytest.approx(
            base * pbl_suppression_factor(200.0, 12)
        )

    def test_temperature_damping_damps_more_by_day(self):
        assert surface_temperature_damping(300.0, 13) <= surface_temperature_damping(300.0, 3)


class TestStability:
    def test_in_unit_interval(self):
        s = boundary_stability_index(120.0, 500.0, 2.0, 4)
        assert 0.0 <= s <= 1.0

    def test_higher_with_light_wind(self):
        calm = boundary_stability_index(120.0, 500.0, 1.0, 4)
        breezy = boundary_stability_index(120.0, 500.0, 10.0, 4)
        assert calm > breezy

    def test_higher_with_shallow_pbl(self):
        shallow = boundary_stability_index(120.0, 150.0, 4.0, 4)
        deep = boundary_stability_index(120.0, 1500.0, 4.0, 4)
        assert shallow > deep


class TestFeedbackScore:
    def test_returns_expected_keys(self):
        score = coupling_feedback_score(180.0, 700.0, 3.0, 12)
        expected = {
            "aod_est", "radiation_transmittance", "pbl_suppression_factor",
            "corrected_pbl_height", "stability_coupling_index",
            "feedback_multiplier", "coupling_strength",
        }
        assert set(score) == expected

    def test_feedback_multiplier_exceeds_one_for_stable_episode(self):
        score = coupling_feedback_score(300.0, 120.0, 1.0, 3)
        assert score["feedback_multiplier"] > 1.0
        assert score["coupling_strength"] in {"weak", "moderate", "strong"}


class TestDataFramePipe:
    def _frame(self):
        t = pd.date_range("2025-11-01", periods=6, freq="1h", tz="UTC")
        return pd.DataFrame({
            "timestamp": t,
            "hour": t.hour,
            "pm25": [30.0, 90.0, 180.0, 250.0, 60.0, 10.0],
            "pbl_height": [400.0] * 6,
            "wind_speed": [3.0] * 6,
        })

    def test_adds_all_feature_columns(self):
        out = add_coupling_features(self._frame())
        for col in ("aod_est", "radiation_transmittance", "pbl_suppression_factor",
                    "corrected_pbl_height", "stability_coupling_index", "feedback_multiplier"):
            assert col in out.columns

    def test_vectorized_matches_scalar_path(self):
        df = self._frame()
        out = add_coupling_features(df)
        row = df.iloc[2]
        scalar = coupling_feedback_score(row["pm25"], row["pbl_height"], row["wind_speed"], row["hour"])
        assert out.loc[2, "stability_coupling_index"] == pytest.approx(
            scalar["stability_coupling_index"], abs=1e-3
        )

    def test_missing_pm25_column_yields_zeros(self):
        out = add_coupling_features(pd.DataFrame({"a": [1, 2]}))
        assert (out["stability_coupling_index"] == 0.0).all()
        assert (out["aod_est"] == 0.0).all()
