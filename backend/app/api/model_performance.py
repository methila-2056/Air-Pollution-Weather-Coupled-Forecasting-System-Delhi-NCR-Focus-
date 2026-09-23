"""REST API for model performance metrics.

Endpoint: GET /api/model/performance?target=pm25
"""

from fastapi import APIRouter, HTTPException, Query

from ..schemas.schemas import ModelPerformanceResponse
from ..services import model_performance_service as svc

router = APIRouter()


@router.get("/model/performance", response_model=ModelPerformanceResponse)
def get_model_performance(
    target: str = Query(default="pm25", description="Pollutant target: pm25 pm10 o3 no2 so2 co"),
) -> ModelPerformanceResponse:
    """Return the actual measured model performance dataset.

    All metrics are the measured values produced by evaluating the deployed
    models on the held-out chronological test split (never used during
    training). Every field is therefore a recorded observation, not a
    calculation performed at request time.
    """
    try:
        return svc.load_model_performance(target=target)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
