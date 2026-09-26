"""Station-wide alert feed.

The rules live in :mod:`..services.alert_service`; this endpoint evaluates them
for **every** station on demand rather than replaying a persisted ``alerts``
table. The persisted table is only appended to by ``POST /api/forecast/generate``
for a single station, so reading it back left the Alerts view frozen on one
station's snapshot. Evaluating live keeps all 17 NCR stations represented and
makes the feed reflect the current forecast run.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Station
from ..schemas.schemas import AlertResponse
from ..services import alert_service

router = APIRouter()


@router.get("/alerts", response_model=list[AlertResponse])
def get_alerts(
    station: str | None = Query(
        default=None,
        description="Restrict the feed to one station name (default: every station).",
    ),
    db: Session = Depends(get_db),
):
    """Active pollution alerts for the whole NCR network.

    Cached for 120 s inside :func:`..services.alert_service.all_station_alerts`,
    keyed on the full unfiltered sweep: a ``?station=`` filter reuses that one
    sweep instead of recomputing the whole network, and ``/api/summary``'s
    ``open_alerts`` shares the same cache entry rather than paying for its own
    pass over all 17 stations.
    """
    if station and not db.query(Station).filter(Station.name == station).first():
        raise HTTPException(status_code=404, detail=f"Station '{station}' not found")

    rows = alert_service.all_station_alerts(db, station)
    return [
        AlertResponse(
            id=0,
            station=row["station"],
            alert_level=row["alert_level"],
            title=row["title"],
            description=row.get("description") or "",
            forecast_horizon_hours=row.get("forecast_horizon_hours"),
            factors=row.get("factors"),
            recommendation=row.get("recommendation"),
            created_at=row["created_at"],
        )
        for row in rows
    ]
