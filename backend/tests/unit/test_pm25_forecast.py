"""Unit + API tests for the PM2.5 forecast service and endpoint.

Models are trained with tiny parameters into a temp dir so the full stack
(DB feature build -> forecaster -> FastAPI endpoint) is exercised against real
XGBoost artifacts.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest
from app.services import pm25_forecast_service as svc
from conftest import TINY_XGB, _make_synthetic_df
from fastapi.testclient import TestClient

from ml.training.train_pm25 import run_training

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def tiny_model_dir(tmp_path_factory) -> pathlib.Path:
    """Train tiny 1..3h PM2.5 models into a session-scoped temp dir."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="pm25_models_"))
    csv = tmp / "synth.csv"
    _make_synthetic_df(n_stations=3, n_hours=800).to_csv(csv, index=False)
    run_training(
        csv_path=csv,
        horizons=[1, 2, 3],
        model_dir=tmp / "models",
        xgb_params=TINY_XGB,
    )
    return tmp / "models"


@pytest.fixture(autouse=True)
def _reset_forecaster(monkeypatch, tiny_model_dir):
    """Point the service at the tiny models and reset the cache each test."""
    monkeypatch.setenv("AEROCAST_PM25_MODEL_DIR", str(tiny_model_dir))
    svc.reset_forecaster()
    yield
    svc.reset_forecaster()


# ─────────────────────────────────────────────────────────────────────────────
# Service-level tests
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildFeatureRow:
    def test_builds_expected_columns(self, db_session):
        from app.models.db_models import Station

        station = db_session.query(Station).filter(Station.name == "Anand Vihar").first()
        row, release, ctx = svc.build_feature_row(db_session, station)

        assert isinstance(row, dict)
        # every trained feature is present in the row (values may be None)
        forecaster = svc.get_pm25_forecaster()
        assert all(f in row for f in forecaster.features)
        assert "pm25_lag1" in row
        assert release is not None
        assert ctx["pollution_rows_in_window"] >= 4

    def test_persistence_last_observed(self, db_session):
        from app.models.db_models import Station

        station = db_session.query(Station).filter(Station.name == "Anand Vihar").first()
        row, release, ctx = svc.build_feature_row(db_session, station)
        # conftest seeds 12 hours of linearly-rising pm25; lag1 = last-but-one
        assert ctx["pm25_lag1"] is not None
        assert row["pm25_lag1"] == ctx["pm25_lag1"]


class TestForecastPm25:
    def test_serves_requested_horizons(self, db_session):
        payload = svc.forecast_pm25(db_session, "Anand Vihar", hours=3)
        assert payload["station"] == "Anand Vihar"
        assert payload["served_horizons"] == [1, 2, 3]
        assert len(payload["forecasts"]) == 3

    def test_unsupported_horizons_raise(self, db_session):
        # models only cover 1..3
        with pytest.raises(RuntimeError):
            svc.forecast_pm25(db_session, "Anand Vihar", hours=6)

    def test_bounds_consistent(self, db_session):
        payload = svc.forecast_pm25(db_session, "Anand Vihar", hours=3)
        for point in payload["forecasts"]:
            assert point["pm25_lower_bound"] <= point["predicted_pm25"] <= point["pm25_upper_bound"]
            assert point["baseline_persistence"] is not None
            assert point["test_mae"] is not None

    def test_unknown_station_raises(self, db_session):
        with pytest.raises(ValueError, match="station_not_found"):
            svc.forecast_pm25(db_session, "Nonexistent Station", hours=3)


# ─────────────────────────────────────────────────────────────────────────────
# API-level tests
# ─────────────────────────────────────────────────────────────────────────────


class TestPm25ForecastApi:
    def test_get_forecast(self, client: TestClient, db_session):
        resp = client.get("/api/forecast/pm25?station_name=Anand Vihar&hours=3")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["station"] == "Anand Vihar"
        assert body["model"] == "xgboost"
        assert "split-conformal" in body["uncertainty_method"].lower()
        assert len(body["forecasts"]) == 3
        point = body["forecasts"][0]
        assert point["forecast_horizon"] == 1
        assert "predicted_pm25" in point
        assert "pm25_lower_bound" in point
        assert "pm25_upper_bound" in point
        assert point["pm25_lower_bound"] <= point["predicted_pm25"] <= point["pm25_upper_bound"]

    def test_default_station_and_hours(self, client: TestClient, db_session):
        resp = client.get("/api/forecast/pm25", params={"hours": 2})
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["forecasts"]) == 2

    def test_invalid_hours(self, client: TestClient, db_session):
        resp = client.get("/api/forecast/pm25", params={"hours": 0})
        assert resp.status_code == 422

    def test_missing_station_404(self, client: TestClient, db_session):
        resp = client.get("/api/forecast/pm25", params={"station_name": "Nope"})
        assert resp.status_code == 404

    def test_model_card_ready(self, client: TestClient, db_session):
        resp = client.get("/api/forecast/pm25/model-card")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["n_horizons"] == 3
        assert body["horizons"] == [1, 2, 3]

    def test_route_not_shadowed_by_forecast_station(self, client: TestClient, db_session):
        """/forecast/pm25 must not be captured by /forecast/{station_name}."""
        resp = client.get("/api/forecast/pm25", params={"hours": 3})
        assert resp.status_code == 200


class TestModelCardUnavailable:
    def test_returns_available_false(self, client: TestClient, db_session, monkeypatch, tmp_path):
        monkeypatch.setenv("AEROCAST_PM25_MODEL_DIR", str(tmp_path / "empty"))
        svc.reset_forecaster()
        resp = client.get("/api/forecast/pm25/model-card")
        assert resp.status_code == 200
        assert resp.json()["available"] is False
        svc.reset_forecaster()

    def test_forecast_when_not_trained_503(self, client: TestClient, db_session, monkeypatch, tmp_path):
        monkeypatch.setenv("AEROCAST_PM25_MODEL_DIR", str(tmp_path / "empty"))
        svc.reset_forecaster()
        resp = client.get("/api/forecast/pm25?station_name=Anand Vihar")
        assert resp.status_code == 503
        svc.reset_forecaster()
