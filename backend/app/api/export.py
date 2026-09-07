from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Forecast, Station

router = APIRouter()


def _station_or_404(db: Session, station_name: str) -> Station:
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
    return station


@router.get("/export/forecast.csv")
def export_forecast_csv(
    station_name: str = Query(default=...),
    hours: int = Query(default=72, ge=1, le=720),
    db: Session = Depends(get_db),
):
    """Download persisted forecasts for a station as a CSV file.

    Useful for offline analysis, PS deliverables, or handing the forecast
    series to downstream tools. Returns a plain-text CSV with an explicit
    Content-Disposition filename.
    """
    station = _station_or_404(db, station_name)
    start = datetime.utcnow() - timedelta(hours=hours)
    forecasts = (
        db.query(Forecast)
        .filter(
            Forecast.station_id == station.id,
            Forecast.forecast_timestamp >= start,
        )
        .order_by(Forecast.forecast_timestamp)
        .all()
    )
    if not forecasts:
        raise HTTPException(status_code=404, detail=f"No forecasts in the requested window for '{station_name}'")

    header = (
        "timestamp,horizon_hours,pm25_pred,pm10_pred,o3_pred,no2_pred,so2_pred,"
        "co_pred,aqi_pred,aqi_category,dominant_pollutant,coupling_stability"
    )
    rows = [header]
    for f in forecasts:
        rows.append(",".join([
            str(f.forecast_timestamp.isoformat()),
            str(f.horizon_hours),
            _num(f.pm25_pred), _num(f.pm10_pred), _num(f.o3_pred),
            _num(f.no2_pred), _num(f.so2_pred), _num(f.co_pred),
            _num(f.aqi_pred),
            f.aqi_category or "",
            f.dominant_pollutant or "",
            _num(f.coupling_stability),
        ]))

    safe_name = station_name.replace(" ", "_").lower()
    return Response(
        content="\n".join(rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="forecast_{safe_name}_{hours}h.csv"',
        },
    )


def _num(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)