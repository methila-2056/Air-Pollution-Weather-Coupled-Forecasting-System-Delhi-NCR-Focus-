"""Optional demo-data hydration for the running app.

When ``DEMO_HYDRATE_EMPTY_DB=true`` the backend checks shortly after startup
whether either observation stream (pollution or weather) has any rows within
the last 24 hours and, if not, loads the bundled coupled dataset + FIRMS fire
archive + model metrics + seed alerts and re-stamps the newest observations
into the last 24 hourly slots. This renders the dashboard as a live-looking
demo on a brand-new database and self-heals stale CPCB feeds.

Deliberately opt-in: the live-refresh ingestion path is never touched, and the
default (flag unset) keeps the app behaviour identical to before.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..database import SessionLocal

logger = logging.getLogger("aerocast.hydration")

RECENCY_WINDOW_HOURS = 24


def _demo_observation_is_stale(db) -> bool:
    """True when pollution or weather has no reading within the last 24h."""
    from ..models.db_models import PollutionReading, WeatherReading

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=RECENCY_WINDOW_HOURS)
    recent_poll = (
        db.query(PollutionReading.id)
        .filter(PollutionReading.timestamp >= cutoff)
        .first()
    )
    recent_wx = (
        db.query(WeatherReading.id)
        .filter(WeatherReading.timestamp >= cutoff)
        .first()
    )
    return not (recent_poll and recent_wx)


def _load_demo_data() -> None:
    from backend.app.models.db_models import PollutionReading
    from backend.scripts import bootstrap_recent, load_data as demo

    csv_path = Path(demo.DEFAULT_CSV)
    fire_csv = Path(demo.MODELS_DIR).parent / "data" / "fire" / "firms_fires.csv"
    metrics_path = demo.MODELS_DIR / "metrics.json"

    db = SessionLocal()
    try:
        counts = demo.load_coupled_data(db, csv_path)
        n_fire = demo.load_fire_data(db, fire_csv)
        n_metrics = demo.load_metrics(db, metrics_path)
        n_alerts = demo.load_alerts_seed(db)
        logger.info(
            "demo data load complete: pollution=%d weather=%d fire=%d metrics=%d alerts=%d",
            counts["pollution"],
            counts["weather"],
            n_fire,
            n_metrics,
            n_alerts,
        )
    finally:
        db.close()

    anchor_minute = 0
    db = SessionLocal()
    try:
        latest = (
            db.query(PollutionReading.timestamp)
            .order_by(PollutionReading.timestamp.desc())
            .first()
        )
        if latest is not None and latest[0] is not None:
            anchor_minute = latest[0].minute
        n_poll = bootstrap_recent.bootstrap_pollution(db, anchor_minute)
        n_wx = bootstrap_recent.bootstrap_weather(db, anchor_minute)
        logger.info("demo re-stamp into last 24h: pollution=%d weather=%d", n_poll, n_wx)
    finally:
        db.close()


async def hydrate_demo_if_empty(stop: asyncio.Event) -> None:
    """Load demo data once when observations are missing or stale (background)."""
    del stop
    try:
        db = SessionLocal()
        try:
            stale = _demo_observation_is_stale(db)
        finally:
            db.close()

        if not stale:
            logger.info("demo hydration skipped: recent pollution+weather already present")
            return

        logger.info("demo hydration: recent observations absent, loading bundled dataset ...")
        await asyncio.to_thread(_load_demo_data)
        logger.info("demo hydration complete")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("demo hydration failed")