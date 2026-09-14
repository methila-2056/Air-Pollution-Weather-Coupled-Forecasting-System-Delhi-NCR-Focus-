"""Atmospheric-condition analysis layer for AeroCast-NCR.

Computes explainable, machine-readable indicators of *how well the atmosphere
is currently venting* the Delhi NCR region, using **only the pollution and
weather observations already stored in the database** — no live network calls
and no ML models (XGBoost/GRU deliberately deferred).

Indicators (each with a provenance tag):

  wind_condition            DERIVED   — deterministic categories from stored
                                        wind_speed / wind_direction.
  pbl_condition             ESTIMATED — boundary-layer height is an Open-Meteo
                                        model field; category is thresholded.
  ventilation_condition     DERIVED   — ventilation coefficient = wind × PBL.
  inversion_indicator       DERIVED   — vertical lapse-rate from stored
                                        pressure-level temperatures when 2+
                                        levels exist (``source="lapse_rate"``),
                                        otherwise a clearly-labelled proxy
                                        (``source="pbl_proxy"``) that is
                                        *never* a surface-temperature threshold.
  pollution_trapping_index  DERIVED   — composite of ventilation, PBL,
                                        inversion and *observed* PM2.5.
                                        It reports trapping propensity, not
                                        an attribution of any pollutant to
                                        any source.

Provenance taxonomy (per indicator)
-----------------------------------
* ``OBSERVED``  — value read back with no processing.
* ``DERIVED``   — deterministic formula/categories applied to stored inputs.
* ``ESTIMATED`` — relies on a model-produced quantity (e.g. PBL height) or on
                  a documented proxy for an unobserved quantity.

Important caveat about the raw inputs (reported in the API):
all weather values are Open-Meteo model output (ERA5-informed / forecast), not
in-situ instruments; pollution values are CPCB observations. This is stated in
``input_basis`` so consumers never mistake an estimate for a measurement.

Formulas (documented here once; consumers see them in
``methodology.formulas``):
  ventilation_coefficient [m2/s] = wind_speed[m/s] * pbl_height[m]
  inversion gradient [K/100 hPa] = (T_top - T_base) / (p_base - p_top) * 100
  dispersion_quality q = 0.50*vent_norm + 0.20*pbl_norm + 0.30*(1-inv_norm)
  trapping_index = clip(0.70*(1 - q) + 0.30*pm25_norm, 0, 1)   (pm25 known)
                   clip(       1 - q,               , 0, 1)     (pm25 unknown)
  pm25_norm = clip((pm25 - 35) / (300 - 35), 0, 1)

Normalized atmospheric features (all 0..1) are exposed for later ML use:
  features.wind, features.pbl, features.ventilation (higher = more dispersion)
  features.inversion, features.trapping              (higher = more trapping)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import numpy as np

logger = logging.getLogger("aerocast.atmosphere")

METHODOLOGY_VERSION = "1.0.0"
REGION = "Delhi NCR + ring stations (CPCB network)"

# ---------------------------------------------------------------------------
# Thresholds / bands (documented in the API response for transparency)
# ---------------------------------------------------------------------------

# Wind speed bands (m/s) — standard urban-meteorology categories.
WIND_BANDS: list[tuple[float, str, str]] = [
    (0.5, "calm", "Calm (<0.5 m/s) — near-stagnant air"),
    (2.0, "light", "Light air (0.5–2 m/s) — limited horizontal ventilation"),
    (4.0, "moderate", "Moderate breeze (2–4 m/s)"),
    (7.0, "brisk", "Brisk breeze (4–7 m/s) — good ventilation"),
    (float("inf"), "strong", "Strong wind (\u22657 m/s) — excellent ventilation"),
]
WIND_REF_MPS = 7.0  # speed that counts as "full" horizontal dispersion

# PBL height (m) — matches ml/features/atmospheric_profile.py conventions.
PBL_STRONG_TRAP_M = 150.0
PBL_MODERATE_TRAP_M = 300.0
PBL_WEAK_TRAP_M = 500.0
PBL_REF_M = 1500.0  # "full" mixing depth for normalization

# Ventilation coefficient bands (m2/s) — Delhi/IITM ventilation classification.
VENT_POOR_M2S = 3000.0
VENT_MODERATE_M2S = 6000.0
VENT_REF_M2S = 6000.0

# PM2.5 reference points for observed-loading normalization (µg/m3):
PM25_REF_GOOD = 35.0  # CPCB 24h satisfactory upper bound
PM25_REF_SEVERE = 300.0  # CPCB emergency band

# Trapping composite weights.
W_DISPERSION = 0.70
W_OBSERVED = 0.30
W_VENT = 0.50
W_PBL = 0.20
W_INV = 0.30


def _clip01(v) -> float | None:
    if v is None:
        return None
    try:
        return round(float(np.clip(float(v), 0.0, 1.0)), 4)
    except (TypeError, ValueError):
        return None


def _float(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def classify_wind(speed: float | None) -> dict[str, Any]:
    """Classify stored wind speed into a condition band."""
    speed = _float(speed)
    if speed is None:
        return {
            "wind_speed_mps": None,
            "wind_direction_deg": None,
            "category": "unavailable",
            "label": "No wind data",
            "normalized": None,
            "provenance": "DERIVED",
            "notes": ["Wind data missing for the latest weather reading."],
        }
    for limit, cat, label in WIND_BANDS:
        if speed < limit:
            return {
                "wind_speed_mps": round(speed, 2),
                "wind_direction_deg": None,
                "category": cat,
                "label": label,
                "normalized": _clip01(speed / WIND_REF_MPS),
                "provenance": "DERIVED",
                "notes": [f"Category from stored wind_speed = {round(speed, 2)} m/s."],
            }
    return {}


def classify_pbl(pbl_height: float | None) -> dict[str, Any]:
    """Classify the (model-estimated) boundary-layer height."""
    pbl = _float(pbl_height)
    if pbl is None:
        return {
            "pbl_height_m": None,
            "category": "unavailable",
            "label": "Boundary-layer height unavailable",
            "normalized": None,
            "provenance": "ESTIMATED",
            "notes": ["PBL height not stored; indicator cannot be computed."],
        }
    if pbl < PBL_STRONG_TRAP_M:
        cat, label = "strong_trapping", "Shallow PBL (<150 m) — strong near-ground trapping"
    elif pbl < PBL_MODERATE_TRAP_M:
        cat, label = "moderate_trapping", "Shallow PBL (150–300 m) — limited vertical mixing"
    elif pbl < PBL_WEAK_TRAP_M:
        cat, label = "weak_trapping", "Moderate PBL (300–500 m) — restricted mixing"
    else:
        cat, label = "good_dispersion", "Deep PBL (\u2265500 m) — good vertical mixing"
    return {
        "pbl_height_m": round(pbl, 1),
        "category": cat,
        "label": label,
        "normalized": _clip01(pbl / PBL_REF_M),
        "provenance": "ESTIMATED",
        "notes": [
            "PBL height is an Open-Meteo model field, not an in-situ measurement.",
            f"Category thresholded on stored pbl_height = {round(pbl, 1)} m.",
        ],
    }


def ventilation_condition(wind_speed: float | None, pbl_height: float | None) -> dict[str, Any]:
    """Ventilation coefficient (wind × PBL) and its condition band."""
    v = _float(wind_speed)
    p = _float(pbl_height)
    if v is None or p is None:
        return {
            "ventilation_coefficient_m2s": None,
            "category": "unavailable",
            "label": "Ventilation coefficient unavailable",
            "normalized": None,
            "provenance": "DERIVED",
            "notes": ["Both wind_speed and pbl_height are required."],
        }
    vc = v * p
    if vc < VENT_POOR_M2S:
        cat, label = "poor", "Poor ventilation (<3000 m2/s) — pollutants accumulate"
    elif vc < VENT_MODERATE_M2S:
        cat, label = "moderate", "Moderate ventilation (3000–6000 m2/s)"
    else:
        cat, label = "good", "Good ventilation (\u22656000 m2/s)"
    return {
        "ventilation_coefficient_m2s": round(vc, 1),
        "category": cat,
        "label": label,
        "normalized": _clip01(vc / VENT_REF_M2S),
        "provenance": "DERIVED",
        "notes": [f"ventilation_coefficient = wind_speed × pbl_height = {round(v, 2)} × {round(p, 1)} m2/s."],
    }


def inversion_indicator(reading) -> dict[str, Any]:
    """Inversion via vertical lapse-rate when available, else a labelled proxy.

    Uses :func:`ml.features.atmospheric_profile.combine_inversion`, which
    requires >=2 stored pressure-level temperatures (temperature_1000hPa ..
    700hPa) to compute a real lapse rate. When those are missing it falls back
    to the documented PBL-height *proxy* and is tagged ``source="pbl_proxy"``
    and ``provenance="ESTIMATED"`` so nobody mistakes it for a measurement.
    A surface-temperature threshold is never used.
    """
    from ml.features.atmospheric_profile import combine_inversion

    temps: dict[float, float] = {}
    for p in (1000, 925, 850, 700):
        val = _float(getattr(reading, f"temperature_{p}hPa", None))
        if val is not None:
            temps[p] = val
    pbl = _float(getattr(reading, "pbl_height", None))

    analysis = combine_inversion(pbl, temps if len(temps) >= 2 else None)
    profile_available = bool(analysis.get("profile_available", False))

    if profile_available:
        provenance = "DERIVED"
        limitations = [
            "Vertical pressure-level temperatures are Open-Meteo model fields.",
        ]
    else:
        provenance = "ESTIMATED"
        limitations = [
            "Vertical temperature profile unavailable (fewer than 2 stored pressure levels):",
            "inversion indicator is a PBL-height PROXY, not a measured lapse rate.",
            "It cannot detect elevated/mid-tropospheric inversions and may miss "
            "inversions that occur despite a deep PBL.",
        ]

    return {
        "detected": bool(analysis.get("inversion_detected", False)),
        "category": str(analysis.get("inversion_category", "unknown")),
        "strength": _float(analysis.get("inversion_strength", 0.0)),
        "source": str(analysis.get("inversion_source", "unavailable")),
        "provenance": provenance,
        "base_pressure_hpa": _float(analysis.get("inversion_base_pressure")),
        "top_pressure_hpa": _float(analysis.get("inversion_top_pressure")),
        "strongest_gradient_k100hpa": _float(analysis.get("strongest_layer_gradient")),
        "lapse_unit": "K per 100 hPa",
        "profile_available": profile_available,
        "pbl_category": str(analysis.get("pbl_category", "unknown")),
        "dispersion_condition": str(analysis.get("dispersion_condition", "UNKNOWN")),
        "normalized": _clip01(analysis.get("inversion_strength", 0.0)),
        "limitations": limitations,
    }


def _compass(direction: float | None) -> str | None:
    if direction is None:
        return None
    pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    deg = float(direction)
    idx = int((deg % 360.0 + 11.25) / 22.5) % 16
    return pts[idx]


def trapping_index(
    wind: dict[str, Any],
    pbl: dict[str, Any],
    vent: dict[str, Any],
    inv: dict[str, Any],
    pm25: float | None,
) -> dict[str, Any]:
    """Composite pollution-trapping indicator (dispersion × observed loading).

    Trapping is the *propensity* of the current atmosphere to retain pollution
    near the surface, not an attribution of any pollutant to any source.
    """
    vn = wind.get("normalized")
    pn = pbl.get("normalized")
    cen = vent.get("normalized")
    invn = inv.get("normalized")
    if cen is None and (vn is None or pn is None):
        return {
            "score": None,
            "category": "unavailable",
            "label": "Trapping index unavailable",
            "normalized": None,
            "provenance": "DERIVED",
            "factors": ["Insufficient meteorological inputs."],
        }
    # Collapse the three meteorology indicators into a dispersion quality 0..1.
    q_meteo = (
        W_VENT * (cen if cen is not None else 0.5)
        + W_PBL * (pn if pn is not None else 0.5)
        + W_INV * (1.0 - (invn if invn is not None else 0.0))
    )
    trap_meteo = _clip01(1.0 - q_meteo)
    trap_meteo = 0.0 if trap_meteo is None else trap_meteo

    pm = _float(pm25)
    if pm is not None and pm > 0:
        pm_norm = _clip01((pm - PM25_REF_GOOD) / (PM25_REF_SEVERE - PM25_REF_GOOD))
        pm_norm = 0.0 if pm_norm is None else pm_norm
        score = _clip01(W_DISPERSION * trap_meteo + W_OBSERVED * pm_norm)
        loading_note = f"Observed PM2.5 {round(pm, 1)} µg/m3 ({round(pm_norm, 3)} normalized) weights trapping {'higher' if pm_norm > trap_meteo else 'lower'}."
    else:
        score = trap_meteo
        loading_note = "No current PM2.5 -> trapping computed from meteorology only."

    if score is None:
        return {
            "score": None,
            "category": "unavailable",
            "label": "unavailable",
            "normalized": None,
            "provenance": "DERIVED",
            "factors": [loading_note],
        }
    if score < 0.33:
        cat, label = "low", "Low trapping tendency"
    elif score < 0.55:
        cat, label = "moderate", "Moderate trapping tendency"
    elif score < 0.75:
        cat, label = "high", "High trapping tendency"
    else:
        cat, label = "severe", "Severe trapping tendency"

    factors = [
        f"Ventilation coefficient {'<=3000' if vent.get('normalized') is not None and vent['normalized'] < 0.5 else '>=6000'} m2/s band: {vent.get('category', 'unavailable')}",
        f"PBL: {pbl.get('category', 'unavailable')} ({pbl.get('pbl_height_m', 'n/a')} m)",
        f"Inversion: {inv.get('category', 'unknown')} (source {inv.get('source', '?')}, strength {inv.get('strength', 0.0)})",
        f"Wind: {wind.get('category', 'unavailable')} ({wind.get('wind_speed_mps', 'n/a')} m/s)",
        loading_note,
    ]
    return {
        "score": round(score, 4),
        "category": cat,
        "label": label,
        "normalized": round(score, 4),
        "provenance": "DERIVED",
        "factors": factors,
    }


def _utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _age_hours(dt: datetime | None, now: datetime) -> float | None:
    naive = _utc_naive(dt)
    if naive is None:
        return None
    return round(max(0.0, (now - naive).total_seconds() / 3600.0), 2)


def analyze_station(db, station, now: datetime | None = None) -> dict[str, Any]:
    """Analyze the latest stored weather + pollution for one station.

    The latest weather reading whose timestamp is not ahead of ``now`` is used
    (open-meteo rows can include forecast hours in the future). If every stored
    row is ahead of now, the newest row is used and flagged.
    """
    now = now or datetime.now(UTC).replace(tzinfo=None)
    from ..models.db_models import PollutionReading, WeatherReading

    rows = (
        db.query(WeatherReading)
        .filter(WeatherReading.station_id == station.id)
        .order_by(WeatherReading.timestamp.desc())
        .limit(1000)
        .all()
    )
    weather: WeatherReading | None = None
    for r in rows:
        ts = _utc_naive(r.timestamp)
        if ts is not None and ts <= now:
            weather = r
            break
    if weather is None and rows:
        weather = rows[0]
    flags: list[str] = []
    if weather is not None:
        wts = _utc_naive(weather.timestamp)  # type: ignore[arg-type]
        if wts is not None and wts > now:
            flags.append(
                "all stored weather readings are ahead of the current time; "
                "results use the newest row (a model forecast hour, not a measurement)."
            )
    pollution = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station.id)
        .order_by(PollutionReading.timestamp.desc())
        .first()
    )
    pollution = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station.id)
        .order_by(PollutionReading.timestamp.desc())
        .first()
    )

    wind_raw = _float(getattr(weather, "wind_speed", None))
    direction = _float(getattr(weather, "wind_direction", None))
    pbl_raw = _float(getattr(weather, "pbl_height", None))

    wind = classify_wind(wind_raw)
    if direction is not None:
        wind["wind_direction_deg"] = round(direction, 1)
        wind["compass_from"] = _compass(direction)
    pbl = classify_pbl(pbl_raw)
    vent = ventilation_condition(wind_raw, pbl_raw)
    inv = inversion_indicator(weather) if weather is not None else None
    pm25 = _float(getattr(pollution, "pm25", None))
    trap = trapping_index(wind, pbl, vent, inv or {}, pm25)

    if weather is None or inv is None:  # no weather at all
        base = {
            "station": station.name,
            "station_id": station.id,
            "analyzed_at": now,
            "weather_timestamp": None,
            "pollution_timestamp": pollution.timestamp if pollution else None,
            "weather_age_hours": None,
            "pollution_age_hours": _age_hours(pollution.timestamp, now) if pollution else None,
            "flags": flags or None,
            "inputs": {},
            "wind": wind,
            "pbl": pbl,
            "ventilation": vent,
            "inversion": None,
            "trapping": trap,
            "features": {
                "wind": wind.get("normalized"),
                "pbl": pbl.get("normalized"),
                "ventilation": vent.get("normalized"),
                "inversion": None,
                "trapping": trap.get("normalized"),
            },
        }
        return base

    inputs = {
        "wind_speed_mps": wind_raw,
        "wind_direction_deg": direction,
        "pbl_height_m": pbl_raw,
        "pressure_msl_hpa": _float(getattr(weather, "pressure_msl", None)),
        "surface_pressure_hpa": _float(getattr(weather, "surface_pressure", None)),
        "temperature_c": _float(getattr(weather, "temperature", None)),
        "humidity_pct": _float(getattr(weather, "humidity", None)),
        "pm25_ugm3": pm25,
        "vertical_temperature_profile_c": {
            p: _float(getattr(weather, f"temperature_{p}hPa", None))
            for p in (1000, 925, 850, 700)
            if getattr(weather, f"temperature_{p}hPa", None) is not None
        },
    }

    return {
        "station": station.name,
        "station_id": station.id,
        "analyzed_at": now,
        "weather_timestamp": weather.timestamp,
        "pollution_timestamp": pollution.timestamp if pollution else None,
        "weather_age_hours": _age_hours(weather.timestamp, now) if weather else None,  # type: ignore[arg-type]
        "pollution_age_hours": _age_hours(pollution.timestamp, now) if pollution else None,
        "flags": flags or None,
        "inputs": inputs,
        "input_basis": {
            "weather": "Open-Meteo (ERA5-informed archive + short-range forecast) — model values, not in-situ instruments",
            "pollution": "CPCB observations (observed)",
        },
        "wind": wind,
        "pbl": pbl,
        "ventilation": vent,
        "inversion": inv,
        "trapping": trap,
        "features": {
            "wind": wind.get("normalized"),
            "pbl": pbl.get("normalized"),
            "ventilation": vent.get("normalized"),
            "inversion": inv.get("normalized"),
            "trapping": trap.get("normalized"),
        },
    }


def get_current_atmosphere(db) -> dict[str, Any]:
    """Compute the current atmosphere for all stations + a region summary."""
    now = datetime.now(UTC).replace(tzinfo=None)
    from ..models.db_models import Station

    stations = db.query(Station).order_by(Station.name).all()
    rows = [analyze_station(db, s, now) for s in stations]

    def _mean(key: str) -> float | None:
        vals = [r["features"].get(key) for r in rows if r["features"].get(key) is not None]
        return round(float(np.mean(vals)), 4) if vals else None

    vent_vals = [r["ventilation"] for r in rows if r["ventilation"].get("ventilation_coefficient_m2s") is not None]
    inv_sources = [r["inversion"]["source"] for r in rows if r.get("inversion")]

    summary = {
        "stations_analyzed": len(rows),
        "stations_with_weather": sum(1 for r in rows if r["weather_timestamp"] is not None),
        "stations_with_pollution": sum(1 for r in rows if r["pollution_timestamp"] is not None),
        "measurement_clock": max(
            (
                r["weather_timestamp"]
                for r in rows
                if (wt := r["weather_timestamp"]) is not None and (wts := _utc_naive(wt)) is not None and wts <= now
            ),
            default=None,
        ),
        "mean_features": {
            "wind": _mean("wind"),
            "pbl": _mean("pbl"),
            "ventilation": _mean("ventilation"),
            "inversion": _mean("inversion"),
            "trapping": _mean("trapping"),
        },
        "ventilation_regime": (
            min(r["ventilation_coefficient_m2s"] for r in vent_vals) if vent_vals else None,
            max(r["ventilation_coefficient_m2s"] for r in vent_vals) if vent_vals else None,
        ),
        "worst_trapping_station": (
            max((row["station"], row["trapping"]["score"]) for row in rows if row["trapping"].get("score") is not None)
            if any(row["trapping"].get("score") is not None for row in rows)
            else None
        ),
        "inversion_sources_seen": sorted(set(inv_sources)),
    }

    return {
        "generated_at": now,
        "region": REGION,
        "methodology": {
            "version": METHODOLOGY_VERSION,
            "formulas": {
                "ventilation_coefficient_m2s": "wind_speed [m/s] * pbl_height [m]",
                "inversion_gradient_k100hpa": "(T_top - T_base) / (p_base - p_top) * 100",
                "inversion_strength": "normalized 0..1 from vertical lapse-rate (or PBL proxy when profile unavailable)",
                "dispersion_quality": "0.50*ventilation_norm + 0.20*pbl_norm + 0.30*(1 - inversion_norm)",
                "trapping_index": "clip(0.70*(1 - dispersion_quality) + 0.30*pm25_norm, 0, 1) — meteorology-only when PM2.5 absent",
            },
            "notes": [
                "Inversion is detected from the vertical temperature lapse-rate, never a surface-temperature threshold.",
                "When fewer than 2 stored pressure levels exist the inversion indicator is a PBL-height PROXY (provenance=ESTIMATED).",
                "No XGBoost/GRU or any ML is used; all indicators are deterministic from stored data.",
                "All normalized features lie in [0,1]; higher wind/pbl/ventilation mean more dispersion, higher inversion/trapping mean more trapping.",
            ],
        },
        "summary": summary,
        "stations": rows,
    }
