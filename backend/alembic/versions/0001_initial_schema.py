"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("city", sa.String(), server_default="Delhi NCR"),
    )
    op.create_index("ix_stations_id", "stations", ["id"])
    op.create_index("ix_stations_name", "stations", ["name"], unique=True)

    op.create_table(
        "pollution_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pm25", sa.Float()),
        sa.Column("pm10", sa.Float()),
        sa.Column("o3", sa.Float()),
        sa.Column("no2", sa.Float()),
        sa.Column("so2", sa.Float()),
        sa.Column("co", sa.Float()),
        sa.Column("aqi", sa.Integer()),
    )
    op.create_index("ix_pollution_readings_id", "pollution_readings", ["id"])
    op.create_index("idx_pollution_station_time", "pollution_readings", ["station_id", "timestamp"])

    op.create_table(
        "weather_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature", sa.Float()),
        sa.Column("humidity", sa.Float()),
        sa.Column("pressure_msl", sa.Float()),
        sa.Column("surface_pressure", sa.Float()),
        sa.Column("wind_speed", sa.Float()),
        sa.Column("wind_direction", sa.Float()),
        sa.Column("precipitation", sa.Float()),
        sa.Column("cloud_cover", sa.Float()),
        sa.Column("pbl_height", sa.Float()),
    )
    op.create_index("ix_weather_readings_id", "weather_readings", ["id"])
    op.create_index("idx_weather_station_time", "weather_readings", ["station_id", "timestamp"])

    op.create_table(
        "fire_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("acq_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.String()),
        sa.Column("frp", sa.Float()),
        sa.Column("satellite", sa.String()),
        sa.Column("daynight", sa.String()),
    )
    op.create_index("ix_fire_readings_id", "fire_readings", ["id"])

    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("forecast_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("pm25_pred", sa.Float()),
        sa.Column("pm10_pred", sa.Float()),
        sa.Column("o3_pred", sa.Float()),
        sa.Column("no2_pred", sa.Float()),
        sa.Column("aqi_pred", sa.Integer()),
        sa.Column("aqi_category", sa.String()),
        sa.Column("dominant_pollutant", sa.String()),
        sa.Column("inversion_detected", sa.Integer()),
        sa.Column("inversion_strength", sa.Float()),
        sa.Column("pbl_height", sa.Float()),
    )
    op.create_index("ix_forecasts_id", "forecasts", ["id"])
    op.create_index("idx_forecast_station_time", "forecasts", ["station_id", "forecast_timestamp"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("alert_level", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String()),
        sa.Column("forecast_horizon_hours", sa.Integer()),
        sa.Column("factors", sa.String()),
        sa.Column("recommendation", sa.String()),
    )
    op.create_index("ix_alerts_id", "alerts", ["id"])

    op.create_table(
        "model_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("pollutant", sa.String(), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("mae", sa.Float()),
        sa.Column("rmse", sa.Float()),
        sa.Column("r2", sa.Float()),
        sa.Column("mape", sa.Float()),
        sa.Column("test_period_start", sa.DateTime()),
        sa.Column("test_period_end", sa.DateTime()),
        sa.Column("trained_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_model_metrics_id", "model_metrics", ["id"])


def downgrade() -> None:
    op.drop_table("model_metrics")
    op.drop_table("alerts")
    op.drop_table("forecasts")
    op.drop_table("fire_readings")
    op.drop_table("weather_readings")
    op.drop_table("pollution_readings")
    op.drop_table("stations")
