from datetime import datetime

from pydantic import BaseModel, Field


class StationResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    city: str

class StationAQISummary(BaseModel):
    name: str
    aqi: int | None
    aqi_category: str
    dominant_pollutant: str | None

class SummaryResponse(BaseModel):
    generated_at: datetime
    stations: int
    stations_with_readings: int
    ncr_avg_aqi: float | None
    worst_station: StationAQISummary | None
    best_station: StationAQISummary | None
    active_fires_24h: int
    open_alerts: int
    models_trained: int
    forecast_coverage: dict

class CurrentAQI(BaseModel):
    station: str
    timestamp: datetime
    pm25: float | None
    pm10: float | None
    o3: float | None
    no2: float | None
    so2: float | None
    co: float | None
    aqi: int | None
    aqi_category: str
    dominant_pollutant: str

class ForecastPoint(BaseModel):
    timestamp: datetime
    horizon_hours: int
    pm25_pred: float | None
    pm10_pred: float | None
    o3_pred: float | None
    no2_pred: float | None
    so2_pred: float | None = None
    co_pred: float | None = None
    aqi_pred: int | None
    aqi_category: str
    dominant_pollutant: str | None = None
    coupling_stability: float | None = None

class GridForecastPoint(BaseModel):
    timestamp: datetime
    horizon_hours: int
    aqi_pred: int | None
    aqi_category: str
    lat: float | None = None
    lon: float | None = None

class ForecastGenerateRequest(BaseModel):
    station_name: str | None = None
    horizons: list[int] = Field(default_factory=lambda: [1, 6, 12, 24, 48, 72])

class ForecastGenerateResponse(BaseModel):
    station: str
    generated_at: datetime
    horizons: list[int]
    forecasts: list[ForecastPoint]

class ForecastComparisonPoint(BaseModel):
    timestamp: datetime
    actual_aqi: int | None
    predicted_aqi: int | None
    actual_pm25: float | None
    predicted_pm25: float | None
    delta: float | None

class ForecastComparisonResponse(BaseModel):
    station: str
    points: list[ForecastComparisonPoint]

class WeatherResponse(BaseModel):
    station: str
    timestamp: datetime
    temperature: float | None
    humidity: float | None
    pressure_msl: float | None
    wind_speed: float | None
    wind_direction: float | None
    precipitation: float | None
    cloud_cover: float | None

class WeatherDetailResponse(BaseModel):
    station: str
    timestamp: datetime
    temperature: float | None
    humidity: float | None
    pressure_msl: float | None
    surface_pressure: float | None
    wind_speed: float | None
    wind_direction: float | None
    precipitation: float | None
    cloud_cover: float | None
    pbl_height: float | None

class InversionResponse(BaseModel):
    station: str
    timestamp: datetime
    pbl_height: float | None
    inversion_detected: bool
    inversion_strength: str
    trapping_risk: str

class CouplingDiagnostics(BaseModel):
    aod_est: float
    radiation_transmittance: float
    pbl_suppression_factor: float
    corrected_pbl_height: float
    stability_coupling_index: float
    feedback_multiplier: float
    coupling_strength: str

class CouplingResponse(BaseModel):
    station: str
    timestamp: datetime
    pm25: float | None
    pbl_height: float | None
    wind_speed: float | None
    diag: CouplingDiagnostics
    narrative: list[str]

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
    factors: list[str]

class TransportDirectionResponse(BaseModel):
    station: str
    from_direction: str
    to_direction: str
    label: str
    wind_speed: float | None
    wind_direction: float | None
    basis: str

class ExplanationResponse(BaseModel):
    station: str
    timestamp: datetime
    prediction: dict
    top_features: list[dict]
    natural_language: list[str]

class AlertResponse(BaseModel):
    id: int
    station: str
    alert_level: str
    title: str
    description: str
    forecast_horizon_hours: int | None
    factors: str | None
    recommendation: str | None
    created_at: datetime

class ModelMetricCreate(BaseModel):
    model_name: str
    pollutant: str
    horizon_hours: int
    mae: float | None = None
    rmse: float | None = None
    r2: float | None = None
    mape: float | None = None
    test_period_start: datetime | None = None
    test_period_end: datetime | None = None

class ModelMetricResponse(BaseModel):
    id: int | None = None
    model_name: str
    pollutant: str
    horizon_hours: int
    mae: float | None
    rmse: float | None
    r2: float | None
    mape: float | None
    test_period_start: datetime | None
    test_period_end: datetime | None
    trained_at: datetime | None = None
