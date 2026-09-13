import logging
import pathlib
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings

logger = logging.getLogger("aerocast.database")

settings = get_settings()


def _find_repo_root() -> pathlib.Path:
    """Locate the directory that owns ``alembic.ini`` by walking up the tree."""
    start = pathlib.Path(__file__).resolve().parent
    for parent in (start, *start.parents):
        if (parent / "alembic.ini").exists():
            return parent
    return start


_REPO_ROOT = _find_repo_root()

engine_kwargs: dict = {
    "pool_pre_ping": True,
}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10

try:
    engine = create_engine(settings.database_url, **engine_kwargs)
except Exception as exc:
    raise RuntimeError(
        "FATAL: Invalid DATABASE_URL configuration. Expected a SQLAlchemy URL such as "
        "'sqlite:///./aerocast_ncr.db' or 'postgresql://user:password@host:port/dbname'. "
        f"Raw error: {exc}"
    ) from exc
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def verify_postgres_connection() -> None:
    """Validate that PostgreSQL is reachable. Raises ``SystemExit`` on failure."""
    if settings.database_url.startswith("sqlite"):
        logger.info("Using SQLite — skipping PostgreSQL connection check")
        return

    logger.info("Verifying PostgreSQL connection ...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        logger.info("PostgreSQL connection verified successfully")
    except Exception as exc:
        logger.critical(
            "FATAL: Cannot connect to PostgreSQL at configured URL. "
            "Check DATABASE_URL, ensure the database server is running, "
            "and verify credentials. Error: %s",
            exc,
        )
        sys.exit(1)

DEFAULT_STATIONS = [
    {"name": "Anand Vihar", "latitude": 28.6492, "longitude": 77.2918, "city": "Delhi NCR"},
    {"name": "RK Puram", "latitude": 28.5601, "longitude": 77.1835, "city": "Delhi NCR"},
    {"name": "ITO", "latitude": 28.6290, "longitude": 77.2410, "city": "Delhi NCR"},
    {"name": "Dwarka", "latitude": 28.5921, "longitude": 77.0460, "city": "Delhi NCR"},
    {"name": "Punjabi Bagh", "latitude": 28.6692, "longitude": 77.1285, "city": "Delhi NCR"},
]

def seed_data(db) -> int:
    from .models.db_models import Station
    existing = db.query(Station).count()
    if existing == 0:
        db.bulk_save_objects([Station(**s) for s in DEFAULT_STATIONS])
        db.commit()
        return len(DEFAULT_STATIONS)
    return 0


def run_migrations() -> bool:
    """Apply Alembic migrations to the configured database.

    Runs ``alembic upgrade head`` against the repository's migration scripts
    (PostgreSQL production path, used by the containerised deploy at startup).
    SQLite databases are deliberately skipped.
    """
    if settings.database_url.startswith("sqlite"):
        return False

    logger.info("Running Alembic migrations (PostgreSQL) ...")
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    cfg.set_main_option("db_url", settings.database_url)
    command.upgrade(cfg, "head")
    return True


def apply_migrations():
    """Lightweight additive schema migrations for existing SQLite databases."""
    import sqlalchemy as sa
    from sqlalchemy import inspect

    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    # Phase-1 renames: reconcile legacy *_readings table names so the SQLite
    # dev database stays in sync with the PostgreSQL observation schema.
    for old_name, new_name in (("pollution_readings", "pollution_observations"),
                               ("weather_readings", "weather_observations")):
        if old_name in table_names:
            with engine.begin() as conn:
                conn.execute(sa.text(f"ALTER TABLE {old_name} RENAME TO {new_name}"))
            inspector = inspect(engine)
            table_names = set(inspector.get_table_names())

    # stations.state
    if "stations" in table_names:
        station_cols = {c["name"] for c in inspector.get_columns("stations")}
        if "state" not in station_cols:
            with engine.begin() as conn:
                conn.execute(sa.text("ALTER TABLE stations ADD COLUMN state VARCHAR"))

    # pollution_observations UNIQUE(station_id, timestamp)
    if "pollution_observations" in table_names:
        pr_cols = {c["name"] for c in inspector.get_columns("pollution_observations")}
        if "id" in pr_cols and "station_id" in pr_cols and "timestamp" in pr_cols:
            with engine.begin() as conn:
                conn.execute(sa.text(
                    "DELETE FROM pollution_observations WHERE id NOT IN ("
                    "  SELECT MAX(id) FROM pollution_observations"
                    "  GROUP BY station_id, timestamp)"
                ))
                conn.execute(sa.text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_pollution_station_ts"
                    " ON pollution_observations (station_id, timestamp)"
                ))

    # weather_observations vertical profile columns
    if "weather_observations" in table_names:
        wx_cols = {c["name"] for c in inspector.get_columns("weather_observations")}
        wx_add = {
            "latitude": "FLOAT",
            "longitude": "FLOAT",
            "pressure": "FLOAT",
            "temperature_1000hPa": "FLOAT",
            "temperature_925hPa": "FLOAT",
            "temperature_850hPa": "FLOAT",
            "temperature_700hPa": "FLOAT",
            "geopotential_height_925hPa": "FLOAT",
            "geopotential_height_850hPa": "FLOAT",
        }
        with engine.begin() as conn:
            for name, dtype in wx_add.items():
                if name not in wx_cols:
                    conn.execute(sa.text(f"ALTER TABLE weather_observations ADD COLUMN {name} {dtype}"))
        # weather_observations UNIQUE(station_id, timestamp) — mirrors the
        # PostgreSQL alembic migration f6a2e7b3c8d9.
        with engine.begin() as conn:
            conn.execute(sa.text(
                "DELETE FROM weather_observations WHERE id NOT IN ("
                "  SELECT MAX(id) FROM weather_observations"
                "  GROUP BY station_id, timestamp)"
            ))
            conn.execute(sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_weather_station_ts"
                " ON weather_observations (station_id, timestamp)"
            ))

    # fire_readings: instrument + brightness source attributes and the
    # hotspot uniqueness key (satellite, latitude, longitude, acq_date)
    # mirroring the PostgreSQL alembic migration e2b1c3d4a5f7.
    if "fire_readings" in table_names:
        fr_cols = {c["name"] for c in inspector.get_columns("fire_readings")}
        with engine.begin() as conn:
            if "instrument" not in fr_cols:
                conn.execute(sa.text("ALTER TABLE fire_readings ADD COLUMN instrument VARCHAR"))
            if "brightness" not in fr_cols:
                conn.execute(sa.text("ALTER TABLE fire_readings ADD COLUMN brightness FLOAT"))
            conn.execute(sa.text(
                "DELETE FROM fire_readings WHERE id NOT IN ("
                "  SELECT MAX(id) FROM fire_readings"
                "  GROUP BY satellite, latitude, longitude, acq_date)"
            ))
            conn.execute(sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_fire_lat_lon_time"
                " ON fire_readings (satellite, latitude, longitude, acq_date)"
            ))
            conn.execute(sa.text(
                "CREATE INDEX IF NOT EXISTS idx_fire_lat_lon_time"
                " ON fire_readings (latitude, longitude, acq_date)"
            ))

    if "forecasts" not in table_names:
        return

    existing_cols = {c["name"] for c in inspector.get_columns("forecasts")}
    add_columns = {
        "so2_pred": "FLOAT",
        "co_pred": "FLOAT",
        "coupling_stability": "FLOAT",
        "coupling_mode": "VARCHAR",
    }
    with engine.begin() as conn:
        for name, dtype in add_columns.items():
            if name not in existing_cols:
                conn.execute(sa.text(f"ALTER TABLE forecasts ADD COLUMN {name} {dtype}"))


def get_db():
    """FastAPI dependency that yields a database session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
