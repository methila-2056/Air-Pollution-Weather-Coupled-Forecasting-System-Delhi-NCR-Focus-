"""What-if scenario analysis endpoints (AeroCast-NCR).

Endpoint: POST /api/scenario/analysis
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Station
from ..schemas.schemas import ScenarioAnalysisRequest, ScenarioAnalysisResponse
from ..services import scenario_service as svc

router = APIRouter()


@router.post("/scenario/analysis", response_model=ScenarioAnalysisResponse)
def post_scenario_analysis(
    req: ScenarioAnalysisRequest,
    db: Session = Depends(get_db),
):
    """Compare a baseline forecast against a what-if scenario produced by
    changing ONLY the requested environmental inputs (wind speed, wind
    direction, PBL height, regional fire activity, inversion).

    The response is explicitly labelled ``SCENARIO ANALYSIS`` and never claims
    causation. The scenario is executed entirely in memory against a copy of
    the forecast feature row: this module issues only SELECT queries and never
    writes to the database, so observational tables are untouched.
    """
    if req.station_name is not None:
        station = db.query(Station).filter(Station.name == req.station_name).first()
        if not station:
            raise HTTPException(
                status_code=404, detail=f"Station '{req.station_name}' not found"
            )
        target = req.station_name
    else:
        first = db.query(Station).order_by(Station.id).first()
        if not first:
            raise HTTPException(status_code=503, detail="No stations available; seed the database first")
        target = first.name

    try:
        payload = svc.run_scenario_analysis(db, target, req.hours, req.changes)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("station_not_found"):
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # defensive: pipeline surprises
        raise HTTPException(status_code=500, detail=f"Scenario analysis failed: {exc}") from exc

    return payload
