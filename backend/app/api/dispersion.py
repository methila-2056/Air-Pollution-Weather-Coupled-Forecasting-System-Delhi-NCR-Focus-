from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.dispersion_service import run_dispersion_forecast_service

router = APIRouter()

DISPERSION_TTL_SECONDS = 300


def dispersion_cache_key(horizon_hours: int, start_hour: int, frame_hours: list[int] | None) -> str:
    """Cache key for a dispersion response.

    Deliberately exported: the control-room pre-warm has to build *exactly* the
    keys this endpoint serves or it burns its CPU warming entries nothing reads.
    The frame set is part of the key because it is part of the response, and it
    is sorted here so two callers asking for the same hours in a different order
    share one entry instead of solving the PDE twice.
    """
    frame_part = "-".join(str(h) for h in sorted(frame_hours)) if frame_hours else "all"
    return f"dispersion:{horizon_hours}:{start_hour}:{frame_part}"


def _parse_frame_hours(raw: str | None) -> list[int] | None:
    """Parse ``?frame_hours=6,12,24`` into a sorted list of hours.

    Returns ``None`` (i.e. "every frame") for an absent or unparseable value so
    a malformed query parameter degrades to the full response instead of an
    empty one. Out-of-range hours are dropped rather than clamped — a request
    for hour 96 of a 72 h run should not silently return hour 72.
    """
    if raw is None:
        return None
    hours: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            return None
        if value < 0:
            return None
        hours.add(value)
    return sorted(hours) or None


@router.get("/dispersion/forecast", response_model=dict)
def get_dispersion_forecast(
    horizon_hours: int = Query(default=72, ge=6, le=72),
    start_hour: int = Query(default=8, ge=0, le=23),
    frame_hours: str | None = Query(
        default=None,
        description=(
            "Comma-separated forecast hours whose grid cells should be "
            "serialised, e.g. '6,12,24,48,72'. The solver always integrates the "
            "full horizon; this only limits how many per-cell AQI grids are "
            "built, which is what makes the response expensive. Omit for every "
            "hourly frame."
        ),
    ),
    db: Session = Depends(get_db),
):
    """Numerical (advection-diffusion) forecast of pollution plumes over NCR.

    Runs the grid-based transport core on the latest persisted AQI surface with
    live PBL / wind / precipitation / stubble-fire sources, producing hourly
    AQI grid frames over the 72-hour horizon. Aerosol loading feeds back into
    PBL suppression and stability (two-way coupled meteorology-chemistry).

    ``frame_hours_available`` always lists every hour the run produced, so a
    client can discover the full set and then request only the frames it
    renders instead of downloading all 72 grids.
    """
    from ..services.ttl_cache import cached

    hours = _parse_frame_hours(frame_hours)
    return cached(
        dispersion_cache_key(horizon_hours, start_hour, hours),
        DISPERSION_TTL_SECONDS,
        lambda: run_dispersion_forecast_service(
            db, horizon_hours=horizon_hours, start_hour=start_hour, frame_hours=hours
        ),
    )
