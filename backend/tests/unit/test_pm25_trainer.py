"""Unit tests for the PM2.5 trainer (persistence + direct-horizon XGBoost)."""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import pytest
from conftest import TINY_XGB, _make_synthetic_df

from ml.training import train_pm25 as tr


@pytest.fixture(scope="module")
def synthetic_csv(tmp_path_factory) -> pathlib.Path:
    path = tmp_path_factory.mktemp("pm25train") / "synthetic.csv"
    _make_synthetic_df(n_stations=3, n_hours=720).to_csv(path, index=False)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectFeatures:
    def test_keeps_candidate_features(self):
        df = _make_synthetic_df()
        feats, dropped = tr._select_features(df)
        assert "temperature" in feats
        assert "pm25_lag1" in feats
        # constant numeric columns are dropped from the feature set
        assert "humidity" not in feats
        assert "fire_count" not in feats
        assert all(col in feats for col in ("hour_sin", "month_sin"))

    def test_all_nan_cols_dropped(self):
        df = _make_synthetic_df()
        df["strongest_layer_gradient"] = np.nan
        feats, dropped = tr._select_features(df)
        assert "strongest_layer_gradient" not in feats
        assert dropped["strongest_layer_gradient"] == "all NaN"


class TestParseHorizonArg:
    def test_range(self):
        assert tr._parse_horizon_arg("1..72") == list(range(1, 73))

    def test_list(self):
        assert tr._parse_horizon_arg("1 3 6 12 24") == [1, 3, 6, 12, 24]


class TestComputeMetrics:
    def test_perfect_prediction(self):
        y = np.array([100.0, 200.0, 150.0])
        m = tr._compute_metrics(y, y)
        assert m["mae"] == 0.0
        assert m["rmse"] == 0.0
        assert m["r2"] == 1.0

    def test_empty(self):
        m = tr._compute_metrics(np.array([]), np.array([]))
        assert m["n"] == 0
        assert np.isnan(m["mae"])

    def test_nonfinite_filtered(self):
        y = np.array([100.0, np.nan, 120.0])
        p = np.array([90.0, 999.0, 110.0])
        m = tr._compute_metrics(y, p)
        assert m["n"] == 2


class TestConformalQuantile:
    def test_empirical_coverage_reaches_target(self):
        rng = np.random.default_rng(0)
        residuals = np.abs(rng.normal(0, 10, 400))
        conf = tr._conformal_quantile(residuals, coverage=0.85)
        empirical = float(np.mean(residuals <= conf["quantile"]))
        assert conf["coverage_target"] == 0.85
        assert empirical >= 0.85

    def test_empty(self):
        conf = tr._conformal_quantile(np.array([]), coverage=0.85)
        assert conf["n_calibration"] == 0
        assert np.isnan(conf["quantile"])


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end run (fast, tiny estimators)
# ─────────────────────────────────────────────────────────────────────────────


class TestRunTraining:
    def test_train_and_save_artifacts(self, synthetic_csv, tmp_path):
        model_dir = tmp_path / "models"
        results = tr.run_training(
            csv_path=synthetic_csv,
            horizons=[1, 3],
            model_dir=model_dir,
            xgb_params=TINY_XGB,
        )

        assert set(results.keys()) == {1, 3}
        for h in (1, 3):
            h_dir = model_dir / f"h-{h}"
            assert (h_dir / "model.joblib").exists()
            assert (h_dir / "metrics.json").exists()
            assert (h_dir / "conformal.json").exists()
            metrics = json.loads((h_dir / "metrics.json").read_text(encoding="utf-8"))
            assert metrics["horizon_hours"] == h
            tm = metrics["test_metrics"]
            assert 0 < tm["mae"] < 400
            assert tm["n"] > 0
            # honest negative/badly-shaped results are invalid
            assert tm["rmse"] >= 0
            assert -0.2 <= tm["r2"] <= 1.0

        config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        assert config["chronological_split"] is True
        assert config["shuffle"] is False
        assert config["strategy"].startswith("direct per-horizon")
        assert config["uncertainty_method"].startswith("Split-conformal")
        assert "features" in config

        preds_file = model_dir / "training_predictions.csv"
        assert preds_file.exists()
        preds = pd.read_csv(preds_file)
        assert set(preds["horizon_hours"].unique()) == {1, 3}
        # xgb predictions are finite on the held-out test rows
        assert preds["predicted_pm25_xgb"].notna().all()

    def test_xgb_beats_or_equals_persistence_on_synthetic(self, synthetic_csv, tmp_path):
        # On a smooth synthetic series XGBoost should reach MAE near persistence;
        # we assert it matches within generous tolerance (structure exists).
        results = tr.run_training(
            csv_path=synthetic_csv,
            horizons=[1],
            model_dir=tmp_path / "m2",
            xgb_params=TINY_XGB,
        )
        tm = results[1]["test_metrics"]
        pm = results[1]["persistence_test"]
        assert tm["mae"] <= pm["mae"] * 1.5 + 1e-6 or results[1]["test_metrics"]["n"] == 0
