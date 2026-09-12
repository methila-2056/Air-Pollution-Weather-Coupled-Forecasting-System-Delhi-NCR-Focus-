from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import PollutionReading, Station
from ..schemas.schemas import PollutionIngestResponse, PollutionReadingResponse, StationResponse
from ..services import cpcb_service
from ..services.cpcb_service import CpcbError

router = APIRouter()


@router.get("/pollution/latest", response_model=list[PollutionReadingResponse])
def pollution_latest(db: Session = Depends(get_db)):
    stations = {s.id: s for s in db.query(Station).all()}
    readings = (
        db.query(PollutionReading)
        .order_by(PollutionReading.station_id, PollutionReading.timestamp.desc())
        .all()
    )
    seen: set[int] = set()
    latest = []
    for reading in readings:
        if reading.station_id in seen:
            continue
        seen.add(reading.station_id)
        station = stations.get(reading.station_id)
        latest.append(PollutionReadingResponse(
            station_id=reading.station_id,
            station=station.name if station else str(reading.station_id),
            city=station.city if station else None,
            state=station.state if station else None,
            timestamp=reading.timestamp,
            pm25=reading.pm25,
            pm10=reading.pm10,
            o3=reading.o3,
            no2=reading.no2,
            so2=reading.so2,
            co=reading.co,
            aqi=reading.aqi,
        ))
    return latest


@router.get("/pollution/stations", response_model=list[StationResponse])
def pollution_stations(db: Session = Depends(get_db)):
    return db.query(Station).order_by(Station.city, Station.name).all()


@router.get("/pollution/{station_id}/history", response_model=list[PollutionReadingResponse])
def pollution_history(station_id: int, limit: int = 168, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station id '{station_id}' not found")
    limit = min(max(limit, 1), 1000)
    readings = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station_id)
        .order_by(PollutionReading.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        PollutionReadingResponse(
            station_id=reading.station_id,
            station=station.name,
            city=station.city,
            state=station.state,
            timestamp=reading.timestamp,
            pm25=reading.pm25,
            pm10=reading.pm10,
            o3=reading.o3,
            no2=reading.no2,
            so2=reading.so2,
            co=reading.co,
            aqi=reading.aqi,
        )
        for reading in readings
    ]


@router.post("/pollution/ingest", response_model=PollutionIngestResponse)
def pollution_ingest(db: Session = Depends(get_db)):
    try:
        summary = cpcb_service.run_ingestion(db)
    except CpcbError as exc:
        status_code = 400 if exc.kind == "missing_key" else 502
        raise HTTPException(status_code=status_code, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pollution ingestion failed: {exc}") from exc
    return summary
