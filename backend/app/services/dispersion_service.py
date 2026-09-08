"""Numerical dispersion forecasting service for Delhi NCR.

Runs the grid-based advection-diffusion-deposition emission solver
(ml.features.dispersion_solver) over the latest persisted NCR forecast surface,
using live weather/fires from the database as lateral boundary and source data.

The solver — rather than pure interpolation — dynamically advects the
stubble-burning plumes downwind and lets meteorology (wind, PBL, rain) coupled
with the aerosol field drive the hourly AQI evolution.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from ml.features.dispersion_solver import run_dispersion_forecast

from ..models.db_models import FireReading, Forecast, Station, WeatherReading
from .aqi_calculator import get_aqi_category
from .grid_service import GRID_STEP, NCR_BOUNDS, build_grid, idw_interpolate


def _latest_weather(db: Session) -> dict:
    """Domain-representative latest weather (average over stations)."""
    vals: dict[str, list] = {"wind_speed": [], "wind_direction": [], "pbl_height": [], "precipitation": []}
    for s in db.query(Station).all():
        row = (
            db.query(WeatherReading)
            .filter(WeatherReading.station_id == s.id)
            .order_by(WeatherReading.timestamp.desc())
            .first()
        )
        if row is None:
            continue
        if row.wind_speed is not None:
            vals["wind_speed"].append(row.wind_speed)
        if row.wind_direction is not None:
            vals["wind_direction"].append(row.wind_direction)
        if row.pbl_height is not None:
            vals["pbl_height"].append(row.pbl_height)
        if row.precipitation is not None:
            vals["precipitation"].append(row.precipitation)
    if not any(vals["wind_speed"]):
        return {"wind_speed": 4.0, "wind_direction": 90.0, "pbl_height": 600.0, "precipitation": 0.0}
    import numpy as _np
    return {
        "wind_speed": float(_np.mean(vals["wind_speed"]) or 4.0),
        "wind_direction": float(_np.mean(vals["wind_direction"]) or 90.0),
        "pbl_height": float(_np.mean(vals["pbl_height"]) or 600.0),
        "precipitation": float(sum(vals["precipitation"]) or 0.0),
    }


def _initial_aqi_field(db: Session, horizon_hours: int) -> np.ndarray | None:
    """IDW-interpolate the latest horizon station forecasts into a grid field."""
    lats, lons = build_grid()
    stations = db.query(Station).order_by(Station.name).all()
    src_lats, src_lons, src_vals = [], [], []
    for s in stations:
        f = (
            db.query(Forecast)
            .filter(
                Forecast.station_id == s.id,
                Forecast.horizon_hours == horizon_hours,
                Forecast.aqi_pred.isnot(None),
            )
            .order_by(Forecast.forecast_timestamp.desc())
            .first()
        )
        if f is None:
            continue
        src_lats.append(s.latitude)
        src_lons.append(s.longitude)
        src_vals.append(f.aqi_pred)
    if not src_vals:
        return None
    return idw_interpolate(
        np.array(src_lats), np.array(src_lons), np.array(src_vals), lats, lons
    )


def _fires_in_domain(db: Session, limit: int = 60) -> list:
    b = NCR_BOUNDS
    rows = db.query(FireReading).order_by(FireReading.acq_date.desc()).limit(1000).all()
    fires = []
    for r in rows:
        if r.latitude is None or r.longitude is None:
            continue
        if b["lat_min"] <= r.latitude <= b["lat_max"] and b["lon_min"] <= r.longitude <= b["lon_max"]:
            fires.append({
                "lat": r.latitude,
                "lon": r.longitude,
                "frp": r.frp or 2.0,
                "confidence": r.confidence,
                "satellite": r.satellite,
            })
            if len(fires) >= limit:
                break
    return fires


def run_dispersion_forecast_service(
    db: Session,
    horizon_hours: int = 72,
    start_hour: int = 8,
) -> dict:
    """Run the numerical dispersion forecast from the latest DB state."""
    wx = _latest_weather(db)
    initial_aqi = _initial_aqi_field(db, min(horizon_hours, 24))
    if initial_aqi is None:
        return {
            "error": "no forecast surface available; generate a coupled forecast first (POST /api/forecast/coupled)",
            "frames": [],
        }

    fires = _fires_in_domain(db)
    # hourly met series: use the observed values as a flat first-guess with a
    # mild diurnal PBL wiggle (shallower at night, deeper around solar noon).
    hours = int(horizon_hours)
    speed_hourly = [wx["wind_speed"]] * hours
    dir_hourly = [wx["wind_direction"]] * hours
    precip_hourly = [wx["precipitation"]] * hours
    base_pbl = wx["pbl_height"]

    pbl_hourly = []
    for h in range(hours):
        hod = (start_hour + h) % 24
        if 7 <= hod <= 18:
            norm = max(0.0, np.cos(2 * np.pi * (hod - 13) / 22.0))
            depth = base_pbl * 0.5 + base_pbl * 1.2 * norm
        else:
            depth = base_pbl * 0.55
        pbl_hourly.append(float(max(200.0, depth)))

    result = run_dispersion_forecast(
        initial_aqi,
        NCR_BOUNDS["lat_min"], NCR_BOUNDS["lat_max"],
        NCR_BOUNDS["lon_min"], NCR_BOUNDS["lon_max"],
        GRID_STEP,
        wx["wind_speed"], wx["wind_direction"], base_pbl, wx["precipitation"],
        fires=fires,
        hours=hours,
        start_hour=start_hour,
        wind_hourly=speed_hourly,
        dir_hourly=dir_hourly,
        precip_hourly=precip_hourly,
        pbl_hourly=pbl_hourly,
    )

    lats, lons = build_grid()
    frames = []
    for fr in result["frames"]:
        cells = []
        aqi = fr["aqi"]
        for i in range(lats.size):
            for j in range(lons.size):
                v = int(aqi[i, j])
                category, _ = get_aqi_category(v)
                cells.append({
                    "lat": round(float(lats[i]), 4),
                    "lon": round(float(lons[j]), 4),
                    "aqi": v,
                    "aqi_category": category,
                })
        frames.append({
            "hour": fr["hour"],
            "hour_of_day": fr["hour_of_day"],
            "wind_speed": fr["wind_speed"],
            "wind_dir_deg": fr["wind_dir_deg"],
            "pbl_height": fr["pbl_height"],
            "precip_mm": fr["precip_mm"],
            "coupling": fr["coupling"],
            "aqi_mean": round(float(aqi.mean()), 1),
            "aqi_max": int(aqi.max()),
            "cells": cells,
        })

    return {
        "mode": "numerical_advection_diffusion",
        "horizon_hours": hours,
        "start_hour": start_hour,
        "domain": NCR_BOUNDS,
        "step_deg": GRID_STEP,
        "wx": {"wind_speed": round(wx["wind_speed"], 2), "wind_direction": round(wx["wind_direction"], 1),
               "pbl_height": round(wx["pbl_height"], 1), "precipitation": round(wx["precipitation"], 2)},
        "fire_count": len(fires),
        "fires": fires[:20],
        "dt_used": round(result["dt_used"], 1),
        "steps_per_hour": result["steps_per_hour"],
        "frames": frames,
    }
