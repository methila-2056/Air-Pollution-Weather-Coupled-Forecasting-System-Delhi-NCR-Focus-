from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ml.features.coupling import coupling_feedback_score

from ..database import get_db
from ..models.db_models import CouplingState, PollutionReading, Station, WeatherReading
from ..schemas.schemas import (
    CouplingDiagnostics,
    CouplingFeaturesResponse,
    CouplingResponse,
    CouplingStateListResponse,
    CouplingStateSnapshot,
)

router = APIRouter()


@router.get("/coupling/state", response_model=CouplingStateListResponse)
def list_coupling_states(db: Session = Depends(get_db)):
    """List the latest persisted coupling snapshots for every station (Phase 30).

    The snapshots are the write-through outputs of ``/coupling/features``:
    nine coupling features plus inversion / PBL / fire-transport fields,
    coupling-state band, contributing domains and data-quality label. Only
    stations whose features have been computed (persisted) appear here.
    """
    rows = (
        db.query(CouplingState, Station)
        .join(Station, Station.id == CouplingState.station_id)
        .order_by(Station.name)
        .all()
    )
    return CouplingStateListResponse(
        generated_at=datetime.now(UTC),
        count=len(rows),
        states=[_snapshot(state, station) for state, station in rows],
    )


@router.get("/coupling/state/{station_name}", response_model=CouplingStateSnapshot)
def get_coupling_state(station_name: str, db: Session = Depends(get_db)):
    """Latest persisted coupling snapshot for one station (Phase 30)."""
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")
    row = (
        db.query(CouplingState)
        .filter(CouplingState.station_id == station.id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No coupling-state snapshot persisted yet for '{station_name}' "
            "(call /api/coupling/features first)",
        )
    return _snapshot(row, station)


def _snapshot(row: CouplingState, station: Station) -> CouplingStateSnapshot:
    return CouplingStateSnapshot(
        station=station.name,
        station_id=station.id,
        computed_at=row.computed_at,
        wind_speed_mps=row.wind_speed_mps,
        wind_direction_deg=row.wind_direction_deg,
        pbl_height_m=row.pbl_height_m,
        inversion_detected=row.inversion_detected,
        inversion_strength=row.inversion_strength,
        inversion_category=row.inversion_category,
        inversion_source=row.inversion_source,
        fire_count=row.fire_count,
        upwind_fire_count=row.upwind_fire_count,
        nearest_fire_distance_km=row.nearest_fire_distance_km,
        fire_impact_score=row.fire_impact_score,
        wind_alignment_pct=row.wind_alignment_pct,
        fire_transport_direction=row.fire_transport_direction,
        fire_transport_time_hours=row.fire_transport_time_hours,
        fire_transport_influence=row.fire_transport_influence,
        dispersion_potential=row.dispersion_potential,
        accumulation_potential=row.accumulation_potential,
        inversion_trapping_potential=row.inversion_trapping_potential,
        pollution_stagnation_index=row.pollution_stagnation_index,
        aerosol_accumulation_potential=row.aerosol_accumulation_potential,
        regional_transport_potential=row.regional_transport_potential,
        ozone_photochemical_potential=row.ozone_photochemical_potential,
        meteorology_pollution_interaction=row.meteorology_pollution_interaction,
        coupling_state=row.coupling_state,
        coupling_domains=row.coupling_domains,
        data_quality=row.data_quality,
        weather_reading_timestamp=row.weather_reading_timestamp,
        pollution_reading_timestamp=row.pollution_reading_timestamp,
    )


@router.get("/coupling/features/{station_name}", response_model=CouplingFeaturesResponse)
def get_coupling_features(station_name: str, db: Session = Depends(get_db)):
    """Nine SIH26082 meteorology-pollution-fire coupling features (real data).

    Computes dispersion/accumulation/inversion-trapping/stagnation/aerosol/
    fire-transport/regional-transport/ozone-photochemical/feedback-surrogate
    features from the latest STORED observations (CPCB pollution, Open-Meteo
    weather incl. vertical pressure-level temperatures, NASA FIRMS fires).
    Missing inputs yield ``value: null`` + ``available: false`` — never an
    invented number.
    """
    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found")

    from ..services.coupling_service import get_coupling_features as _features

    return _features(db, station)


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
        timestamp=datetime.now(UTC).replace(tzinfo=None),
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
