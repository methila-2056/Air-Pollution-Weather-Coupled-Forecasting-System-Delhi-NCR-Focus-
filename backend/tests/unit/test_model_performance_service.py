"""Unit + API tests for the model-performance dashboard path.

Covers ``app.services.model_performance_service`` (the endpoint behind the
"Model Performance" card) and the ``GET /api/model/performance`` route.
"""

import json

import pytest
from app.schemas.schemas import ModelPerformanceResponse
from app.services import model_performance_service as svc

VALID_JSON = {
    "schema_version": 1,
    "target": "pm25",
    "model_dir": "tmp",
    "data_source": "test.csv",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "feature_count": 3,
    "features": ["temperature", "wind_speed", "humidity"],
    "horizons": [1, 6],
    "evaluated_models": ["xgboost", "persistence"],
    "split_type": "chronological",
    "split_ratios": [0.6, 0.2, 0.2],
    "split_ranges": {
        "train": {"start": "2024-01-01 00:00:00", "end": "2024-06-01 00:00:00", "n_rows": 100},
        "validation": {"start": "2024-06-01 00:00:00", "end": "2024-08-01 00:00:00", "n_rows": 20},
        "test": {"start": "2024-08-01 00:00:00", "end": "2024-12-01 00:00:00", "n_rows": 40},
    },
    "results": [
        {
            "horizon_hours": 1,
            "n_train": 100,
            "n_val": 20,
            "n_test": 40,
            "test_period_start": "2024-08-01 00:00:00",
            "test_period_end": "2024-12-01 00:00:00",
            "metrics": {
                "xgboost": {"mae": 10.0, "rmse": 15.0, "r2": 0.9, "mape": 12.0, "nmae": 0.1, "n": 40},
                "persistence": {"mae": 20.0, "rmse": 25.0, "r2": 0.5, "mape": 20.0, "nmae": 0.2, "n": 40},
            },
        },
        {
            "horizon_hours": 6,
            "n_train": 100,
            "n_val": 20,
            "n_test": 40,
            "metrics": {"xgboost": {"mae": 18.0, "rmse": 24.0, "r2": 0.7, "mape": 18.0, "nmae": 0.18, "n": 40}},
        },
    ],
}


@pytest.fixture()
def model_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AEROCAST_PM25_MODEL_DIR", str(tmp_path))
    return tmp_path


def test_get_evaluation_path_resolves_env_override(model_dir):
    assert svc.get_evaluation_path() == model_dir / "evaluation.json"


def test_load_model_performance_returns_validated_schema(model_dir):
    (model_dir / "evaluation.json").write_text(json.dumps(VALID_JSON), encoding="utf-8")
    result = svc.load_model_performance()
    assert isinstance(result, ModelPerformanceResponse)
    assert result.target == "pm25"
    assert result.horizons == [1, 6]
    assert result.evaluated_models == ["xgboost", "persistence"]
    assert result.feature_count == 3
    assert result.split_ranges["test"].n_rows == 40
    assert result.results[0].metrics["xgboost"].mae == 10.0
    assert result.results[0].horizon_hours == 1


def test_load_model_performance_missing_dataset_raises(model_dir):
    with pytest.raises(FileNotFoundError, match="evaluate_pm25"):
        svc.load_model_performance()


def test_api_model_performance_200(client, model_dir):
    (model_dir / "evaluation.json").write_text(json.dumps(VALID_JSON), encoding="utf-8")
    response = client.get("/api/model/performance")
    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "pm25"
    assert body["horizons"] == [1, 6]
    assert len(body["results"]) == 2
    assert "xgboost" in body["results"][0]["metrics"]


def test_api_model_performance_404_without_dataset(client, model_dir):
    response = client.get("/api/model/performance")
    assert response.status_code == 404
    assert "evaluate_pm25" in response.json()["detail"]
