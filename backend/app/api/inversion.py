from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import Station, WeatherReading
from ..schemas.schemas import InversionResponse

router = APIRouter()

_PBL_WEAK_M = 500.0


def classify_inversion(pbl_height):
    """PBL-height proxy inversion classification (legacy / fallback).

    Returns (detected, category_label, risk_label) — kept backward-compatible
    with the reported string fields.
    """
    if pbl_height is None:
        return "unknown", "unknown", "unknown"
    if pbl_height < 150:
        return True, "Strong", "HIGH"
    elif pbl_height < 300:
        return True, "Moderate", "MEDIUM"
    elif pbl_height < 500:
        return True, "Weak", "LOW"
    else:
        return False, "None", "MINIMAL"


def _temp_by_level(reading) -> dict:
    """Pull pressure-level temperatures (degC) from the DB row."""
    temps = {}
    for p in (1000, 925, 850, 700):
        val = getattr(reading, f"temperature_{p}hPa", None)
        if val is not None:
            temps[p] = float(val)
    return temps


def _compute_inversion(reading) -> dict:
    """Compute inversion via lapse rate when vertical data exists, else proxy.

    Returns a dict with keys:
      inversion_detected, inversion_category, inversion_strength (label),
      inversion_strength_score (0-1), trapping_risk, inversion_source,
      inversion_base_pressure, inversion_top_pressure, strongest_layer_gradient,
      low_pbl_flag, pbl_category, dispersion_condition.
    """
    from ml.features.atmospheric_profile import combine_inversion

    temps = _temp_by_level(reading)
    pbl = getattr(reading, "pbl_height", None)

    analysis = combine_inversion(pbl, temps if len(temps) >= 2 else None)

    # Reuse the legacy label mapping for backward-compatible response fields.
    if analysis["profile_available"]:
        category = analysis["inversion_category"]  # none/weak/moderate/strong
        label = {  # capitalize for existing UI expectations
            "none": "None", "weak": "Weak", "moderate": "Moderate", "strong": "Strong",
            "unknown": "unknown",
        }.get(category, "unknown")
        risk = {
            "none": "MINIMAL", "weak": "LOW", "moderate": "MEDIUM", "strong": "HIGH",
            "unknown": "UNKNOWN",
        }.get(category, "UNKNOWN")
    else:
        _, label, risk = classify_inversion(pbl)

    return {
        "inversion_detected": bool(analysis.get("inversion_detected", False)),
        "inversion_category": analysis.get("inversion_category", "none"),
        "inversion_strength": label,
        "inversion_strength_score": float(analysis.get("inversion_strength", 0.0)),
        "trapping_risk": risk,
        "inversion_source": analysis.get("inversion_source", "pbl_proxy"),
        "inversion_base_pressure": analysis.get("inversion_base_pressure"),
        "inversion_top_pressure": analysis.get("inversion_top_pressure"),
        "strongest_layer_gradient": analysis.get("strongest_layer_gradient"),
        "low_pbl_flag": bool(analysis.get("low_pbl_flag", False)),
        "pbl_category": analysis.get("pbl_category", "unknown"),
        "dispersion_condition": analysis.get("dispersion_condition", "UNKNOWN"),
    }


@router.get("/inversion/{station_name}", response_model=InversionResponse)
def get_inversion(station_name: str, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
    reading = db.query(WeatherReading).filter(WeatherReading.station_id == station.id).order_by(WeatherReading.timestamp.desc()).first()
    if not reading:
        raise HTTPException(status_code=404, detail=f"No weather data for station '{station_name}'")
    inv = _compute_inversion(reading)
    return InversionResponse(
        station=station_name,
        timestamp=reading.timestamp,
        pbl_height=reading.pbl_height,
        inversion_detected=inv["inversion_detected"],
        inversion_strength=inv["inversion_strength"],
        inversion_strength_score=inv.get("inversion_strength_score"),
        inversion_category=inv.get("inversion_category"),
        inversion_source=inv.get("inversion_source"),
        inversion_base_pressure=inv.get("inversion_base_pressure"),
        inversion_top_pressure=inv.get("inversion_top_pressure"),
        strongest_layer_gradient=inv.get("strongest_layer_gradient"),
        low_pbl_flag=inv.get("low_pbl_flag"),
        pbl_category=inv.get("pbl_category"),
        dispersion_condition=inv.get("dispersion_condition"),
        trapping_risk=inv["trapping_risk"],
    )
