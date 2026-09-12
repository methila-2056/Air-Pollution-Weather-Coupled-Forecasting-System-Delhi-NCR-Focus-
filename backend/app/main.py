import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text

from .api import (
    alerts,
    atmosphere,
    coupling,
    dispersion,
    events,
    explanation,
    export,
    fire,
    forecast,
    grid,
    inversion,
    model_metrics,
    model_performance,
    pm25_forecast,
    pollution,
    scenario,
    stations,
    summary,
    transport_risk,
    weather,
)
from .config import get_settings
from .database import (
    Base,
    SessionLocal,
    apply_migrations,
    engine,
    run_migrations,
    seed_data,
    verify_postgres_connection,
)

settings = get_settings()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_LEVEL = getattr(logging, settings.log_level.upper(), logging.INFO)

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aerocast")

# Quieten noisy third-party loggers
logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if LOG_LEVEL <= logging.DEBUG else logging.WARNING
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

_refresh_stop = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("AeroCast-NCR backend starting (env=%s)", settings.environment)

    # 1. Verify PostgreSQL connectivity (exits on failure)
    verify_postgres_connection()

    # 2. Database migrations + schema
    try:
        migrated = run_migrations()
        apply_migrations()
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seeded = seed_data(db)
            if seeded:
                logger.info("Seeded %d default Delhi NCR stations", seeded)
            if migrated:
                logger.info("Alembic migrations applied at startup")
    except Exception as exc:
        logger.warning("Startup database initialisation skipped: %s", exc)

    # 3. Optional live-refresh scheduler
    refresh_task = None
    if getattr(settings, "live_refresh_enabled", False):
        from .services.refresh_service import refresh_loop
        refresh_task = asyncio.create_task(
            refresh_loop(interval_hours=settings.live_refresh_interval_hours, stop=_refresh_stop)
        )
        logger.info(
            "Live refresh scheduler started (interval=%sh)",
            settings.live_refresh_interval_hours,
        )

    logger.info("AeroCast-NCR backend ready")
    yield

    # --- Shutdown ---
    if refresh_task is not None:
        _refresh_stop.set()
        refresh_task.cancel()
        try:
            await refresh_task
        except (asyncio.CancelledError, Exception):
            pass
    logger.info("AeroCast-NCR backend shutting down")

app = FastAPI(
    title="AeroCast-NCR API",
    description="AI-Powered 72-Hour Air Quality & Pollution-Plume Forecasting for Delhi NCR",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stations.router, prefix="/api", tags=["Stations"])
app.include_router(pollution.router, prefix="/api", tags=["Pollution"])
# NOTE: pm25_forecast must be registered BEFORE forecast because the latter has
# a dynamic `/forecast/{station_name}` route that would otherwise shadow the
# static `/forecast/pm25` path.
app.include_router(pm25_forecast.router, prefix="/api", tags=["PM2.5 Forecast"])
app.include_router(forecast.router, prefix="/api", tags=["Forecast"])
app.include_router(weather.router, prefix="/api", tags=["Weather"])
app.include_router(inversion.router, prefix="/api", tags=["Inversion"])
app.include_router(atmosphere.router, prefix="/api", tags=["Atmosphere"])
app.include_router(fire.router, prefix="/api", tags=["Fire"])
app.include_router(explanation.router, prefix="/api", tags=["Explanation"])
app.include_router(alerts.router, prefix="/api", tags=["Alerts"])
app.include_router(model_metrics.router, prefix="/api", tags=["Model Metrics"])
app.include_router(model_performance.router, prefix="/api", tags=["Model Performance"])
app.include_router(coupling.router, prefix="/api", tags=["Coupling Feedback"])
app.include_router(grid.router, prefix="/api", tags=["Grid Forecast"])
app.include_router(dispersion.router, prefix="/api", tags=["Dispersion Forecast"])
app.include_router(summary.router, prefix="/api", tags=["Summary"])
app.include_router(export.router, prefix="/api", tags=["Export"])
app.include_router(transport_risk.router, prefix="/api", tags=["Transport Risk"])
app.include_router(events.router, prefix="/api", tags=["Pollution Events"])
app.include_router(scenario.router, prefix="/api", tags=["Scenario Analysis"])

@app.get("/api/health")
def health():
    """Liveness probe â€” returns HTTP 200 with ``{"status": "ok"}``.

    The rich variant (with database connectivity) is served at ``/health``
    and is used by Docker/Compose healthchecks.
    """
    return {"status": "ok"}


@app.get("/health")
def health_probe():
    """Readiness probe â€” also verifies database connectivity so that Docker
    healthchecks catch database outages.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
        logger.warning("Health check: database unreachable")
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "service": "AeroCast-NCR API",
        "version": "1.0.0",
        "database": db_status,
    }

@app.get("/api/data-quality")
def data_quality():
    from .models.db_models import (
        Alert,
        FireReading,
        Forecast,
        ModelMetrics,
        PollutionReading,
        Station,
        WeatherReading,
    )

    db = SessionLocal()
    try:
        tables = [
            ("stations", Station, []),
            ("pollution_observations", PollutionReading, ["pm25", "pm10", "o3", "no2", "so2", "co", "aqi"]),
            ("weather_observations", WeatherReading, ["temperature", "humidity", "wind_speed", "wind_direction", "pbl_height"]),
            ("fire_readings", FireReading, ["latitude", "longitude", "acq_date"]),
            ("forecasts", Forecast, ["pm25_pred", "pm10_pred", "aqi_pred", "aqi_category"]),
            ("alerts", Alert, ["alert_level", "title"]),
            ("model_metrics", ModelMetrics, ["model_name", "pollutant"]),
        ]
        tables_report = {}
        recommendations = []
        for name, model, columns in tables:
            total = db.query(model).count()
            missing = {}
            for col in columns:
                nulls = db.query(model).filter(getattr(model, col).is_(None)).count()
                missing[col] = nulls
                if nulls:
                    recommendations.append(f"{name}.{col} has {nulls} missing value(s) out of {total} row(s)")
            tables_report[name] = {"total": total, "missing_values": missing}

        stations = db.query(Station).order_by(Station.name).all()
        forecast_coverage = {}
        forecasted_stations = 0
        for s in stations:
            n = db.query(Forecast).filter(Forecast.station_id == s.id).count()
            forecast_coverage[s.name] = n
            if n:
                forecasted_stations += 1

        latest_pollution = db.query(func.max(PollutionReading.timestamp)).scalar()
        latest_weather = db.query(func.max(WeatherReading.timestamp)).scalar()
        latest_fire = db.query(func.max(FireReading.acq_date)).scalar()

        return {
            "status": "ok",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "station_count": len(stations),
            "stations_with_forecasts": forecasted_stations,
            "forecast_coverage": forecast_coverage,
            "latest_pollution_reading": latest_pollution.isoformat() if latest_pollution else None,
            "latest_weather_reading": latest_weather.isoformat() if latest_weather else None,
            "latest_fire_reading": latest_fire.isoformat() if latest_fire else None,
            "tables": tables_report,
            "recommendations": recommendations,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Data quality check failed: {exc}") from exc
    finally:
        db.close()

