"""Coupling engine — meteorology-pollution-fire interaction features (SIH26082).

The SIH26082 problem statement asks a coupled air-quality-weather system to
expose a set of *scientifically interpretable* coupling features. This module
computes those named features from **stored, real observations** (CPCB
pollution, Open-Meteo weather + vertical profile, NASA FIRMS fires) — never
from random numbers and never by overwriting a measured value.

Features (all normalized 0..1, higher = more of the named tendency):

  dispersion_potential            how likely the current atmosphere disperses
                                  pollutants (wind x PBL + inversion discount)
  accumulation_potential          complement of dispersion (1 - dispersion)
  inversion_trapping_potential    trapping from a capping inversion / shallow PBL
  pollution_stagnation_index      low wind + low PBL + inversion -> stagnation
  aerosol_accumulation_potential  observed PM2.5 load x trapping propensity
  fire_transport_influence        upwind fire intensity/distance/alignment
  regional_transport_potential    likelihood regional fire smoke advects to NCR
  ozone_photochemical_potential   warmth + stagnation + NO2 precursor potential
  meteorology_pollution_interaction  composite "data-driven feedback surrogate"

Every feature carries a ``basis`` string describing exactly which stored inputs
entered the formula, and a ``available`` flag. When an input is missing the
feature is reported as ``None`` (the UI renders "Data unavailable"), it is
never invented. Constants mirror the rest of the codebase (see
``atmosphere_service`` PBL/ventilation references and ``fire_impact``).

This module is deliberately pure/deterministic so it can be unit-tested
without a database.
"""

from __future__ import annotations

from typing import Any

# Normalization anchors (shared with backend/app/services/atmosphere_service.py).
WIND_REF_MPS = 7.0            # m/s that counts as "full" horizontal ventilation
PBL_REF_M = 1500.0            # m that counts as "full" vertical mixing depth
PM25_REF_GOOD = 35.0          # CPCB 24h "satisfactory" upper bound (µg/m3)
PM25_REF_SEVERE = 300.0       # CPCB emergency band (µg/m3)
NO2_REF = 120.0               # µg/m3 anchor for NO2 precursor availability
TEMP_WARM_C = 25.0            # °C above which photochemical potential ramps
TEMP_HOT_C = 40.0             # °C at which the temperature term saturates
VENT_REF = 6000.0             # m2/s ventilation coefficient anchor
UPWIND_COUNT_SATURATION = 50.0  # upwind fires that fully saturate the count term
FIRE_DIST_REF_KM = 500.0      # regional fire radius (fire_impact.DEFAULT_MAX_DISTANCE_KM)
TRANSPORT_TIME_REF_H = 24.0   # h at which transport-time term fully decays


def _clip01(v) -> float | None:
    if v is None:
        return None
    try:
        return round(max(0.0, min(1.0, float(v))), 4)
    except (TypeError, ValueError):
        return None


def _norm(value, ref: float) -> float | None:
    if value is None:
        return None
    try:
        return _clip01(float(value) / ref)
    except (TypeError, ValueError):
        return None


def _as_float(value, default: float):
    try:
        if value is None:
            return None
        f = float(value)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _band(value, lo, hi) -> str | None:
    if value is None:
        return None
    if value < lo:
        return "Low"
    if value < hi:
        return "Moderate"
    return "High"


