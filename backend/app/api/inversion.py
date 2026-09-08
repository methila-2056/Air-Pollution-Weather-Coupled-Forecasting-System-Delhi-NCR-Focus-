from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Station, WeatherReading
from ..schemas.schemas import InversionResponse

router = APIRouter()

def classify_inversion(pbl_height):
    if pbl_height is None:
        return "unknown", "unknown", "unknown"
    if pbl_height < 150:
        return True, "Strong", "HIGH"
    elif pbl_height < 300:
        return True, "Moderate", "MEDIUM"
    elif pbl_height < 500:
        return True, "Weak", "LOW"
    else:
        return False, "None", "MINIMAL"

@router.get("/inversion/{station_name}", response_model=InversionResponse)
def get_inversion(station_name: str, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
    reading = db.query(WeatherReading).filter(WeatherReading.station_id == station.id).order_by(WeatherReading.timestamp.desc()).first()
    if not reading:
        raise HTTPException(status_code=404, detail=f"No weather data for station '{station_name}'")
    detected, strength, risk = classify_inversion(reading.pbl_height)
    return InversionResponse(
        station=station_name,
        timestamp=reading.timestamp,
        pbl_height=reading.pbl_height,
        inversion_detected=detected,
        inversion_strength=strength,
        trapping_risk=risk,
    )
