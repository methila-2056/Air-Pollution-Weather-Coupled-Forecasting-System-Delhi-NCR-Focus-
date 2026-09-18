"""Chemical-transport-model (CTM) engine interface (SIH26082 R6).

Plugs real CTM engines — NOAA HYSPLIT and genuine WRF-Chem output — ahead of
the analytic advection-diffusion surrogate whenever they are actually installed
and configured with real input data. Engines are **never simulated**: if no
genuine engine is runnable, ``CtmUnavailable`` is raised and the caller falls
back to the documented analytic surrogate (see ``docs/hysplit.md`` and
``docs/wrfchem_adapter.md``).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Protocol

import numpy as np


class CtmUnavailable(RuntimeError):
    """Raised when a CTM engine is requested but not concretely runnable.

    The message lists exactly what is missing (executable, meteorological
    data, netCDF-capable stack, genuine WRF-Chem output, ...) so operators can
    close the gap; nothing is ever fabricated.
    """


class CtmResult:
    """A genuine CTM model run over a regular lat/lon grid."""

    def __init__(
        self,
        *,
        engine: str,
        pollutant: str,
        units: str,
        start_utc: _dt.datetime,
        times_utc: list[_dt.datetime],
        data: np.ndarray,
        lat: np.ndarray,
        lon: np.ndarray,
        metadata: dict[str, Any],
        hour_of_day: list[int] | None = None,
    ):
        self.engine = engine
        self.pollutant = pollutant
        self.units = units
        self.start_utc = start_utc
        self.times_utc = times_utc
        self.data = data  # shape (T, nlat, nlon)
        self.lat = lat
        self.lon = lon
        self.metadata = metadata
        self.hour_of_day = hour_of_day or [t.hour for t in times_utc]

    @property
    def n_frames(self) -> int:
        return int(self.data.shape[0])


class CTMEngine(Protocol):
    """Common interface implemented by every concrete CTM engine."""

    name: str

    def is_available(self) -> bool:
        """True only when real, authenticated inputs are present in-place."""
        ...

    def unavailable_reasons(self) -> list[str]:
        """Human-readable reasons for unavailability (diagnostics/reporting)."""
        ...

    def run(
        self,
        start_utc: _dt.datetime,
        hours: int,
        domain: dict[str, float],
        grid_step: float,
        sources: list[dict[str, float]] | None = None,
    ) -> CtmResult:
        ...


_REGISTRY: list[type[CTMEngine]] = []
# Deterministic priority: genuine WRF-Chem output first, then HYSPLIT (NOAA).
_ENGINE_ORDER: list[str] = ["WRF-Chem", "HYSPLIT (NOAA)"]


def register(cls: type[CTMEngine]) -> type[CTMEngine]:
    """Class decorator registering a concrete CTM engine implementation."""
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)
    return cls


def engine_classes() -> list[type[CTMEngine]]:
    return list(_REGISTRY)


def available_engines(
    domain: dict[str, float] | None = None,
    grid_step: float | None = None,
) -> list[str]:
    """Names of engines that are genuinely runnable right now."""
    ready: list[str] = []
    for cls in sorted(_REGISTRY, key=lambda c: _ENGINE_ORDER.index(c.name) if c.name in _ENGINE_ORDER else 99):
        engine = cls()
        if engine.is_available():
            ready.append(engine.name)
    return ready


def run_best_engine(
    start_utc: _dt.datetime,
    hours: int,
    domain: dict[str, float],
    grid_step: float,
    sources: list[dict[str, float]] | None = None,
    engine_name: str | None = None,
) -> tuple[str, CtmResult]:
    """Run the highest-priority *genuinely runnable* engine.

    Raises ``CtmUnavailable`` (with aggregated reasons) if none is runnable.
    Returns ``(engine_name, CtmResult)`` on success.
    """
    if engine_name is not None:
        classes = [c for c in _REGISTRY if c.name == engine_name]
        if not classes:
            raise CtmUnavailable(f"Unknown CTM engine requested: {engine_name!r}")
        return _run_one(classes[0](), start_utc, hours, domain, grid_step, sources)

    reasons: list[str] = []
    for cls in sorted(_REGISTRY, key=lambda c: _ENGINE_ORDER.index(c.name) if c.name in _ENGINE_ORDER else 99):
        engine = cls()
        if not engine.is_available():
            reasons.extend(engine.unavailable_reasons())
            continue
        return _run_one(engine, start_utc, hours, domain, grid_step, sources)

    raise CtmUnavailable(
        "No genuine CTM engine is configured. Reasons:\n  - "
        + "\n  - ".join(dict.fromkeys(reasons))
        + "\nFalling back to the analytic advection-diffusion surrogate."
    )


def _run_one(
    engine: CTMEngine,
    start_utc: _dt.datetime,
    hours: int,
    domain: dict[str, float],
    grid_step: float,
    sources: list[dict[str, float]] | None,
) -> tuple[str, CtmResult]:
    try:
        return engine.name, engine.run(start_utc, hours, domain, grid_step, sources=sources)
    except CtmUnavailable:
        raise
    except Exception as exc:  # never surface internal failures as CTM output
        raise CtmUnavailable(f"{engine.name} run failed: {exc}") from exc


def _default_hours(hours: int) -> list[int]:
    return list(range(max(1, hours)))
