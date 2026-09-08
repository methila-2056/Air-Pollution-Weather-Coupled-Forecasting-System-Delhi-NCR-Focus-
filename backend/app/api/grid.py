from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Forecast, Station, WeatherReading
from ..services.grid_service import compute_ncr_grid

router = APIRouter()


@router.get("/grid/forecast", response_model=dict)
def get_grid_forecast(
    horizon_hours: int = Query(default=24, ge=1, le=72),
    db: Session = Depends(get_db),
):
    """High-resolution spatial AQI forecast over the NCR domain.

    Interpolates the latest persisted station forecasts (IDW + wind advection)
    onto a ~2.2km grid for a chosen horizon, returning cells for mapping.
    """
    stations = db.query(Station).order_by(Station.name).all()
    if not stations:
        return {"error": "no stations", "cells": []}

    forecasts_by_station = {}
    wind_dir = wind_speed = None
    for s in stations:
        wx = (
            db.query(WeatherReading)
            .filter(WeatherReading.station_id == s.id)
            .order_by(WeatherReading.timestamp.desc())
            .first()
        )
        if wx and wind_dir is None:
            wind_dir = wx.wind_direction
            wind_speed = wx.wind_speed
        horizon = max(1, min(72, horizon_hours))
        fs = (
            db.query(Forecast)
            .filter(
                Forecast.station_id == s.id,
                Forecast.horizon_hours == horizon,
            )
            .order_by(Forecast.forecast_timestamp.desc())
            .all()
        )
        forecasts_by_station[s.name] = [
            {
                "horizon_hours": f.horizon_hours,
                "aqi_pred": f.aqi_pred,
                "aqi_category": f.aqi_category,
            }
            for f in fs
        ]

    return compute_ncr_grid(
        stations,
        forecasts_by_station,
        horizon_hours,
        wind_dir=wind_dir,
        wind_speed=wind_speed,
    )


@router.get("/grid/overview", response_model=dict)
def get_grid_overview(db: Session = Depends(get_db)):
    """Summary of forecast coverage across NCR stations and horizons."""
    stations = db.query(Station).order_by(Station.name).all()
    counts = {
        s.name: db.query(Forecast).filter(Forecast.station_id == s.id).count()
        for s in stations
    }
    latest = db.query(Forecast).order_by(Forecast.forecast_timestamp.desc()).first()
    return {
        "stations": [{"name": s.name, "lat": s.latitude, "lon": s.longitude, "forecasts": counts[s.name]} for s in stations],
        "latest_forecast_at": latest.forecast_timestamp.isoformat() if latest else None,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
