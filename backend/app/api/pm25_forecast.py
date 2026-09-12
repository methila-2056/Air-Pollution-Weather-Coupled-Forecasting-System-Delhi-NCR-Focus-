"""REST API for the trained PM2.5 forecasting models.

Endpoint: GET /api/forecast/pm25?station_name=...&hours=72
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Station
from ..schemas.schemas import (
    ForecastExplanationResponse,
    Pm25ForecastExplanationResponse,
    Pm25ForecastResponse,
    Pm25ModelCardResponse,
)
from ..services import pm25_explanation_service
from ..services import pm25_forecast_service as svc

router = APIRouter()


@router.get("/forecast/pm25", response_model=Pm25ForecastResponse)
def get_pm25_forecast(
    station_name: str | None = Query(default=None, description="Station name (defaults to first station)"),
    hours: int = Query(default=72, ge=1, le=72),
    db: Session = Depends(get_db),
):
    """72-hour PM2.5 forecast for one station, with uncertainty bounds.

    Uses the trained direct multi-horizon XGBoost models + per-horizon
    split-conformal prediction intervals. Returns honest per-horizon test
    metrics alongside every prediction.
    """
    # Resolve the target station BEFORE the forecast try-block so 404/503
    # responses are never masked by the generic exception handler.
    if station_name is not None:
        station = db.query(Station).filter(Station.name == station_name).first()
        if not station:
            raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
        target = station_name
    else:
        first = db.query(Station).order_by(Station.id).first()
        if not first:
            raise HTTPException(status_code=503, detail="No stations available; seed the database first")
        target = first.name

    try:
        payload = svc.forecast_pm25(db, target, hours)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("station_not_found"):
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # defensive: pipeline surprises
        raise HTTPException(status_code=500, detail=f"PM2.5 forecast failed: {exc}") from exc

    return payload


@router.get("/forecast/pm25/model-card", response_model=Pm25ModelCardResponse)
def get_pm25_model_card(db: Session = Depends(get_db)):
    """Describe the loaded PM2.5 models without running a forecast."""
    try:
        forecaster = svc.get_pm25_forecaster()
    except Exception as exc:
        return {
            "model": "xgboost", "forecast_strategy": "direct multi-horizon",
            "uncertainty_method": "split-conformal", "coverage_target": None,
            "n_horizons": 0, "horizons": [], "n_features": 0, "available": False,
            "message": str(exc),
        }
    summary = forecaster.summary()
    return {
        "model": summary["model"],
        "forecast_strategy": summary["strategy"],
        "uncertainty_method": summary["uncertainty_method"],
        "coverage_target": summary["coverage_target"],
        "n_horizons": summary["n_horizons"],
        "horizons": summary["horizons"],
        "n_features": summary["n_features"],
        "available": forecaster.is_available,
        "message": "ready" if forecaster.is_available else "PM2.5 models not trained",
    }


@router.get("/forecast/pm25/explanation", response_model=Pm25ForecastExplanationResponse)
def get_pm25_forecast_explanation(
    station_name: str | None = Query(default=None, description="Station name (defaults to first station)"),
    horizon: int = Query(default=24, ge=1, le=72),
    db: Session = Depends(get_db),
):
    """SHAP explanation for a PM2.5 XGBoost forecast horizon.

    Explains the SAME feature row the forecast endpoint uses: per-feature SHAP
    contributions from shap.TreeExplainer on the deployed model, split into
    top positive/negative drivers. Forecast_pm25, base_value, and every
    percentage are model-derived — nothing is hardcoded or estimated.
    """
    if station_name is not None:
        station = db.query(Station).filter(Station.name == station_name).first()
        if not station:
            raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
        target = station_name
    else:
        first = db.query(Station).order_by(Station.id).first()
        if not first:
            raise HTTPException(status_code=503, detail="No stations available; seed the database first")
        target = first.name

    try:
        payload = pm25_explanation_service.explain_pm25_forecast(db, target, horizon)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("station_not_found"):
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # defensive: SHAP pipeline surprises
        raise HTTPException(status_code=500, detail=f"PM2.5 explanation failed: {exc}") from exc

    return payload


@router.get("/forecast/{forecast_id}/explanation", response_model=ForecastExplanationResponse)
def get_forecast_explanation(
    forecast_id: int,
    db: Session = Depends(get_db),
):
    """SHAP explanation for a *stored* forecast, keyed by its id.

    Rebuilds the exact feature row consumed at the forecast's release hour and
    runs shap.TreeExplainer on the deployed XGBoost model for that horizon.
    ``forecast_pm25`` (the model-derived prediction on that same row) plus
    ``top_positive_drivers``/``top_negative_drivers`` are all real SHAP
    results — nothing hardcoded, no fabricated percentages.

    Use with: ``/api/forecast/generate`` or ``/api/forecast/coupled`` which
    persist forecast rows, or with the ``id`` of any row in the ``forecasts``.
    """
    try:
        payload = pm25_explanation_service.explain_forecast_by_id(db, forecast_id)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("forecast_not_found"):
            raise HTTPException(status_code=404, detail=msg) from exc
        if msg.startswith("station_not_found"):
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # defensive: SHAP pipeline surprises
        raise HTTPException(status_code=500, detail=f"Forecast explanation failed: {exc}") from exc

    return payload