class CouplingInputs:
    """Typed container of the real inputs feeding the coupling engine.

    All fields are optional; missing inputs produce ``None`` features with an
    explicit basis explaining which input was unavailable.
    """

    def __init__(
        self,
        *,
        temperature_c: float | None = None,
        humidity_pct: float | None = None,
        pressure_hpa: float | None = None,
        wind_speed_mps: float | None = None,
        wind_direction_deg: float | None = None,
        pbl_height_m: float | None = None,
        pm25_ugm3: float | None = None,
        pm10_ugm3: float | None = None,
        no2_ugm3: float | None = None,
        o3_ugm3: float | None = None,
        inversion_detected: bool | None = None,
        inversion_strength: float | None = None,       # 0..1 (lapse-rate or proxy)
        inversion_category: str | None = None,
        fire_count: int | None = None,
        upwind_fire_count: int | None = None,
        nearest_fire_distance_km: float | None = None,
        fire_impact_score: float | None = None,        # 0..1 fire_impact module
        wind_alignment_pct: float | None = None,
        transport_time_hours: float | None = None,
    ) -> None:
        self.temperature_c = _as_float(temperature_c, 0.0)
        self.humidity_pct = _as_float(humidity_pct, 0.0)
        self.pressure_hpa = _as_float(pressure_hpa, 0.0)
        self.wind_speed_mps = _as_float(wind_speed_mps, 0.0)
        self.wind_direction_deg = _as_float(wind_direction_deg, 0.0)
        self.pbl_height_m = _as_float(pbl_height_m, 0.0)
        self.pm25_ugm3 = _as_float(pm25_ugm3, 0.0)
        self.pm10_ugm3 = _as_float(pm10_ugm3, 0.0)
        self.no2_ugm3 = _as_float(no2_ugm3, 0.0)
        self.o3_ugm3 = _as_float(o3_ugm3, 0.0)
        self.inversion_detected = inversion_detected
        self.inversion_strength = _clip01(inversion_strength)
        self.inversion_category = inversion_category
        self.fire_count = int(fire_count) if fire_count is not None else None
        self.upwind_fire_count = int(upwind_fire_count) if upwind_fire_count is not None else None
        self.nearest_fire_distance_km = _as_float(nearest_fire_distance_km, 0.0)
        self.fire_impact_score = _clip01(fire_impact_score)
        self.wind_alignment_pct = _as_float(wind_alignment_pct, 0.0)
        self.transport_time_hours = _as_float(transport_time_hours, 0.0)


