"""Estimated Regional Pollution Transport Risk endpoint (AeroCast-NCR)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.schemas import TransportRiskCurrentResponse
from ..services.transport_risk_service import get_current_transport_risk

router = APIRouter()


@router.get("/transport-risk/current", response_model=TransportRiskCurrentResponse)
def get_transport_risk_current(
    hours: int = Query(
        default=72, ge=1, le=24 * 30,
        description="Fire look-back window (hours) for upwind fire activity",
    ),
    db: Session = Depends(get_db),
):
    """Current Estimated Regional Pollution Transport Risk (0-100, transparent).

    Built from stored FIRMS fire observations, Open-Meteo weather and CPCB
    pollution. This is an ESTIMATION engine, not a chemical plume model; the
    response disclaims any claim that a specific fire caused Delhi pollution.
    """
    return get_current_transport_risk(db, fire_window_hours=hours)
