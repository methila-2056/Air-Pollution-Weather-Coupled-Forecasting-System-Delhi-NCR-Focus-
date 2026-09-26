"""Cold-start cache pre-warm for the control room.

Render's free tier scales the service to zero after ~15 minutes idle, and a
measured production cold wake takes ~76 s. The Control Room then fans out ~14
requests at once, several of which are heavy aggregations over the pooled Neon
Postgres (``/api/summary`` ~12 s, ``/api/atmosphere/current`` ~11 s for all 17
stations, ``/api/data-quality`` ~11 s). On a cold instance every one of those
caches is empty, so the fan-out serialises on a 0.5-CPU box, individual requests
run past the browser's timeout, and panels are left permanently empty — the
exact failure this module exists to prevent.

Every panel already reads through :func:`..services.ttl_cache.cached`. This
module simply runs the same builders, with the *same cache keys*, in the
background right after the app reports ready. The first dashboard load after a
cold start is then served from a warm cache.

Design notes:

* Opt-in via ``CONTROL_ROOM_PREWARM`` (see :mod:`..config`). It is off by
  default so local development, pytest and CI never pay for it.
* Runs off the event loop in a worker thread, one entry at a time, with a pause
  between entries so a real user request that arrives mid-pre-warm is not
  starved of the single CPU.
* Best-effort: a failing entry is logged and skipped. A pre-warm that throws
  must never take the service down.
* Nothing is fabricated or mutated — these are the same read-only builders the
  HTTP handlers call.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("aerocast.prewarm")

# Pause between entries. Long enough that an inbound request is served without
# queueing behind a 10 s aggregation, short enough that the whole sweep still
# finishes inside a typical cold-boot window.
_ENTRY_GAP_S = 1.0


def _entries() -> list[tuple[str, str, float, Callable[[object], object]]]:
    """``(label, cache_key, ttl, builder)`` for every heavy read-only panel.

    The keys must stay identical to the ones the HTTP layer uses, otherwise the
    pre-warm fills an entry nobody reads.
    """
    from ..api import fire as fire_api
    from ..api import grap as grap_api
    from ..api import grid as grid_api
    from ..api import summary as summary_api

    # Imported here rather than at module scope: ``main`` imports the API
    # routers, so a top-level import would be circular. By the time the sweep
    # runs the app is fully imported.
    from ..main import _data_quality_report
    from ..services import alert_service, atmosphere_service, transport_risk_service
    from ..services.dispersion_service import run_dispersion_forecast_service

    return [
        ("atmosphere:current", "atmosphere:current", 300, lambda db: atmosphere_service.get_current_atmosphere(db)),
        ("alerts:all_stations", "alerts:all_stations", 120, lambda db: alert_service.all_station_alerts(db)),
        ("summary", "summary", 60, lambda db: summary_api._build_summary(db)),
        # Opens its own session (it is defined in main.py that way).
        ("data-quality", "data-quality", 300, lambda _db: _data_quality_report()),
        ("transport-risk:current:72", "transport-risk:current:72", 300,
         lambda db: transport_risk_service.get_current_transport_risk(db, fire_window_hours=72)),
        ("grap:current", "grap:current", 300, lambda db: grap_api._compute_grap_current(db)),
        ("fire-activity", "fire-activity", 300, lambda db: fire_api._compute_fire_activity(db)),
        ("fire-hotspots", "fire-hotspots", 300, lambda db: fire_api._compute_fire_hotspots(db)),
        ("plume-risk", "plume-risk", 300, lambda db: fire_api._compute_plume_risk(db)),
        ("grid:forecast:24", "grid:forecast:24", 120, lambda db: grid_api._compute_grid(db, 24)),
        # Most expensive single panel (72 hourly x 1575-cell grids). Last, so the
        # cheap high-traffic panels are warm before the CPU goes into the solver.
        ("dispersion:72:8:all", "dispersion:72:8:all", 300,
         lambda db: run_dispersion_forecast_service(db, horizon_hours=72, start_hour=8)),
    ]


def prewarm_control_room(stop: threading.Event | None = None) -> None:
    """Populate the TTL cache with the control room's heavy read payloads.

    ``stop`` (a :class:`threading.Event`) lets the caller abandon the sweep at
    shutdown; it is checked between entries only, never mid-query.
    """
    from ..database import SessionLocal
    from .ttl_cache import cached

    started = time.monotonic()
    warmed, failed = 0, 0
    for label, key, ttl, builder in _entries():
        if stop is not None and stop.is_set():
            logger.info("Pre-warm cancelled after %d entries", warmed)
            return
        try:
            with SessionLocal() as db:
                cached(key, ttl, lambda b=builder: b(db))
            warmed += 1
            logger.info("Pre-warmed %s", label)
        except Exception:
            failed += 1
            logger.exception("Pre-warm failed for %s (continuing)", label)
        time.sleep(_ENTRY_GAP_S)
    logger.info(
        "Pre-warm complete: %d entries warm, %d failed, %.1fs", warmed, failed, time.monotonic() - started
    )