def compute_coupling_features(inputs: CouplingInputs) -> dict[str, Any]:
    """Compute the nine SIH26082 coupling features from real stored inputs.

    Returns a dict with the features plus ``inputs`` and ``methodology`` so
    consumers can always see exactly what went into each number.
    """
    wind = inputs.wind_speed_mps
    wind_norm = _norm(wind, WIND_REF_MPS)
    pbl = inputs.pbl_height_m
    pbl_norm = _norm(pbl, PBL_REF_M)
    inv = inputs.inversion_strength
    inv_detected = bool(inputs.inversion_detected) if inputs.inversion_detected is not None else (inv is not None and (inv or 0.0) > 0.0)
    pm25 = inputs.pm25_ugm3
    temp = inputs.temperature_c

    vent = None
    if wind is not None and pbl is not None:
        vent = _norm(wind * pbl, VENT_REF)
    vent_norm = vent

    # ---- 1. dispersion_potential -------------------------------------------
    # Wind x PBL ventilation, discounted by any capping inversion (mirrors
    # atmosphere_service dispersion_quality). Pure meteorology -> chemistry.
    if vent_norm is not None:
        q = 0.5 * vent_norm + 0.2 * (pbl_norm or 0.0) + 0.3 * (1.0 - (inv or 0.0))
        dispersion_potential = _clip01(q)
        disp_basis = (
            "0.50*ventilation_norm + 0.20*pbl_norm + 0.30*(1-inversion_strength), "
            f"ventilation_norm={vent_norm}, pbl_norm={pbl_norm}, inversion_strength={inv}"
        )
    else:
        dispersion_potential = None
        disp_basis = "requires wind_speed and pbl_height (ventilation coefficient)"

    # ---- 2. accumulation_potential ------------------------------------------
    if dispersion_potential is not None:
        accumulation_potential = _clip01(1.0 - dispersion_potential)
        accum_basis = "1 - dispersion_potential"
    else:
        accumulation_potential = None
        accum_basis = "unavailable: dispersion_potential unavailable"

    # ---- 3. inversion_trapping_potential ------------------------------------
    if inv is not None or pbl_norm is not None:
        pbl_term = _clip01(1.0 - (pbl_norm or 0.0))  # shallow PBL -> more trapping
        inversion_trapping_potential = _clip01(0.5 * (inv or 0.0) + 0.5 * (pbl_term or 0.0))
        trap_basis = (
            "0.50*inversion_strength + 0.50*(1 - pbl_norm), "
            f"inversion_strength={inv}, pbl_norm={pbl_norm}"
        )
    else:
        inversion_trapping_potential = None
        trap_basis = "requires inversion_strength or pbl_height"

    # ---- 4. pollution_stagnation_index --------------------------------------
    if wind_norm is not None or pbl_norm is not None or inv is not None:
        stagnation = (
            0.4 * (1.0 - (wind_norm or 0.0))
            + 0.4 * (1.0 - (pbl_norm or 0.0))
            + 0.2 * (inv or 0.0)
        )
        pollution_stagnation_index = _clip01(stagnation)
        stagnation_basis = (
            "0.40*(1-wind_norm) + 0.40*(1-pbl_norm) + 0.20*inversion_strength, "
            f"wind_norm={wind_norm}, pbl_norm={pbl_norm}, inversion_strength={inv}"
        )
    else:
        pollution_stagnation_index = None
        stagnation_basis = "requires wind_speed, pbl_height or inversion_strength"

    # ---- 5. aerosol_accumulation_potential -----------------------------------
    pm25_norm = None
    if pm25 is not None:
        pm25_norm = _clip01((pm25 - PM25_REF_GOOD) / (PM25_REF_SEVERE - PM25_REF_GOOD))
    if pm25_norm is not None and accumulation_potential is not None:
        aerosol_accumulation_potential = _clip01(0.5 * pm25_norm + 0.5 * accumulation_potential)
        aero_basis = (
            "0.50*pm25_observed_norm + 0.50*accumulation_potential, "
            f"pm25={pm25}, pm25_norm={pm25_norm}"
        )
    else:
        aerosol_accumulation_potential = None
        aero_basis = (
            "requires observed pm25 and accumulation_potential "
            "(observed loading is never overwritten by an artificial formula)"
        )

    # ---- 6. fire_transport_influence -----------------------------------------
    if inputs.fire_count is not None or inputs.fire_impact_score is not None or inputs.nearest_fire_distance_km is not None:
        count_term = _clip01((inputs.upwind_fire_count or 0) / UPWIND_COUNT_SATURATION)
        proximity = None
        if inputs.nearest_fire_distance_km is not None:
            proximity = _clip01(1.0 - min(1.0, inputs.nearest_fire_distance_km / FIRE_DIST_REF_KM))
        alignment = _clip01((inputs.wind_alignment_pct or 0.0) / 100.0)
        impact = inputs.fire_impact_score
        if impact is None:
            impact = 0.0
        fire_transport_influence = _clip01(
            0.5 * impact + 0.25 * (proximity or 0.0) + 0.15 * count_term + 0.10 * alignment
        )
        fire_inf_basis = (
            "0.50*fire_impact_score + 0.25*proximity + 0.15*upwind_count_sat + 0.10*wind_alignment, "
            f"impact={impact}, proximity={proximity}, count_term={count_term}, alignment={alignment}"
        )
    else:
        fire_transport_influence = None
        fire_inf_basis = "requires fire_count / fire_impact_score / nearest_fire_distance"

    # ---- 7. regional_transport_potential --------------------------------------
    if fire_transport_influence is not None or wind_norm is not None or vent_norm is not None:
        vent_term = _clip01(1.0 - (vent_norm or 0.0)) if vent_norm is not None else None
        regional_transport_potential = _clip01(
            0.6 * (fire_transport_influence or 0.0)
            + 0.25 * (vent_term if vent_term is not None else 0.5)
            + 0.15 * (1.0 - (wind_norm or 0.0))
        )
        region_basis = (
            "0.60*fire_transport_influence + 0.25*(1-ventilation_norm) + 0.15*(1-wind_norm), "
            f"fire_influence={fire_transport_influence}, vent_term={vent_term}, wind_norm={wind_norm}"
        )
    else:
        regional_transport_potential = None
        region_basis = "requires fire influence or wind/ventilation data"

    # ---- 8. ozone_photochemical_potential --------------------------------------
    temp_norm = None
    if temp is not None:
        temp_norm = _clip01((temp - TEMP_WARM_C) / (TEMP_HOT_C - TEMP_WARM_C))
    no2_norm = _norm(inputs.no2_ugm3, NO2_REF)
    if temp_norm is not None or no2_norm is not None or wind_norm is not None:
        ozone_photochemical_potential = _clip01(
            0.5 * (temp_norm if temp_norm is not None else 0.0)
            + 0.3 * (1.0 - (wind_norm or 0.0))
            + 0.2 * (no2_norm or 0.0)
        )
        o3_basis = (
            "0.50*temperature_norm + 0.30*(1-wind_norm) + 0.20*no2_precursor_norm — "
            "photochemical *potential* (warmth + stagnation + precursors), not a "
            "measured ozone formation rate; "
            f"temp_norm={temp_norm}, wind_norm={wind_norm}, no2_norm={no2_norm}"
        )
    else:
        ozone_photochemical_potential = None
        o3_basis = "requires temperature, wind or no2"

    # ---- 9. meteorology_pollution_interaction -----------------------------------
    present = [
        v
        for v in (
            accumulation_potential,
            pollution_stagnation_index,
            ozone_photochemical_potential,
            fire_transport_influence,
        )
        if v is not None
    ]
    if present:
        meteorology_pollution_interaction = _clip01(float(sum(present)) / len(present))
        mpi_basis = (
            "mean(accumulation_potential, pollution_stagnation_index, "
            "ozone_photochemical_potential, fire_transport_influence) — a "
            "data-driven pollution-meteorology feedback SURROGATE, not a physical "
            "aerosol-radiation-chemistry simulation"
        )
    else:
        meteorology_pollution_interaction = None
        mpi_basis = "requires at least one atmospheric/pollution coupling feature"

    features = {
        "dispersion_potential": _feature(dispersion_potential, disp_basis),
        "accumulation_potential": _feature(accumulation_potential, accum_basis),
        "inversion_trapping_potential": _feature(inversion_trapping_potential, trap_basis),
        "pollution_stagnation_index": _feature(pollution_stagnation_index, stagnation_basis),
        "aerosol_accumulation_potential": _feature(aerosol_accumulation_potential, aero_basis),
        "fire_transport_influence": _feature(fire_transport_influence, fire_inf_basis),
        "regional_transport_potential": _feature(regional_transport_potential, region_basis),
        "ozone_photochemical_potential": _feature(ozone_photochemical_potential, o3_basis),
        "meteorology_pollution_interaction": _feature(meteorology_pollution_interaction, mpi_basis),
    }

    return {
        "features": features,
        "inputs": {
            "temperature_c": inputs.temperature_c,
            "humidity_pct": inputs.humidity_pct,
            "pressure_hpa": inputs.pressure_hpa,
            "wind_speed_mps": inputs.wind_speed_mps,
            "wind_direction_deg": inputs.wind_direction_deg,
            "pbl_height_m": inputs.pbl_height_m,
            "pm25_ugm3": inputs.pm25_ugm3,
            "pm10_ugm3": inputs.pm10_ugm3,
            "no2_ugm3": inputs.no2_ugm3,
            "o3_ugm3": inputs.o3_ugm3,
            "inversion_detected": inv_detected,
            "inversion_strength": inputs.inversion_strength,
            "inversion_category": inputs.inversion_category,
            "fire_count": inputs.fire_count,
            "upwind_fire_count": inputs.upwind_fire_count,
            "nearest_fire_distance_km": inputs.nearest_fire_distance_km,
            "fire_impact_score": inputs.fire_impact_score,
            "wind_alignment_pct": inputs.wind_alignment_pct,
            "transport_time_hours": inputs.transport_time_hours,
        },
        "methodology": {
            "note": (
                "Features are computed from stored observations (CPCB pollution, "
                "Open-Meteo weather/vertical profile, NASA FIRMS fires). They are "
                "documented *potentials/tendencies*, not measurements. The "
                "meteorology-pollution coupling is a data-driven surrogate — no "
                "claim is made of a physics-based chemistry feedback loop."
            ),
            "constants": {
                "wind_ref_mps": WIND_REF_MPS,
                "pbl_ref_m": PBL_REF_M,
                "pm25_ref_good_ugm3": PM25_REF_GOOD,
                "pm25_ref_severe_ugm3": PM25_REF_SEVERE,
                "no2_ref_ugm3": NO2_REF,
                "temp_warm_c": TEMP_WARM_C,
                "temp_hot_c": TEMP_HOT_C,
                "vent_ref_m2s": VENT_REF,
                "upwind_count_saturation": UPWIND_COUNT_SATURATION,
                "fire_dist_ref_km": FIRE_DIST_REF_KM,
                "transport_time_ref_h": TRANSPORT_TIME_REF_H,
            },
        },
    }


def _feature(value, basis: str) -> dict[str, Any]:
    return {
        "value": value,
        "available": value is not None,
        "basis": basis,
    }


def band_label(value) -> str | None:
    """Map a feature value (0..1) to a Low / Moderate / High label."""
    return _band(value, 0.33, 0.66)
