"""GRAded Response Action Plan (GRAP) endpoints for Delhi NCR.

Exposes the static CAQM stage matrix and live assessments. The live assessment
is derived from persisted observation state (24-hour NCR-average AQI, latest
PBL-derived inversion proxy and recent FIRMS fire intensity) with no external
network calls, so it is safe to call from the dashboard on every refresh.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import FireReading, PollutionReading, Station, WeatherReading
from ..schemas.schemas import GrapAssessment, GrapStageOut, GrapStagesResponse
from ..services.aqi_calculator import calculate_aqi, get_aqi_category, get_dominant_pollutant
from ..services.grap_service import assess_grap, get_grap_stages

router = APIRouter()

INVERSION_PBL_REFERENCE_M = 500  # mirrors forecast_service's PBL proxy


def _inversion_proxy_from_pbl(pbl_height_m: float | None) -> float | None:
    """Normalised 0..1 inversion proxy from the shallowest recent PBL height."""
    if pbl_height_m is None or pbl_height_m != pbl_height_m:
        return None
    return max(0.0, min(1.0, (INVERSION_PBL_REFERENCE_M - pbl_height_m) / INVERSION_PBL_REFERENCE_M))


@router.get("/grap/stages", response_model=GrapStagesResponse)
def grap_stages():
    """The full GRAP stage matrix (not-invoked + Stages I-IV)."""
    return GrapStagesResponse(stages=[GrapStageOut(**s) for s in get_grap_stages()])


@router.get("/grap/current", response_model=GrapAssessment)
def grap_current(db: Session = Depends(get_db)):
    """Assess the operative GRAP stage for NCR from current persisted state."""
    from ..services.ttl_cache import cached

    return cached("grap:current", 300, lambda: _compute_grap_current(db))


def _compute_grap_current(db: Session) -> GrapAssessment:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)

    stations = db.query(Station).order_by(Station.name).all()
    aqi_values: list[int] = []
    latest: list[PollutionReading] = []
    for s in stations:
        r = (
            db.query(PollutionReading)
            .filter(PollutionReading.station_id == s.id, PollutionReading.timestamp >= since)
            .order_by(PollutionReading.timestamp.desc())
            .first()
        )
        if r is not None:
            latest.append(r)
            if r.aqi is not None:
                aqi_values.append(r.aqi)

    ncr_aqi = round(sum(aqi_values) / len(aqi_values)) if aqi_values else None
    category, _ = get_aqi_category(ncr_aqi) if ncr_aqi is not None else (None, None)

    def _avg(attr):
        values = [getattr(r, attr) for r in latest if getattr(r, attr) is not None]
        return sum(values) / len(values) if values else None

    dominant = get_dominant_pollutant(
        _avg("pm25"), _avg("pm10"), _avg("o3"), _avg("no2"), _avg("so2"), _avg("co"),
    ) if latest else None

    shallowest_pbl = (
        db.query(func.min(WeatherReading.pbl_height))
        .filter(WeatherReading.timestamp >= since)
        .scalar()
    )
    mean_frp = (
        db.query(func.avg(FireReading.frp))
        .filter(FireReading.acq_date >= since)
        .scalar()
    )
    fire_mean_frp_mw = float(mean_frp) if mean_frp is not None else None

    result = assess_grap(
        aqi=ncr_aqi,
        inversion_strength=_inversion_proxy_from_pbl(shallowest_pbl),
        fire_mean_frp_mw=fire_mean_frp_mw,
    )
    result["aqi_category"] = category
    result["dominant_pollutant"] = dominant
    return GrapAssessment(**result)


@router.get("/grap/{station_name}", response_model=GrapAssessment)
def grap_for_station(station_name: str, db: Session = Depends(get_db)):
    """Assess the operative GRAP stage for one station's latest reading."""
    station = db.query(Station).filter(func.lower(Station.name) == station_name.lower()).first()
    if station is None:
        raise HTTPException(status_code=404, detail=f"Unknown station: {station_name}")

    r = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station.id)
        .order_by(PollutionReading.timestamp.desc())
        .first()
    )
    aqi, category, dominant = calculate_aqi(
        r.pm25 if r else None, r.pm10 if r else None, r.o3 if r else None,
        r.no2 if r else None, r.so2 if r else None, r.co if r else None,
    ) if r else (None, None, None)

    latest_pbl = (
        db.query(WeatherReading.pbl_height)
        .filter(WeatherReading.station_id == station.id)
        .order_by(WeatherReading.timestamp.desc())
        .first()
    )

    result = assess_grap(
        aqi=aqi if r else None,
        inversion_strength=_inversion_proxy_from_pbl(latest_pbl[0] if latest_pbl else None),
        fire_mean_frp_mw=None,
    )
    result["aqi_category"] = category if category and category != "Unknown" else None
    result["dominant_pollutant"] = dominant
    return GrapAssessment(**result)
