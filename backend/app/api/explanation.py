from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Station
from ..schemas.schemas import ExplanationResponse
from ..services import explanation_service, forecast_service

router = APIRouter()

@router.get("/explanation/{station_name}", response_model=ExplanationResponse)
def get_explanation(station_name: str, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")

    features = forecast_service.build_features_from_db(db, station.id)
    model = forecast_service.load_pollutant_model("pm25", 24)
    prediction = forecast_service.predict_pollutants(features, horizons=[24])[0]

    if model is not None:
        top_features = explanation_service.explain_prediction(model, features)
    else:
        top_features = explanation_service.explain_fallback(features)

    natural_language = explanation_service.generate_natural_language(features, top_features, prediction)

    return ExplanationResponse(
        station=station.name,
        timestamp=datetime.utcnow(),
        prediction=prediction,
        top_features=top_features,
        natural_language=natural_language,
    )
