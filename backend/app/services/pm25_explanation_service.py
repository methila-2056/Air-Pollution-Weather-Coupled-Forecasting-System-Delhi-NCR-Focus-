"""SHAP explanation service for the production PM2.5 XGBoost forecasts.

Re-uses the exact feature row built by ``pm25_forecast_service.build_feature_row``
(the same row the forecast endpoint issues predictions from) and explains it
with ``shap.TreeExplainer`` against the deployed model for the requested
horizon. The prediction and SHAP values therefore come from the *same* model
and feature vector as the live forecast — nothing is re-engineered or faked.
"""

from __future__ import annotations

import logging
import os
import pathlib
from datetime import timedelta
from typing import Any

import pandas as pd

from ..models.db_models import Forecast, Station
from ..utils.helpers import repo_root

logger = logging.getLogger("pm25_explanation_service")

DEFAULT_MODEL_DIR = repo_root() / "models" / "pm25"

_valid_horizons = {1, 6, 12, 24, 48, 72}

_shap_explainer_cache: dict[tuple[str, int], Any] = {}


def reset_explainer() -> None:
    """Drop the cached explainer (used by tests to switch model dirs)."""
    _shap_explainer_cache.clear()


def get_model_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("AEROCAST_PM25_MODEL_DIR", DEFAULT_MODEL_DIR))


def get_shap_explainer(horizon: int):
    """Return a cached Pm25ShapExplainer bound to (model_dir, horizon)."""
    from ml.explainability import Pm25ShapExplainer

    model_dir = get_model_dir()
    key = (str(model_dir), horizon)
    if key not in _shap_explainer_cache:
        _shap_explainer_cache[key] = Pm25ShapExplainer(model_dir)
    return _shap_explainer_cache[key]


def explain_pm25_forecast(
    db,
    station_name: str,
    horizon: int,
    prediction: float | None = None,
) -> dict[str, Any]:
    """Explain the PM2.5 XGBoost forecast for ``horizon`` at ``station_name``.

    Returns a payload with real SHAP-derived top positive/negative drivers
    plus the honest per-horizon held-out test metrics for that model.
    """
    if horizon not in _valid_horizons:
        raise ValueError(
            f"horizon_out_of_range: explanation is available for horizons "
            f"{sorted(_valid_horizons)} (got {horizon})"
        )

    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise ValueError(f"station_not_found: {station_name}")

    explainer = get_shap_explainer(horizon)
    if not explainer.is_trained(horizon):
        raise RuntimeError(f"No trained XGBoost model for horizon {horizon}h; cannot explain")

    from ..services.pm25_forecast_service import build_feature_row, get_pm25_forecaster

    forecaster = get_pm25_forecaster()
    if not forecaster.is_available:
        raise RuntimeError("PM2.5 models are not trained yet; cannot explain forecasts")

    feature_row, release_time, context = build_feature_row(db, station)

    if prediction is None:
        x = explainer.build_vector(feature_row)
        model = forecaster.models.get(horizon)
        if model is None:
            raise RuntimeError(
                f"Forecaster has no model for horizon {horizon}h; cannot explain"
            )
        prediction = float(model.predict(x)[0])

    result = explainer.explain_row(feature_row, horizon, prediction=prediction)

    met = forecaster.test_metrics(horizon)
    forecast_ts = release_time + timedelta(hours=horizon)

    payload = {
        "forecast_id": None,
        "station": station.name,
        "station_id": station.id,
        "model": "xgboost",
        "explanation_method": result["explanation_method"],
        "horizon_hours": horizon,
        "forecast_timestamp": forecast_ts.to_pydatetime(),
        "stored_pm25_pred": None,
        "forecast_pm25": result["forecast_pm25"],
        "base_value": result["base_value"],
        "summary": result["summary"],
        "top_positive_drivers": result["top_positive_drivers"],
        "top_negative_drivers": result["top_negative_drivers"],
        "contributions_by_magnitude": result["contributions_by_magnitude"],
        "n_features": result["n_features"],
        "feature_values_used": context,
        "data_as_of": release_time.to_pydatetime(),
        "generated_at": pd.Timestamp.now(tz=None).to_pydatetime(),
        "test_metrics": {
            "mae": met.get("mae"),
            "rmse": met.get("rmse"),
            "r2": met.get("r2"),
            "n": met.get("n"),
        },
    }
    return payload


def explain_forecast_by_id(db, forecast_id: int) -> dict[str, Any]:
    """Explain a *stored* forecast row via real SHAP on the deployed XGBoost model.

    Rebuilds the exact feature row the model would have consumed at the
    forecast's release hour (``forecast_timestamp - horizon_hours``) and runs
    ``shap.TreeExplainer`` on it. ``forecast_pm25`` is the model-derived
    prediction for that same feature row (so the SHAP decomposition is exact:
    forecast = base_value + sum of shap values); ``stored_pm25_pred`` is the
    value that was originally persisted on the row.
    """
    forecast = db.query(Forecast).filter(Forecast.id == forecast_id).first()
    if forecast is None:
        raise ValueError(f"forecast_not_found: no forecast with id {forecast_id}")

    horizon = forecast.horizon_hours
    if horizon not in _valid_horizons:
        raise ValueError(
            f"horizon_out_of_range: explanation is available for horizons "
            f"{sorted(_valid_horizons)} (got {horizon})"
        )

    station = db.query(Station).filter(Station.id == forecast.station_id).first()
    if not station:
        raise ValueError(f"station_not_found: station_id={forecast.station_id}")

    explainer = get_shap_explainer(horizon)
    if not explainer.is_trained(horizon):
        raise RuntimeError(f"No trained XGBoost model for horizon {horizon}h; cannot explain")

    from ..services.pm25_forecast_service import build_feature_row, get_pm25_forecaster

    forecaster = get_pm25_forecaster()
    if not forecaster.is_available:
        raise RuntimeError("PM2.5 models are not trained yet; cannot explain forecasts")

    forecast_ts = pd.Timestamp(forecast.forecast_timestamp)
    release_hour = forecast_ts.floor("h") - timedelta(hours=horizon)
    feature_row, release_time, context = build_feature_row(db, station, as_of_hour=release_hour)

    x = explainer.build_vector(feature_row)
    model = forecaster.models.get(horizon)
    if model is None:
        raise RuntimeError(
            f"Forecaster has no model for horizon {horizon}h; cannot explain"
        )
    prediction = float(model.predict(x)[0])

    result = explainer.explain_row(feature_row, horizon, prediction=prediction)

    met = forecaster.test_metrics(horizon)

    payload = {
        "forecast_id": forecast.id,
        "station": station.name,
        "station_id": station.id,
        "model": "xgboost",
        "explanation_method": result["explanation_method"],
        "horizon_hours": horizon,
        "forecast_timestamp": forecast_ts.to_pydatetime(),
        "stored_pm25_pred": forecast.pm25_pred,
        "forecast_pm25": result["forecast_pm25"],
        "base_value": result["base_value"],
        "summary": result["summary"],
        "top_positive_drivers": result["top_positive_drivers"],
        "top_negative_drivers": result["top_negative_drivers"],
        "contributions_by_magnitude": result["contributions_by_magnitude"],
        "n_features": result["n_features"],
        "feature_values_used": context,
        "data_as_of": release_time.to_pydatetime(),
        "generated_at": pd.Timestamp.now(tz=None).to_pydatetime(),
        "test_metrics": {
            "mae": met.get("mae"),
            "rmse": met.get("rmse"),
            "r2": met.get("r2"),
            "n": met.get("n"),
        },
    }
    return payload
