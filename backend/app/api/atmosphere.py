"""Atmospheric-condition analysis API (GET /api/atmosphere/current)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.schemas import AtmosphereCurrentResponse
from ..services.atmosphere_service import get_current_atmosphere

router = APIRouter()


@router.get("/atmosphere/current", response_model=AtmosphereCurrentResponse)
def get_atmosphere_current(
    station_name: str | None = Query(
        default=None,
        description="Restrict to a single station (exact CPCB display name).",
    ),
    db: Session = Depends(get_db),
):
    """Current atmospheric-condition indicators for Delhi NCR.

    Computed exclusively from stored weather + pollution observations
    (no ML). Every indicator carries a provenance tag:
    OBSERVED / DERIVED / ESTIMATED. See ``methodology`` for the exact
    formulas and limitations.
    """
    result = get_current_atmosphere(db)
    if station_name:
        result["stations"] = [s for s in result["stations"] if s["station"] == station_name]
        result["summary"]["stations_analyzed"] = len(result["stations"])
    return result
