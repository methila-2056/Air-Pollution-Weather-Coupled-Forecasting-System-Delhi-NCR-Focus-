from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import PollutionReading, Station
from ..schemas.schemas import (
    PollutionCoverageResponse,
    PollutionIngestResponse,
    PollutionReadingResponse,
    StationPollutionCoverage,
    StationResponse,
)
from ..services import cpcb_service
from ..services.cpcb_service import CpcbError

router = APIRouter()


@router.get("/pollution/latest", response_model=list[PollutionReadingResponse])
def pollution_latest(db: Session = Depends(get_db)):
    stations = {s.id: s for s in db.query(Station).all()}
    from sqlalchemy import func
    from sqlalchemy.orm import aliased

    latest_ts = (
        db.query(
            PollutionReading.station_id,
            func.max(PollutionReading.timestamp).label("max_ts"),
        )
        .group_by(PollutionReading.station_id)
        .subquery()
    )
    pr = aliased(PollutionReading)
    readings = (
        db.query(pr)
        .join(latest_ts, (pr.station_id == latest_ts.c.station_id) & (pr.timestamp == latest_ts.c.max_ts))
        .order_by(pr.station_id)
        .all()
    )
    return [
        PollutionReadingResponse(
            station_id=reading.station_id,
            station=stations[reading.station_id].name if reading.station_id in stations else str(reading.station_id),
            city=stations[reading.station_id].city if reading.station_id in stations else None,
            state=stations[reading.station_id].state if reading.station_id in stations else None,
            timestamp=reading.timestamp,
            pm25=reading.pm25,
            pm10=reading.pm10,
            o3=reading.o3,
            no2=reading.no2,
            so2=reading.so2,
            co=reading.co,
            aqi=reading.aqi,
            data_source=reading.data_source,
        )
        for reading in readings
    ]


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
            data_source=reading.data_source,
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


@router.get("/pollution/coverage", response_model=PollutionCoverageResponse)
def pollution_coverage(db: Session = Depends(get_db)):
    """Per-station monitoring-network coverage report (SIH26082 17/17 audit).

    Reports how many readings each station has, its data sources, recency and
    sufficiency, so incomplete coverage is visible and actionable instead of
    silently producing placeholder forecasts.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(hours=48)
    stations = db.query(Station).order_by(Station.city, Station.name).all()
    rows = {}
    for station in stations:
        readings = (
            db.query(PollutionReading)
            .filter(PollutionReading.station_id == station.id)
            .order_by(PollutionReading.timestamp.desc())
            .all()
        )
        if not readings:
            rows[station.id] = {
                "last": None,
                "count": 0,
                "sources": set(),
                "history_days": None,
                "recent": 0,
            }
            continue
        last = readings[0].timestamp
        recent = sum(1 for r in readings if r.timestamp is not None and r.timestamp >= cutoff)
        sources = {r.data_source or "legacy" for r in readings if r.data_source or True}
        span = (last - readings[-1].timestamp).total_seconds() / 86400.0
        rows[station.id] = {
            "last": last,
            "count": len(readings),
            "sources": sources,
            "history_days": round(abs(span), 1),
            "recent": recent,
        }

    def _sufficiency(info: dict) -> str:
        if info["count"] == 0:
            return "no_data"
        if info["recent"] == 0:
            return "stale"
        if info["recent"] < 8:
            return "limited"
        if info["count"] < 96:
            return "insufficient_history"
        return "adequate"

    stations_report = [
        StationPollutionCoverage(
            station_id=s.id,
            station=s.name,
            city=s.city,
            readings=rows[s.id]["count"],
            last_timestamp=rows[s.id]["last"],
            hours_since_last=(
                round((now - rows[s.id]["last"]).total_seconds() / 3600.0, 1)
                if rows[s.id]["last"] is not None
                else None
            ),
            history_days=rows[s.id]["history_days"],
            sufficiency=_sufficiency(rows[s.id]),
            sources=sorted(rows[s.id]["sources"]),
        )
        for s in stations
    ]
    with_readings = sum(1 for r in stations_report if r.readings > 0)
    recent = sum(1 for r in stations_report if r.hours_since_last is not None and r.hours_since_last <= 48)
    insufficient = sum(1 for r in stations_report if r.sufficiency != "adequate")
    total = max(1, len(stations_report))
    return PollutionCoverageResponse(
        stations_total=len(stations_report),
        stations_with_readings=with_readings,
        stations_recent=recent,
        stations_insufficient=insufficient,
        coverage_pct=round(100.0 * recent / total, 1),
        stations=stations_report,
    )
