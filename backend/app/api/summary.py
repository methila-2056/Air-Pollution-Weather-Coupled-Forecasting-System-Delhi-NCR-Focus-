from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Alert, FireReading, Forecast, ModelMetrics, PollutionReading, Station
from ..schemas.schemas import StationAQISummary, SummaryResponse
from ..services.aqi_calculator import get_aqi_category, get_dominant_pollutant

router = APIRouter()


@router.get("/summary", response_model=SummaryResponse)
def get_summary(db: Session = Depends(get_db)):
    """Aggregate NCR-wide key performance indicators for the dashboard.

    Centre-stage summary of the current air-quality scenario: how many
    stations are reporting, the current network-average AQI, the worst and
    best station, live fire forcing, open alerts, and forecast/model
    coverage. Backed entirely by persisted service-state tables.
    """
    stations = db.query(Station).order_by(Station.name).all()

    since = datetime.utcnow() - timedelta(hours=24)
    latest_by_station = {}
    for s in stations:
        r = (
            db.query(PollutionReading)
            .filter(PollutionReading.station_id == s.id, PollutionReading.timestamp >= since)
            .order_by(PollutionReading.timestamp.desc())
            .first()
        )
        if r is not None:
            latest_by_station[s.id] = r

    summaries = []
    for s in stations:
        r = latest_by_station.get(s.id)
        if r is None:
            continue
        if r.aqi is not None:
            category, _ = get_aqi_category(r.aqi)
        else:
            category = "Unknown"
        summaries.append(StationAQISummary(
            name=s.name,
            aqi=r.aqi,
            aqi_category=category,
            dominant_pollutant=get_dominant_pollutant(r.pm25, r.pm10, r.o3, r.no2, r.so2, r.co),
        ))

    aqi_values = [x.aqi for x in summaries if x.aqi is not None]
    worst = max(summaries, key=lambda x: x.aqi or -1) if summaries else None
    best = min(summaries, key=lambda x: x.aqi if x.aqi is not None else 10**9) if summaries else None

    active_fires = (
        db.query(FireReading)
        .filter(FireReading.acq_date >= since)
        .count()
    )
    open_alerts = db.query(Alert).count()
    models_trained = db.query(ModelMetrics).count()

    stations_with_forecast = (
        db.query(Forecast.station_id).distinct().count()
    )
    latest_forecast = db.query(Forecast).order_by(Forecast.forecast_timestamp.desc()).first()

    return SummaryResponse(
        generated_at=datetime.utcnow(),
        stations=len(stations),
        stations_with_readings=len(summaries),
        ncr_avg_aqi=round(float(sum(aqi_values) / len(aqi_values)), 1) if aqi_values else None,
        worst_station=worst,
        best_station=best,
        active_fires_24h=active_fires,
        open_alerts=open_alerts,
        models_trained=models_trained,
        forecast_coverage={
            "stations_with_forecast": stations_with_forecast,
            "latest_forecast_at": latest_forecast.forecast_timestamp if latest_forecast else None,
        },
    )