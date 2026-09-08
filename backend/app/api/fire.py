import math
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import FireReading, Station, WeatherReading
from ..schemas.schemas import FireActivityResponse, PlumeRiskResponse, TransportDirectionResponse

router = APIRouter()

DELHI_LAT = 28.6139
DELHI_LON = 77.2090

COMPASS_POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

UPWIND_SOURCES = {"N", "NNE", "NW", "NNW", "W", "WNW"}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))

def estimate_transport_direction(wind_direction):
    if wind_direction is None:
        return {"source": "Unknown", "target": "Unknown", "label": "Unknown"}
    from_idx = int((float(wind_direction) % 360) / 22.5 + 0.5) % 16
    to_idx = (from_idx + 8) % 16
    source = COMPASS_POINTS[from_idx]
    target = COMPASS_POINTS[to_idx]
    return {"source": source, "target": target, "label": f"{source} \u2192 {target}"}

def _latest_wind(db: Session, station_name: str = None):
    query = db.query(WeatherReading)
    if station_name:
        station = db.query(Station).filter(Station.name == station_name).first()
        if station:
            query = query.filter(WeatherReading.station_id == station.id)
    reading = query.order_by(WeatherReading.timestamp.desc()).first()
    if not reading:
        return None, None, None
    return reading, reading.wind_speed, reading.wind_direction

@router.get("/fire-activity", response_model=FireActivityResponse)
def get_fire_activity(db: Session = Depends(get_db)):
    fires = db.query(FireReading).order_by(FireReading.acq_date.desc()).limit(1000).all()
    if not fires:
        return FireActivityResponse(total_fires=0, high_confidence_fires=0, mean_frp=0.0, region="Delhi NCR", date=datetime.now())
    high_conf = sum(1 for f in fires if f.confidence and f.confidence.lower() == "high")
    frps = [f.frp for f in fires if f.frp is not None]
    return FireActivityResponse(
        total_fires=len(fires),
        high_confidence_fires=high_conf,
        mean_frp=sum(frps) / len(frps) if frps else 0.0,
        region="Punjab/Haryana/Rajasthan",
        date=fires[0].acq_date if fires else datetime.now(),
    )

@router.get("/fire/transport", response_model=TransportDirectionResponse)
def get_transport_direction(station_name: str = "Anand Vihar", db: Session = Depends(get_db)):
    reading, speed, wind_deg = _latest_wind(db, station_name)
    est = estimate_transport_direction(wind_deg)
    basis = "live weather data"
    if wind_deg is None:
        est = {"source": "NW", "target": "SE", "label": "NW \u2192 SE"}
        basis = "climatological default (NW winter winds)"
    return TransportDirectionResponse(
        station=station_name,
        from_direction=est["source"],
        to_direction=est["target"],
        label=est["label"],
        wind_speed=speed,
        wind_direction=wind_deg,
        basis=basis,
    )

@router.get("/plume-risk", response_model=PlumeRiskResponse)
def get_plume_risk(db: Session = Depends(get_db)):
    fires = db.query(FireReading).order_by(FireReading.acq_date.desc()).limit(500).all()
    if not fires:
        return PlumeRiskResponse(
            risk_level="LOW",
            risk_score=0.1,
            fire_count=0,
            transport_direction="Unknown",
            wind_speed=0,
            distance_nearest_fire=999,
            confidence=0,
            factors=["No fire data available"],
        )

    fire_count = len(fires)
    distances = [haversine(DELHI_LAT, DELHI_LON, f.latitude, f.longitude) for f in fires]
    min_dist = min(distances)

    reading, wind_speed, wind_deg = _latest_wind(db)
    est = estimate_transport_direction(wind_deg)
    if wind_deg is None:
        est = {"source": "NW", "target": "SE", "label": "NW \u2192 SE"}
    transport_direction = est["label"]

    base = (fire_count / 100) * (1 / max(min_dist / 100, 0.1))
    alignment = 1.0 if est["source"] in UPWIND_SOURCES else 0.9
    risk_score = min(1.0, base * alignment)

    if risk_score > 0.7:
        risk_level = "HIGH"
    elif risk_score > 0.4:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    factors = []
    if fire_count > 50:
        factors.append(f"High fire activity: {fire_count} active hotspots")
    if min_dist < 200:
        factors.append(f"Nearest fire only {min_dist:.0f}km from Delhi")
    if wind_deg is not None:
        factors.append(f"Wind {wind_speed:.1f} m/s from {est['source']}; plume transport toward {est['target']}")
    else:
        factors.append("Wind data unavailable; assuming climatological NW \u2192 SE transport")

    return PlumeRiskResponse(
        risk_level=risk_level,
        risk_score=round(risk_score, 3),
        fire_count=fire_count,
        transport_direction=transport_direction,
        wind_speed=round(wind_speed or 0, 1),
        distance_nearest_fire=round(min_dist, 1),
        confidence=round(min(risk_score, 0.95), 2),
        factors=factors,
    )
