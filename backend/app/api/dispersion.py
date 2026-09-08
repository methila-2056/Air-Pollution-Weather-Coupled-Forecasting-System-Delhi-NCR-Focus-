from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.dispersion_service import run_dispersion_forecast_service

router = APIRouter()


@router.get("/dispersion/forecast", response_model=dict)
def get_dispersion_forecast(
    horizon_hours: int = Query(default=72, ge=6, le=72),
    start_hour: int = Query(default=8, ge=0, le=23),
    db: Session = Depends(get_db),
):
    """Numerical (advection-diffusion) forecast of pollution plumes over NCR.

    Runs the grid-based transport core on the latest persisted AQI surface with
    live PBL / wind / precipitation / stubble-fire sources, producing hourly
    AQI grid frames over the 72-hour horizon. Aerosol loading feeds back into
    PBL suppression and stability (two-way coupled meteorology-chemistry).
    """
    return run_dispersion_forecast_service(db, horizon_hours=horizon_hours, start_hour=start_hour)
