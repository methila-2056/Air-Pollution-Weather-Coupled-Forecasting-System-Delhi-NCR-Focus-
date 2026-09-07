from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import get_settings

settings = get_settings()

engine_kwargs = {}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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


def apply_migrations():
    """Lightweight additive schema migrations for existing SQLite databases.

    `Base.metadata.create_all` only creates missing *tables*, not missing
    *columns* on pre-existing tables. This adds any newly-introduced columns to
    the `forecasts` table so upgraded databases stay compatible without a full
    rebuild. Purely additive (ALTER TABLE ... ADD COLUMN); never destructive.
    """
    import sqlalchemy as sa
    from sqlalchemy import inspect

    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "forecasts" not in inspector.get_table_names():
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
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()