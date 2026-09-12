"""Unit tests for the PM2.5 model evaluation pipeline (evaluate_pm25)."""

from __future__ import annotationsimport pathlibimport pandas as pdimport pytestfrom conftest import TINY_XGB, _make_synthetic_dffrom ml.training import evaluate_pm25 as evfrom ml.training.train_pm25 import run_trainingRF_TINY = {"n_estimators": 20, "max_depth": 3, "n_jobs": 1}


@pytest.fixture(scope="module")
def trained_models(tmp_path_factory) -> pathlib.Path:
    """Train tiny 1..3h models the evaluator can load as the deployed stack."""
    tmp = tmp_path_factory.mktemp("pm25eval")
    csv = tmp / "synth.csv"
    _make_synthetic_df(n_stations=3, n_hours=800).to_csv(csv, index=False)
    run_training(
        csv_path=csv,
        horizons=[1, 3],
        model_dir=tmp / "models",
        xgb_params=TINY_XGB,
    )
    return tmp / "models"


@pytest.fixture(scope="module")
def eval_df() -> pd.DataFrame:
    df = _make_synthetic_df(n_stations=3, n_hours=800)
    for h in (1, 3):
        df[f"target_h{h}"] = df.groupby("station")["pm25"].shift(-h)
    return df


class TestSplitRanges:
    def test_reports_per_split_periods(self, eval_df):
        ranges = ev._split_ranges(eval_df)
        assert set(ranges) == {"train", "validation", "test"}
        for split in ("train", "validation", "test"):
            assert ranges[split]["n_rows"] > 0
            assert ranges[split]["start"] <= ranges[split]["end"]
        assert ranges["train"]["end"] < ranges["validation"]["start"]
        assert ranges["validation"]["end"] < ranges["test"]["start"]


class TestEvaluateHorizon:
    def test_all_models_scored_on_same_test_rows(self, trained_models, eval_df):
        from joblib import load        from ml.training.train_pm25 import _select_features

        features, _ = _select_features(eval_df)
        xgb_model = load(trained_models / "h-1" / "model.joblib")
        res = ev.evaluate_horizon(eval_df, features, 1, xgb_model, rf_params=RF_TINY)

        assert res["horizon_hours"] == 1
        assert res["n_test"] > 0
        assert res["n_train"] > 0
        assert set(res["metrics"]) == {"persistence", "random_forest", "xgboost"}
        counts = {m["n"] for m in res["metrics"].values()}
        assert len(counts) == 1, "all models must be evaluated on the same rows"

    def test_persistence_is_pm25_lag1(self, trained_models, eval_df):
        from joblib import load        from ml.training.train_pm25 import _select_features

        features, _ = _select_features(eval_df)
        xgb_model = load(trained_models / "h-3" / "model.joblib")
        res = ev.evaluate_horizon(eval_df, features, 3, xgb_model, rf_params=RF_TINY)

        test_rows = eval_df[
            eval_df["target_h3"].notna() & eval_df["pm25_lag1"].notna()
        ]
        test_rows = test_rows[test_rows["split"] == "test"]
        assert res["metrics"]["persistence"]["n"] == len(test_rows)
        assert res["test_period_start"] == str(test_rows["timestamp"].min())


class TestRunEvaluation:
    def test_writes_json_and_csv(self, trained_models, tmp_path):
        csv = trained_models.parent / "synth.csv"
        out_json = tmp_path / "evaluation.json"
        out_csv = tmp_path / "evaluation.csv"

        payload = ev.run_evaluation(
            csv_path=csv,
            model_dir=trained_models,
            horizons=[1, 3],
            output_path=out_json,
            csv_output_path=out_csv,
            rf_params=RF_TINY,
        )

        assert payload["target"] == "pm25"
        assert payload["horizons"] == [1, 3]
        assert payload["evaluated_models"] == ["persistence", "random_forest", "xgboost"]
        assert payload["split_type"] == "chronological"
        assert payload["feature_count"] == len(payload["features"]) > 0
        assert set(payload["split_ranges"]) == {"train", "validation", "test"}
        assert len(payload["results"]) == 2
        for res in payload["results"]:
            assert res["horizon_hours"] in (1, 3)
            for m in ("persistence", "random_forest", "xgboost"):
                assert res["metrics"][m]["n"] > 0
                assert res["metrics"][m]["r2"] <= 1.0 + 1e-9
                assert res["metrics"][m]["rmse"] >= 0
                assert res["metrics"][m]["mae"] >= 0

        assert out_json.exists()
        assert out_csv.exists()
        flat = pd.read_csv(out_csv)
        assert set(flat["model"]) == {"persistence", "random_forest", "xgboost"}
        assert set(flat["horizon_hours"]) == {1, 3}
        assert flat[["mae", "rmse", "r2"]].notna().all().all()

    def test_missing_config_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ev.run_evaluation(
                csv_path=tmp_path / "nope.csv",
                model_dir=tmp_path / "empty",
                horizons=[1],
            )
