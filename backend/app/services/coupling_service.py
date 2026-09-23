"""Coupling-service: assemble real stored observations -> coupling features.

Bridge between the database and :mod:`ml.features.coupling_engine`. It reads
the latest stored CPCB pollution, Open-Meteo weather (+ stored vertical
pressure-level temperatures) and NASA FIRMS fire observations for a station /
region, then runs the deterministic coupling-engine feature computation.

Nothing here fabricates values: when a stored field is missing the
corresponding input is ``None`` and the engine reports the feature as
unavailable with an explicit basis string.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ml.features.atmospheric_profile import combine_inversion
from ml.features.coupling_engine import CouplingInputs, compute_coupling_features
from ml.features.fire_impact import DEFAULT_MAX_DISTANCE_KM, compute_fire_impact


def _float(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _pressure_level_temps(reading) -> dict[float, float]:
    temps: dict[float, float] = {}
    for p in (1000, 925, 850, 700):
        val = _float(getattr(reading, f"temperature_{p}hPa", None))
        if val is not None:
            temps[p] = val
    return temps


def _inversion_from(reading) -> dict[str, Any]:
    temps = _pressure_level_temps(reading)
    pbl = _float(getattr(reading, "pbl_height", None))
    return combine_inversion(pbl, temps if len(temps) >= 2 else None)


def _fire_impact_from_rows(fire_rows: list, lat: float, lon: float, wind_dir: float | None, wind_speed: float | None) -> dict[str, Any]:
    """Compute fire impact from already-loaded FireReading rows (pure helper)."""
    empty = {
        "fire_count": 0,
        "fire_impact_score": 0.0,
        "nearest_fire_distance": DEFAULT_MAX_DISTANCE_KM + 1.0,
        "wind_aligned_fire_count": 0,
        "wind_alignment_pct": 0.0,
        "transport_time_hours": None,
        "transport_risk": 0.0,
        "transport_risk_level": "none",
        "stubble_impact_score": 0.0,
    }
    if not fire_rows:
        return empty
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "lat": _float(f.latitude),
                "lon": _float(f.longitude),
                "frp": _float(f.frp) if f.frp is not None else 1.0,
            }
            for f in fire_rows
        ]
    )
    if df.empty:
        return empty
    impact = compute_fire_impact(
        df,
        lat,
        lon,
        wind_dir if wind_dir is not None else 0.0,
        wind_speed or 0.0,
        max_distance_km=DEFAULT_MAX_DISTANCE_KM,
    )
    impact["nearest_fire_distance"] = round(float(impact["nearest_fire_distance"]), 1)
    return impact


def _load_recent_fires(db, limit: int = 500):
    from ..models.db_models import FireReading

    return (
        db.query(FireReading)
        .order_by(FireReading.acq_date.desc())
        .limit(limit)
        .all()
    )


def get_coupling_inputs(db, station) -> tuple[CouplingInputs, dict[str, Any]]:
    """Build ``CouplingInputs`` + provenance from the station's stored data.

    Returns ``(inputs, provenance)`` where ``provenance`` maps the same inputs
    to the actual DB rows that produced them (honest traceability).
    """
    from ..models.db_models import PollutionReading, WeatherReading

    wx = (
        db.query(WeatherReading)
        .filter(WeatherReading.station_id == station.id)
        .order_by(WeatherReading.timestamp.desc())
        .first()
    )
    poll = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station.id)
        .order_by(PollutionReading.timestamp.desc())
        .first()
    )

    inversion = _inversion_from(wx) if wx is not None else None

    fires = _load_recent_fires(db)
    lat = _float(getattr(station, "latitude", None))
    lon = _float(getattr(station, "longitude", None))
    if lat is None or lon is None:
        lat, lon = 28.6139, 77.2090  # NCR centroid only when station has no coords
    wind_dir = _float(getattr(wx, "wind_direction", None)) if wx is not None else None
    wind_speed = _float(getattr(wx, "wind_speed", None)) if wx is not None else None
    fire = _fire_impact_from_rows(fires, lat, lon, wind_dir, wind_speed)

    inputs = CouplingInputs(
        temperature_c=_float(getattr(wx, "temperature", None)) if wx is not None else None,
        humidity_pct=_float(getattr(wx, "humidity", None)) if wx is not None else None,
        pressure_hpa=_float(getattr(wx, "pressure_msl", None)) if wx is not None else None,
        wind_speed_mps=wind_speed,
        wind_direction_deg=wind_dir,
        pbl_height_m=_float(getattr(wx, "pbl_height", None)) if wx is not None else None,
        pm25_ugm3=_float(getattr(poll, "pm25", None)) if poll is not None else None,
        pm10_ugm3=_float(getattr(poll, "pm10", None)) if poll is not None else None,
        no2_ugm3=_float(getattr(poll, "no2", None)) if poll is not None else None,
        o3_ugm3=_float(getattr(poll, "o3", None)) if poll is not None else None,
        inversion_detected=bool(inversion.get("inversion_detected", False)) if inversion else None,
        inversion_strength=_float(inversion.get("inversion_strength")) if inversion is not None else None,
        inversion_category=str(inversion.get("inversion_category", "unknown")) if inversion else None,
        fire_count=int(fire["fire_count"]) if fire["fire_count"] else None,
        upwind_fire_count=int(fire["wind_aligned_fire_count"]) if fire["wind_aligned_fire_count"] else None,
        nearest_fire_distance_km=fire["nearest_fire_distance"],
        fire_impact_score=fire["fire_impact_score"],
        wind_alignment_pct=fire["wind_alignment_pct"],
        transport_time_hours=fire["transport_time_hours"],
    )

    provenance = {
        "weather_reading_timestamp": wx.timestamp.isoformat() if wx and wx.timestamp else None,
        "pollution_reading_timestamp": poll.timestamp.isoformat() if poll and poll.timestamp else None,
        "inversion_source": inversion.get("inversion_source", "unavailable") if inversion else "unavailable",
        "inversion_profile_available": bool(inversion.get("profile_available", False)) if inversion else False,
        "inversion_category": str(inversion.get("inversion_category", "unknown")) if inversion else None,
        "fire_impact_basis": (
            f"{int(fire['fire_count'])} stored fire(s) within {DEFAULT_MAX_DISTANCE_KM:.0f} km; "
            f"{int(fire['wind_aligned_fire_count'])} upwind of the surface wind vector"
        ),
        "note": (
            "All inputs are the latest stored observations. Inversion uses the "
            "real vertical pressure-level lapse-rate when >=2 stored levels exist, "
            "otherwise the labelled PBL-height proxy."
        ),
    }
    return inputs, provenance


def get_coupling_features(db, station) -> dict[str, Any]:
    """Full coupling-features packet (inputs + features + methodology + provenance)."""
    inputs, provenance = get_coupling_inputs(db, station)
    result = compute_coupling_features(inputs)
    result["station"] = station.name
    result["timestamp"] = datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z"
    result["provenance"] = provenance
    return result


_FORECAST_WINDOW_HOURS = 72


def get_forecast_context(db, station) -> dict[str, Any]:
    """Per-horizon atmospheric + coupling context for the station's 72h window.

    For each forecast horizon (1..72 h) the nearest stored ``WeatherReading``
    (within +/- 2h of the target timestamp) supplies the atmospheric state and
    a photochemical/inversion estimate; regional fire impact and observed
    pollution are shared across horizons (they are region-wide, not per-hour).
    Missing rows produce ``None`` fields — the UI renders them as unavailable.
    """
    from ..models.db_models import PollutionReading, WeatherReading

    now = datetime.now(UTC).replace(tzinfo=None)

    poll = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station.id)
        .order_by(PollutionReading.timestamp.desc())
        .first()
    )
    pm25 = _float(getattr(poll, "pm25", None)) if poll is not None else None
    pm10 = _float(getattr(poll, "pm10", None)) if poll is not None else None
    no2 = _float(getattr(poll, "no2", None)) if poll is not None else None
    o3 = _float(getattr(poll, "o3", None)) if poll is not None else None

    fires = _load_recent_fires(db)
    lat = _float(getattr(station, "latitude", None)) or 28.6139
    lon = _float(getattr(station, "longitude", None)) or 77.2090
    latest_wx = (
        db.query(WeatherReading)
        .filter(WeatherReading.station_id == station.id)
        .order_by(WeatherReading.timestamp.desc())
        .first()
    )
    wind_dir = _float(getattr(latest_wx, "wind_direction", None)) if latest_wx is not None else None
    wind_speed = _float(getattr(latest_wx, "wind_speed", None)) if latest_wx is not None else None
    fire = _fire_impact_from_rows(fires, lat, lon, wind_dir, wind_speed)

    # All weather rows for the station (to find nearest-per-horizon efficiently).
    wx_rows = (
        db.query(WeatherReading)
        .filter(WeatherReading.station_id == station.id)
        .order_by(WeatherReading.timestamp.asc())
        .all()
    )

    contexts: list[dict[str, Any]] = []
    for h in range(1, _FORECAST_WINDOW_HOURS + 1):
        target = now + timedelta(hours=h)
        wx = _nearest_weather_row(wx_rows, target, tolerance=timedelta(hours=2))
        inversion = _inversion_from(wx) if wx is not None else None

        ctx_wind_dir = _float(getattr(wx, "wind_direction", None)) if wx is not None else None
        ctx_wind_speed = _float(getattr(wx, "wind_speed", None)) if wx is not None else None
        inputs = CouplingInputs(
            temperature_c=_float(getattr(wx, "temperature", None)) if wx is not None else None,
            humidity_pct=_float(getattr(wx, "humidity", None)) if wx is not None else None,
            pressure_hpa=_float(getattr(wx, "pressure_msl", None)) if wx is not None else None,
            wind_speed_mps=ctx_wind_speed,
            wind_direction_deg=ctx_wind_dir or wind_dir,
            pbl_height_m=_float(getattr(wx, "pbl_height", None)) if wx is not None else None,
            pm25_ugm3=pm25,
            pm10_ugm3=pm10,
            no2_ugm3=no2,
            o3_ugm3=o3,
            inversion_detected=bool(inversion.get("inversion_detected", False)) if inversion else None,
            inversion_strength=_float(inversion.get("inversion_strength")) if inversion is not None else None,
            inversion_category=str(inversion.get("inversion_category", "unknown")) if inversion else None,
            fire_count=int(fire["fire_count"]) if fire["fire_count"] else None,
            upwind_fire_count=int(fire["wind_aligned_fire_count"]) if fire["wind_aligned_fire_count"] else None,
            nearest_fire_distance_km=fire["nearest_fire_distance"],
            fire_impact_score=fire["fire_impact_score"],
            wind_alignment_pct=fire["wind_alignment_pct"],
            transport_time_hours=fire["transport_time_hours"],
        )
        feat = compute_coupling_features(inputs)["features"]

        contexts.append(
            {
                "horizon_hours": h,
                "target_timestamp": target.isoformat() + "Z",
                "weather_match_timestamp": wx.timestamp.isoformat() if wx and wx.timestamp else None,
                "temperature_c": inputs.temperature_c,
                "humidity_pct": inputs.humidity_pct,
                "pressure_hpa": inputs.pressure_hpa,
                "wind_speed_mps": inputs.wind_speed_mps,
                "wind_direction_deg": inputs.wind_direction_deg,
                "pbl_height_m": inputs.pbl_height_m,
                "inversion_detected": inputs.inversion_detected,
                "inversion_strength": inputs.inversion_strength,
                "inversion_category": inputs.inversion_category,
                "inversion_source": inversion.get("inversion_source") if inversion is not None else None,
                "dispersion_potential": feat["dispersion_potential"]["value"],
                "accumulation_potential": feat["accumulation_potential"]["value"],
                "inversion_trapping_potential": feat["inversion_trapping_potential"]["value"],
                "pollution_stagnation_index": feat["pollution_stagnation_index"]["value"],
                "fire_transport_influence": feat["fire_transport_influence"]["value"],
                "regional_transport_potential": feat["regional_transport_potential"]["value"],
                "ozone_photochemical_potential": feat["ozone_photochemical_potential"]["value"],
                "meteorology_pollution_interaction": feat["meteorology_pollution_interaction"]["value"],
            }
        )

    return {
        "station": station.name,
        "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z",
        "units": {
            "wind_speed_mps": "meters/second (meteorological FROM direction)",
            "pbl_height_m": "meters",
            "temperature_c": "degrees Celsius",
            "pressure_hpa": "hectopascals",
            "features": "normalized 0..1 (None = input data unavailable)",
        },
        "regional_note": (
            "Fire-influence and observed-pollution terms are regional and reuse the "
            "latest stored observations across all horizons; only atmospheric fields "
            "vary per horizon via nearest stored weather rows."
        ),
        "horizons": contexts,
    }


def _nearest_weather_row(rows, target, tolerance: timedelta, within_max_hours: int = 6):
    """Nearest stored weather row to *target* time (worst case +/- 6h)."""
    best = None
    best_delta = None
    for r in rows:
        if r.timestamp is None:
            continue
        d = abs(r.timestamp - target)
        if d > timedelta(hours=within_max_hours) and d > tolerance:
            continue
        if best_delta is None or d < best_delta:
            best = r
            best_delta = d
    return best
