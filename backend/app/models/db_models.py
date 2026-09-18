from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from ..database import Base


class Station(Base):
    __tablename__ = "stations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    city = Column(String, default="Delhi NCR")
    state = Column(String)

class PollutionReading(Base):
    __tablename__ = "pollution_observations"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    pm25 = Column(Float)
    pm10 = Column(Float)
    o3 = Column(Float)
    no2 = Column(Float)
    so2 = Column(Float)
    co = Column(Float)
    aqi = Column(Integer)
    # Provenance tag: which official source produced this reading
    # (data_gov_in | opencity_ckan | cpcb_dataset | cpcb_live). NULL for legacy
    # rows ingested before the column existed.
    data_source = Column(String)
    __table_args__ = (
        UniqueConstraint("station_id", "timestamp", name="uq_pollution_station_ts"),
        Index("idx_pollution_station_time", "station_id", "timestamp"),
    )

class WeatherReading(Base):
    __tablename__ = "weather_observations"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    temperature = Column(Float)
    humidity = Column(Float)
    pressure = Column(Float)
    pressure_msl = Column(Float)
    surface_pressure = Column(Float)
    wind_speed = Column(Float)
    wind_direction = Column(Float)
    precipitation = Column(Float)
    cloud_cover = Column(Float)
    pbl_height = Column(Float)
    # Vertical pressure-level temperature (degC) used for lapse-rate inversion
    # (SIH26082). Open-Meteo / ERA5 style: temperature at standard pressure
    # levels. All optional — when NULL the PBL-height proxy is used.
    temperature_1000hPa = Column(Float)
    temperature_925hPa = Column(Float)
    temperature_850hPa = Column(Float)
    temperature_700hPa = Column(Float)
    geopotential_height_925hPa = Column(Float)
    geopotential_height_850hPa = Column(Float)
    __table_args__ = (
        UniqueConstraint("station_id", "timestamp", name="uq_weather_station_ts"),
        Index("idx_weather_station_time", "station_id", "timestamp"),
    )

class FireReading(Base):
    """A single NASA FIRMS active-fire observation (hotspot event).

    Stores the raw fire *observation* only — no attribution to pollution is
    implied here. ``acq_date`` is kept as naive-UTC (matching the weather
    convention) and the row key (satellite, latitude, longitude, acq_date)
    prevents duplicate ingestion of the same hotspot detection.
    """
    __tablename__ = "fire_readings"
    id = Column(Integer, primary_key=True, index=True)
    satellite = Column(String)
    instrument = Column(String)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    acq_date = Column(DateTime(timezone=True), nullable=False)
    confidence = Column(String)
    frp = Column(Float)
    brightness = Column(Float)
    daynight = Column(String)
    __table_args__ = (
        UniqueConstraint("satellite", "latitude", "longitude", "acq_date", name="uq_fire_lat_lon_time"),
        Index("idx_fire_lat_lon_time", "latitude", "longitude", "acq_date"),
    )

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

class User(Base):
    """Portal account used by the UI authentication layer (SIH26082).

    Stored passwords are scrypt-hashed with a per-user random salt; only the
    hex-encoded salt and hash are persisted. See ``backend/app/security.py``.
    """
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Analyst")
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
