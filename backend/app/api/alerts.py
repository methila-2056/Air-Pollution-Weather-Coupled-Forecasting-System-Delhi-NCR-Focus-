from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.db_models import Alert, Station
from ..schemas.schemas import AlertResponse

router = APIRouter()

@router.get("/alerts", response_model=list[AlertResponse])
def get_alerts(db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(50).all()
    station_names = {}
    for a in alerts:
        if a.station_id not in station_names:
            station = db.query(Station).filter(Station.id == a.station_id).first()
            station_names[a.station_id] = station.name if station else f"station-{a.station_id}"
    return [AlertResponse(
        id=a.id,
        station=station_names.get(a.station_id, "unknown"),
        alert_level=a.alert_level,
        title=a.title,
        description=a.description or "",
        forecast_horizon_hours=a.forecast_horizon_hours,
        factors=a.factors,
        recommendation=a.recommendation,
        created_at=a.created_at,
    ) for a in alerts]