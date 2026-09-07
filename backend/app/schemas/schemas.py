from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class StationResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    city: str

class CurrentAQI(BaseModel):
    station: str
    timestamp: datetime
    pm25: Optional[float]
    pm10: Optional[float]
    o3: Optional[float]
    no2: Optional[float]
    so2: Optional[float]
    co: Optional[float]
    aqi: Optional[int]
    aqi_category: str
    dominant_pollutant: str

class ForecastPoint(BaseModel):
    timestamp: datetime
    horizon_hours: int
    pm25_pred: Optional[float]
    pm10_pred: Optional[float]
    o3_pred: Optional[float]
    no2_pred: Optional[float]
    aqi_pred: Optional[int]
    aqi_category: str

class ForecastGenerateRequest(BaseModel):
    station_name: Optional[str] = None
    horizons: List[int] = Field(default_factory=lambda: [1, 6, 12, 24, 48, 72])

class ForecastGenerateResponse(BaseModel):
    station: str
    generated_at: datetime
    horizons: List[int]
    forecasts: List[ForecastPoint]

class ForecastComparisonPoint(BaseModel):
    timestamp: datetime
    actual_aqi: Optional[int]
    predicted_aqi: Optional[int]
    actual_pm25: Optional[float]
    predicted_pm25: Optional[float]
    delta: Optional[float]

class ForecastComparisonResponse(BaseModel):
    station: str
    points: List[ForecastComparisonPoint]

class WeatherResponse(BaseModel):
    station: str
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]
    pressure_msl: Optional[float]
    wind_speed: Optional[float]
    wind_direction: Optional[float]
    precipitation: Optional[float]
    cloud_cover: Optional[float]

class WeatherDetailResponse(BaseModel):
    station: str
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]
    pressure_msl: Optional[float]
    surface_pressure: Optional[float]
    wind_speed: Optional[float]
    wind_direction: Optional[float]
    precipitation: Optional[float]
    cloud_cover: Optional[float]
    pbl_height: Optional[float]

class InversionResponse(BaseModel):
    station: str
    timestamp: datetime
    pbl_height: Optional[float]
    inversion_detected: bool
    inversion_strength: str
    trapping_risk: str

class FireActivityResponse(BaseModel):
    total_fires: int
    high_confidence_fires: int
    mean_frp: float
    region: str
    date: datetime

class PlumeRiskResponse(BaseModel):
    risk_level: str
    risk_score: float
    fire_count: int
    transport_direction: str
    wind_speed: float
    distance_nearest_fire: float
    confidence: float
    factors: List[str]

class TransportDirectionResponse(BaseModel):
    station: str
    from_direction: str
    to_direction: str
    label: str
    wind_speed: Optional[float]
    wind_direction: Optional[float]
    basis: str

class ExplanationResponse(BaseModel):
    station: str
    timestamp: datetime
    prediction: dict
    top_features: List[dict]
    natural_language: List[str]

class AlertResponse(BaseModel):
    id: int
    station: str
    alert_level: str
    title: str
    description: str
    forecast_horizon_hours: Optional[int]
    factors: Optional[str]
    recommendation: Optional[str]
    created_at: datetime

class ModelMetricCreate(BaseModel):
    model_name: str
    pollutant: str
    horizon_hours: int
    mae: Optional[float] = None
    rmse: Optional[float] = None
    r2: Optional[float] = None
    mape: Optional[float] = None
    test_period_start: Optional[datetime] = None
    test_period_end: Optional[datetime] = None

class ModelMetricResponse(BaseModel):
    id: Optional[int] = None
    model_name: str
    pollutant: str
    horizon_hours: int
    mae: Optional[float]
    rmse: Optional[float]
    r2: Optional[float]
    mape: Optional[float]
    test_period_start: Optional[datetime]
    test_period_end: Optional[datetime]
    trained_at: Optional[datetime] = None