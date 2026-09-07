"""Unit tests for temperature-inversion detection (SIH26082 PS #4)."""

import numpy as np
import pandas as pd
import pytest

from ml.features.inversion import add_inversion_features, detect_inversion


class TestDetectInversion:
    def test_strong_below_150m(self):
        is_inv, category, strength = detect_inversion(100.0, hour=5)
        assert is_inv is True
        assert category == "strong"

    def test_moderate_150_to_300(self):
        is_inv, category, _ = detect_inversion(250.0, hour=5)
        assert category == "moderate"

    def test_weak_300_to_500(self):
        is_inv, category, _ = detect_inversion(450.0, hour=5)
        assert category == "weak"

    def test_none_above_500(self):
        is_inv, category, _ = detect_inversion(900.0, hour=12)
        assert is_inv is False
        assert category == "none"

    def test_strength_bounded_and_monotonic(self):
        s100 = detect_inversion(100.0, hour=12)[2]
        s400 = detect_inversion(400.0, hour=12)[2]
        s900 = detect_inversion(900.0, hour=12)[2]
        assert 0.0 <= s100 <= 1.0
        assert s100 > s400 > s900

    def test_unknown_on_nan(self):
        is_inv, category, strength = detect_inversion(np.nan, hour=12)
        assert is_inv is False
        assert category == "unknown"
        assert strength == 0.0

    def test_night_amplifies_diurnal_strength(self):
        night = detect_inversion(400.0, hour=2)[2]
        day = detect_inversion(400.0, hour=13)[2]
        assert night > day


class TestAddInversionFeatures:
    def _frame(self):
        ts = pd.date_range("2025-11-01", periods=4, freq="6h", tz="UTC")
        return pd.DataFrame({
            "timestamp": ts,
            "pbl_height": [120.0, 220.0, 450.0, 1200.0],
        })

    def test_columns_added(self):
        out = add_inversion_features(self._frame())
        for col in ("inversion_detected", "inversion_strength", "inversion_category"):
            assert col in out.columns

    def test_values_match_scalar_detection(self):
        out = add_inversion_features(self._frame())
        row = out.iloc[0]
        hour = pd.Timestamp(row["timestamp"]).hour
        _, cat, strength = detect_inversion(row["pbl_height"], hour=hour)
        assert row["inversion_category"] == cat
        assert row["inversion_strength"] == pytest.approx(strength)

    def test_missing_pbl_defaults_to_zero(self):
        out = add_inversion_features(pd.DataFrame({"x": [1, 2]}))
        assert out["inversion_detected"].tolist() == [0, 0]
        assert out["inversion_category"].tolist() == ["none", "none"]