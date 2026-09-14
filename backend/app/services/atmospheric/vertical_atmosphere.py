"""Open-Meteo pressure-level vertical atmosphere ingestion (SIH26082).

Fetches vertical temperature + geopotential-height profiles at standard
pressure levels (1000 / 925 / 850 / 700 hPa) for each Delhi NCR station from
the free Open-Meteo forecast API, then computes the scientifically defensible
inversion analysis (vertical lapse rate) and PBL classification.

Design notes / SIH alignment
----------------------------
* The data are **real** (Open-Meteo reanalysis-informed forecast), not
  fabricated. Temperatures are standard WMO pressure-level fields.
* **Graceful fallback**: when the network is unavailable the module returns
  ``analysis=None`` and callers fall back to the documented PBL-threshold proxy
  (see ``ml/features/inversion.py``).
* **Disclosure**: the analysis dict carries ``inversion_source`` in
  {``lapse_rate``, ``pbl_proxy``} so consumers (dashboards, API) can state
  whether inversion strength came from a true vertical profile or a proxy.

ERA5 pressure-level data (Copernicus CDS) would be the production-scale
upgrade; Open-Meteo is used here so the prototype remains key-free and
reproducible on commodity hardware (see README "Honest Scope" and
``docs/methodology.md`` §9).
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from ml.features.atmospheric_profile import (
    DEFAULT_LEVELS_HPA,
    combine_inversion,
)

logger = logging.getLogger("aerocast.atmosphere")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT = 30

#: Standard pressure levels (hPa) from the WRF/ERA5 vertical grid convention.
PRESSURE_LEVELS = DEFAULT_LEVELS_HPA

#: Detection threshold for lapse-rate inversion (documented in atmospheric_profile).
LAPSE_UNIT = "K per 100 hPa"


def _level_variables(levels: list[float] | None = None) -> list[str]:
    """Build the Open-Meteo hourly variable list for temperature at *levels*."""
    chosen: list[float] = levels if levels is not None else PRESSURE_LEVELS
    return [f"temperature_{int(p)}hPa" for p in chosen]


def fetch_vertical_profile(
    latitude: float,
    longitude: float,
    forecast_days: int = 3,
    levels: list[float] | None = None,
) -> dict | None:
    """Fetch vertical temperature/geopotential profile from Open-Meteo.

    Returns a dict::

        {
          "time": [iso strings],
          "temperature": {1000: [...], 925: [...], 850: [...], 700: [...]},
          "geopotential_height": {925: [...], 850: [...]},
          "level_unit": "hPa",
          "temperature_unit": "degC",
        }

    or ``None`` if the request failed.
    """
    levels = levels if levels is not None else PRESSURE_LEVELS
    hourly = _level_variables(levels)
    # Geopotential heights available at these levels on the free tier.
    for p in (925, 850):
        name = f"geopotential_height_{int(p)}hPa"
        if f"temperature_{int(p)}hPa" in hourly:
            hourly.append(name)

    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(hourly),
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }
    try:
        resp = requests.get(FORECAST_URL, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # network / API errors
        logger.warning("Open-Meteo pressure-level fetch failed: %s", exc)
        return None

    hourly_data = data.get("hourly", {})
    if not hourly_data or "time" not in hourly_data:
        logger.warning("Open-Meteo returned no pressure-level data")
        return None

    temps: dict[float, list[float]] = {}
    geopot: dict[float, list[float]] = {}
    for level in levels:
        var = f"temperature_{int(level)}hPa"
        if var in hourly_data:
            temps[float(level)] = hourly_data[var]
    for p in (925, 850):
        var = f"geopotential_height_{int(p)}hPa"
        if var in hourly_data:
            geopot[float(p)] = hourly_data[var]

    if len(temps) < 2:
        logger.warning("Fewer than 2 temperature levels available (%s)", sorted(temps))
        return None

    return {
        "time": hourly_data["time"],
        "temperature": temps,
        "geopotential_height": geopot,
        "level_unit": "hPa",
        "temperature_unit": "degC",
    }


def analyze_vertical_profile(
    profile: dict | None,
    pbl_height: float | None,
    *,
    at_index: int = -1,
) -> dict | None:
    """Run the inversion/PBL analysis for a single timestep of a profile.

    Args:
        profile: dict from :func:`fetch_vertical_profile` (or None).
        pbl_height: Open-Meteo boundary-layer height at the same timestep (m).
        at_index: index into the profile time series (defaults to latest).

    Returns None when ``profile`` is None; otherwise the combined analysis dict
    (see ``ml/features/atmospheric_profile.combine_inversion``).
    """
    if not profile:
        return None

    temps: dict[float, float] = {}
    for p, series in (profile.get("temperature") or {}).items():
        try:
            val = float(series[at_index])
        except (IndexError, TypeError, ValueError):
            continue
        temps[float(p)] = val

    return combine_inversion(pbl_height, temps)


def analyze_station(
    latitude: float,
    longitude: float,
    pbl_height: float | None,
    forecast_days: int = 3,
    levels: list[float] | None = None,
) -> dict:
    """One-call helper: fetch + analyze a station's vertical atmosphere.

    Always returns a dict. When vertical data is unavailable it returns the
    PBL-proxy analysis so callers never crash:

        {"station_atmosphere": {...}, "profile_fetched": bool}
    """
    profile = fetch_vertical_profile(latitude, longitude, forecast_days=forecast_days, levels=levels)
    if profile is None:
        analysis = combine_inversion(pbl_height, None)
        return {"station_atmosphere": analysis, "profile_fetched": False}
    found = analyze_vertical_profile(profile, pbl_height)
    if found is None:
        analysis = combine_inversion(pbl_height, None)
        return {"station_atmosphere": analysis, "profile_fetched": False}
    found["profile_fetched"] = True
    return {"station_atmosphere": found, "profile_fetched": True}
