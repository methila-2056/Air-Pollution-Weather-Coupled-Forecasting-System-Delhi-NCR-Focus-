from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import PollutionReading, Station
from ..schemas.schemas import CurrentAQI, StationResponse
from ..services.aqi_calculator import calculate_aqi

router = APIRouter()

@router.get("/stations", response_model=list[StationResponse])
def get_stations(db: Session = Depends(get_db)):
    stations = db.query(Station).order_by(Station.name).all()
    return stations

@router.get("/stations/{station_name}", response_model=StationResponse)
def get_station_by_name(station_name: str, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
    return station

@router.get("/current/{station_name}", response_model=CurrentAQI)
def get_current_aqi(station_name: str, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
    reading = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station.id)
        .order_by(PollutionReading.timestamp.desc())
        .first()
    )
    if not reading:
        raise HTTPException(status_code=404, detail=f"No pollution readings for station '{station_name}'")
    aqi, category, dominant = calculate_aqi(
        reading.pm25, reading.pm10, reading.o3, reading.no2, reading.so2, reading.co
    )
    return CurrentAQI(
        station=station.name,
        timestamp=reading.timestamp,
        pm25=reading.pm25,
        pm10=reading.pm10,
        o3=reading.o3,
        no2=reading.no2,
        so2=reading.so2,
        co=reading.co,
        aqi=aqi or reading.aqi,
        aqi_category=category,
        dominant_pollutant=dominant,
    )
