from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.db_models import ModelMetrics
from ..schemas.schemas import ModelMetricCreate, ModelMetricResponse

router = APIRouter()

def _to_response(m) -> ModelMetricResponse:
    return ModelMetricResponse(
        id=m.id,
        model_name=m.model_name,
        pollutant=m.pollutant,
        horizon_hours=m.horizon_hours,
        mae=m.mae,
        rmse=m.rmse,
        r2=m.r2,
        mape=m.mape,
        test_period_start=m.test_period_start,
        test_period_end=m.test_period_end,
        trained_at=m.trained_at,
    )

@router.get("/model/metrics", response_model=list[ModelMetricResponse])
def get_model_metrics(db: Session = Depends(get_db)):
    metrics = db.query(ModelMetrics).order_by(ModelMetrics.trained_at.desc(), ModelMetrics.id.desc()).all()
    return [_to_response(m) for m in metrics]

@router.post("/model/metrics", response_model=ModelMetricResponse, status_code=201)
def save_model_metrics(metric: ModelMetricCreate, db: Session = Depends(get_db)):
    if not metric.model_name or not metric.pollutant:
        raise HTTPException(status_code=400, detail="model_name and pollutant are required")
    if not metric.horizon_hours:
        raise HTTPException(status_code=400, detail="horizon_hours is required")
    record = ModelMetrics(
        model_name=metric.model_name,
        pollutant=metric.pollutant,
        horizon_hours=metric.horizon_hours,
        mae=metric.mae,
        rmse=metric.rmse,
        r2=metric.r2,
        mape=metric.mape,
        test_period_start=metric.test_period_start,
        test_period_end=metric.test_period_end,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_response(record)