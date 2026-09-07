from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from ..database import get_db
from ..models.db_models import Station, PollutionReading, WeatherReading
from ..schemas.schemas import CouplingResponse, CouplingDiagnostics
from ml.features.coupling import coupling_feedback_score

router = APIRouter()


@router.get("/coupling/{station_name}", response_model=CouplingResponse)
def get_coupling_feedback(station_name: str, db: Session = Depends(get_db)):
    """Return two-way weather-chemistry coupling diagnostics for a station.

    Demonstrates the chemistry -> meteorology feedback path (aerosols suppress
    PBL / stabilise the boundary layer) alongside the meteorology -> chemistry
    path (stable PBL + low wind trap pollutants).
    """
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")

    poll = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station.id)
        .order_by(PollutionReading.timestamp.desc())
        .first()
    )
    wx = (
        db.query(WeatherReading)
        .filter(WeatherReading.station_id == station.id)
        .order_by(WeatherReading.timestamp.desc())
        .first()
    )

    pm25 = poll.pm25 if poll else None
    pbl = wx.pbl_height if wx else None
    wind = wx.wind_speed if wx else None
    hour = wx.timestamp.hour if wx and wx.timestamp else 12

    diag = coupling_feedback_score(pm25 or 0.0, pbl or 600.0, wind or 4.0, hour)

    narrative = _build_narrative(pm25, pbl, wind, diag)

    return CouplingResponse(
        station=station.name,
        timestamp=datetime.utcnow(),
        pm25=pm25,
        pbl_height=pbl,
        wind_speed=wind,
        diag=CouplingDiagnostics(**diag),
        narrative=narrative,
    )


def _build_narrative(pm25, pbl, wind, diag: dict) -> list[str]:
    lines = []
    if pm25 is not None and pm25 >= 120:
        lines.append(
            f"Heavy PM2.5 loading ({pm25:.0f} µg/m³) is attenuating solar radiation "
            "(transmittance ~{0:.0%}).".format(diag["radiation_transmittance"])
        )
    elif pm25 is not None and pm25 >= 60:
        lines.append(
            f"Moderate PM2.5 loading ({pm25:.0f} µg/m³) is dampening daytime "
            "solar heating of the surface."
        )

    if diag["pbl_suppression_factor"] < 0.95:
        lines.append(
            "Aerosol radiative forcing is suppressing planetary boundary layer growth "
            f"(effective PBL reduced to ~{diag['corrected_pbl_height']:.0f} m)."
        )

    stability = diag["stability_coupling_index"]
    if stability >= 0.6:
        lines.append(
            "The coupled system is strongly self-reinforcing: a stable, aerosol-suppressed "
            "boundary layer retains pollutants near the surface, further increasing aerosol load."
        )
    elif stability >= 0.35:
        lines.append(
            "Moderate two-way coupling detected: reduced mixing is moderately enhancing "
            "near-surface pollutant retention."
        )
    else:
        lines.append(
            "Weak coupling feedback: dispersion conditions favour pollutant removal "
            "(no strong aerosol-PBL trapping loop)."
        )
    return lines