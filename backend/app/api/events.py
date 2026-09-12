"""Pollution-event detection endpoints (AeroCast-NCR).

Endpoint: GET /api/events/current?station_name=...&hours=48
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Station
from ..schemas.schemas import PollutionEventsCurrentResponse
from ..services import pollution_event_service as svc

router = APIRouter()


@router.get("/events/current", response_model=PollutionEventsCurrentResponse)
def get_current_events(
    station_name: str | None = Query(default=None, description="Station name (defaults to first station)"),
    hours: int = Query(default=48, ge=1, le=72, description="Forecast horizon (hours) to scan for events"),
    db: Session = Depends(get_db),
):
    """Current/upcoming pollution events (surge / relief / high-risk episode).

    Detected from the trained PM2.5 forecast series plus the currently stored
    atmosphere (ventilation, PBL, inversion, wind, regional transport risk).
    Every event carries the actual stored values that triggered it, a confidence
    object derived from the model's split-conformal interval, and the full
    threshold documentation — no invented numbers.
    """
    if station_name is not None:
        station = db.query(Station).filter(Station.name == station_name).first()
        if not station:
            raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
        target = station_name
    else:
        first = db.query(Station).order_by(Station.id).first()
        if not first:
            raise HTTPException(status_code=503, detail="No stations available; seed the database first")
        target = first.name

    try:
        payload = svc.detect_current_events(db, target, horizon_hours=hours)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("station_not_found"):
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # defensive: pipeline surprises
        raise HTTPException(status_code=500, detail=f"Pollution-event detection failed: {exc}") from exc

    return payload
