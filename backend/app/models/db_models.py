from sqlalchemy import Column, Integer, Float, String, DateTime, Index
from sqlalchemy.sql import func
from ..database import Base

class Station(Base):
    __tablename__ = "stations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    city = Column(String, default="Delhi NCR")

class PollutionReading(Base):
    __tablename__ = "pollution_readings"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    pm25 = Column(Float)
    pm10 = Column(Float)
    o3 = Column(Float)
    no2 = Column(Float)
    so2 = Column(Float)
    co = Column(Float)
    aqi = Column(Integer)
    __table_args__ = (
        Index("idx_pollution_station_time", "station_id", "timestamp"),
    )

class WeatherReading(Base):
    __tablename__ = "weather_readings"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    pressure_msl = Column(Float)
    surface_pressure = Column(Float)
    wind_speed = Column(Float)
    wind_direction = Column(Float)
    precipitation = Column(Float)
    cloud_cover = Column(Float)
    pbl_height = Column(Float)
    __table_args__ = (
        Index("idx_weather_station_time", "station_id", "timestamp"),
    )

class FireReading(Base):
    __tablename__ = "fire_readings"
    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    acq_date = Column(DateTime(timezone=True), nullable=False)
    confidence = Column(String)
    frp = Column(Float)
    satellite = Column(String)
    daynight = Column(String)

class Forecast(Base):
    __tablename__ = "forecasts"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    forecast_timestamp = Column(DateTime(timezone=True), nullable=False)
    horizon_hours = Column(Integer, nullable=False)
    pm25_pred = Column(Float)
    pm10_pred = Column(Float)
    o3_pred = Column(Float)
    no2_pred = Column(Float)
    so2_pred = Column(Float)
    co_pred = Column(Float)
    aqi_pred = Column(Integer)
    aqi_category = Column(String)
    dominant_pollutant = Column(String)
    inversion_detected = Column(Integer)
    inversion_strength = Column(Float)
    pbl_height = Column(Float)
    coupling_stability = Column(Float)
    coupling_mode = Column(String)
    __table_args__ = (
        Index("idx_forecast_station_time", "station_id", "forecast_timestamp"),
    )

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    alert_level = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String)
    forecast_horizon_hours = Column(Integer)
    factors = Column(String)
    recommendation = Column(String)

class ModelMetrics(Base):
    __tablename__ = "model_metrics"
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, nullable=False)
    pollutant = Column(String, nullable=False)
    horizon_hours = Column(Integer, nullable=False)
    mae = Column(Float)
    rmse = Column(Float)
    r2 = Column(Float)
    mape = Column(Float)
    test_period_start = Column(DateTime)
    test_period_end = Column(DateTime)
    trained_at = Column(DateTime(timezone=True), server_default=func.now())
