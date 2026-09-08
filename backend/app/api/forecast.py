from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Alert, Forecast, PollutionReading, Station
from ..schemas.schemas import (
    ForecastComparisonPoint,
    ForecastComparisonResponse,
    ForecastGenerateRequest,
    ForecastGenerateResponse,
    ForecastPoint,
)
from ..services import alert_service, forecast_service

router = APIRouter()

def _round_hour(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.replace(minute=0, second=0, microsecond=0)

def _station_or_404(db: Session, station_name: str) -> Station:
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
    return station

def _to_forecast_point(f) -> ForecastPoint:
    return ForecastPoint(
        timestamp=f.forecast_timestamp,
        horizon_hours=f.horizon_hours,
        pm25_pred=f.pm25_pred,
        pm10_pred=f.pm10_pred,
        o3_pred=f.o3_pred,
        no2_pred=f.no2_pred,
        so2_pred=f.so2_pred,
        co_pred=f.co_pred,
        aqi_pred=f.aqi_pred,
        aqi_category=f.aqi_category or "",
        dominant_pollutant=f.dominant_pollutant,
        coupling_stability=f.coupling_stability,
    )

@router.post("/forecast/coupled", response_model=dict)
def generate_coupled_forecast(
    req: ForecastGenerateRequest = ForecastGenerateRequest(),
    db: Session = Depends(get_db),
):
    """Run the time-stepped two-way coupled weather-chemistry forecast.

    Steps meteorology + chemistry forward hour-by-hour, correcting PBL height,
    temperature, and stability from the freshly forecast aerosol load, then
    persists the coupled forecast points. Returns both the coupled series and
    the direct (uncoupled) series for comparison, plus the feedback path.
    """
    if not req.horizons:
        raise HTTPException(status_code=400, detail="horizons must be a non-empty list")
    invalid = [h for h in req.horizons if not 1 <= h <= 72]
    if invalid:
        raise HTTPException(status_code=400, detail=f"invalid horizon values: {invalid}")

    if req.station_name:
        station = _station_or_404(db, req.station_name)
    else:
        station = db.query(Station).order_by(Station.id).first()
        if not station:
            raise HTTPException(status_code=503, detail="No stations available; seed the database first")

    horizons = list(dict.fromkeys(req.horizons))
    result = forecast_service.generate_coupled_forecast(db, station.id, horizons)
    rows = forecast_service.save_coupled_forecasts(db, station.id, result["coupled"])

    return {
        "station": station.name,
        "generated_at": datetime.utcnow(),
        "horizons": horizons,
        "mode": "coupled-two-way",
        "coupled": result["coupled"],
        "uncoupled": result["uncoupled"],
        "feedback_path": result["feedback_path"],
        "saved_points": len(rows),
    }

@router.post("/forecast/generate", response_model=ForecastGenerateResponse)
def generate_forecast(
    req: ForecastGenerateRequest = ForecastGenerateRequest(),
    db: Session = Depends(get_db),
):
    if not req.horizons:
        raise HTTPException(status_code=400, detail="horizons must be a non-empty list")
    invalid = [h for h in req.horizons if not 1 <= h <= 72]
    if invalid:
        raise HTTPException(status_code=400, detail=f"invalid horizon values: {invalid}")

    if req.station_name:
        station = _station_or_404(db, req.station_name)
    else:
        station = db.query(Station).order_by(Station.id).first()
        if not station:
            raise HTTPException(status_code=503, detail="No stations available; seed the database first")

    horizons = list(dict.fromkeys(req.horizons))
    _, predictions = forecast_service.generate_forecast(db, station.id, horizons)

    weather = forecast_service.get_weather_context(db, station.id)
    fire = forecast_service.get_fire_context(db)
    aqi_series = [p["aqi_pred"] for p in predictions]
    if len(aqi_series) >= 2:
        if aqi_series[-1] > aqi_series[0] * 1.05:
            trend = "rising"
        elif aqi_series[-1] < aqi_series[0] * 0.95:
            trend = "falling"
        else:
            trend = "stable"
    else:
        trend = "stable"

    worst = max(predictions, key=lambda p: p["aqi_pred"])
    alert_inputs = {**worst, "trend": trend}
    for alert in alert_service.generate_alerts(alert_inputs, weather, fire):
        db.add(Alert(
            station_id=station.id,
            alert_level=alert["alert_level"],
            title=alert["title"],
            description=alert.get("description", ""),
            forecast_horizon_hours=alert.get("forecast_horizon_hours"),
            factors=alert.get("factors"),
            recommendation=alert.get("recommendation"),
        ))
    db.commit()

    return ForecastGenerateResponse(
        station=station.name,
        generated_at=datetime.utcnow(),
        horizons=horizons,
        forecasts=[
            ForecastPoint(
                timestamp=datetime.utcnow() + timedelta(hours=p["horizon_hours"]),
                horizon_hours=p["horizon_hours"],
                pm25_pred=p["pm25_pred"],
                pm10_pred=p["pm10_pred"],
                o3_pred=p["o3_pred"],
                no2_pred=p["no2_pred"],
                so2_pred=p.get("so2_pred"),
                co_pred=p.get("co_pred"),
                aqi_pred=p["aqi_pred"],
                aqi_category=p["aqi_category"],
            )
            for p in predictions
        ],
    )

@router.get("/forecast/comparison/{station_name}", response_model=ForecastComparisonResponse)
def get_forecast_comparison(
    station_name: str,
    hours: int = Query(default=72, ge=1, le=720),
    db: Session = Depends(get_db),
):
    station = _station_or_404(db, station_name)
    start = datetime.utcnow() - timedelta(hours=hours)

    forecasts = (
        db.query(Forecast)
        .filter(Forecast.station_id == station.id, Forecast.forecast_timestamp >= start)
        .order_by(Forecast.forecast_timestamp)
        .all()
    )
    readings = (
        db.query(PollutionReading)
        .filter(
            PollutionReading.station_id == station.id,
            PollutionReading.timestamp >= start - timedelta(hours=2),
        )
        .order_by(PollutionReading.timestamp)
        .all()
    )

    reading_by_hour = {}
    for r in readings:
        key = _round_hour(r.timestamp)
        reading_by_hour.setdefault(key, r)

    points = []
    for f in forecasts:
        key = _round_hour(f.forecast_timestamp)
        actual = reading_by_hour.get(key)
        delta = None
        if actual and actual.pm25 is not None and f.pm25_pred is not None:
            delta = round(f.pm25_pred - actual.pm25, 1)
        points.append(ForecastComparisonPoint(
            timestamp=f.forecast_timestamp,
            actual_aqi=actual.aqi if actual else None,
            predicted_aqi=f.aqi_pred,
            actual_pm25=actual.pm25 if actual else None,
            predicted_pm25=f.pm25_pred,
            delta=delta,
        ))

    if not points:
        raise HTTPException(status_code=404, detail=f"No forecasts within the last {hours} hours for station '{station_name}'")
    return ForecastComparisonResponse(station=station.name, points=points)

@router.get("/forecast/ncr", response_model=dict[str, list[ForecastPoint]])
def get_ncr_forecast(hours: int = Query(default=72, ge=1, le=72), db: Session = Depends(get_db)):
    stations = db.query(Station).order_by(Station.name).all()
    result = {}
    for station in stations:
        forecasts = (
            db.query(Forecast)
            .filter(Forecast.station_id == station.id, Forecast.horizon_hours <= hours)
            .order_by(Forecast.forecast_timestamp)
            .all()
        )
        result[station.name] = [_to_forecast_point(f) for f in forecasts]
    return result

@router.get("/forecast/{station_name}", response_model=list[ForecastPoint])
def get_forecast(station_name: str, hours: int = Query(default=72, ge=1, le=72), db: Session = Depends(get_db)):
    station = _station_or_404(db, station_name)
    forecasts = (
        db.query(Forecast)
        .filter(Forecast.station_id == station.id, Forecast.horizon_hours <= hours)
        .order_by(Forecast.forecast_timestamp)
        .all()
    )
    return [_to_forecast_point(f) for f in forecasts]
