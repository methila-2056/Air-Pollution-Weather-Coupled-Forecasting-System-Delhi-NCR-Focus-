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
    result = _current_atmosphere_cached(db)
    if station_name:
        stations = [s for s in result["stations"] if s["station"] == station_name]
        out = dict(result)
        out["stations"] = stations
        out["summary"] = dict(result["summary"])
        out["summary"]["stations_analyzed"] = len(stations)
        return out
    return result


def _current_atmosphere_cached(db):
    """Compute once per TTL window — see ``services.ttl_cache``.

    Building the profile for all 17 stations means ~50 sequential queries to
    the pooled Neon Postgres (~11 s); the underlying observations only change
    on the 3-hour refresh cadence, so cache the serialisable result.
    """
    from ..services.ttl_cache import cached

    return cached("atmosphere:current", 300, lambda: get_current_atmosphere(db))
