"""Two-way weather-chemistry coupling feedback module.

Implements the aerosol-radiation-boundary-layer feedback that is the core
of the SIH26082 problem statement: dense aerosol loading (PM2.5) attenuates
incoming solar radiation, cooling the surface and suppressing planetary
boundary layer (PBL) development. A suppressed PBL, in turn, reduces vertical
mixing and traps pollutants near the ground — a positive feedback loop.

This module encodes that physical mechanism as a set of analytic, physics-
informed coupling corrections:

  * Forward path (meteorology -> chemistry):
      PBL height, temperature, wind, humidity and inversion strength drive
      pollutant dispersion / accumulation (already modelled by the ML
      forecasters).

  * Missing backward path (chemistry -> meteorology):
      Aerosol loading reduces shortwave radiation reaching the surface
      (aerosol direct radiative effect), which:
        - suppresses daytime PBL growth  (lower PBL -> stronger inversion)
        - reduces diurnal temperature amplitude (cooler daytime)
        - stabilises the boundary layer   (higher stability index)

The module exposes these corrected meteorological fields and a set of coupling
features so the same physics can be applied consistently at training time and
in live inference.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# OPTICAL_PARAMS
# Aerosol optical depth (AOD) estimated from surface PM2.5 column loading.
PM25_TO_AOD = 0.00025          # AOD per ug/m3 (coarse but reasonable approximation)
SURFACE_COLUMN_KM = 1.0        # assumed mixed column depth for conversion (km)
AOD_TO_PBL_SUPPRESSION = 0.35  # fractional PBL reduction per unit baseline AOD


def estimate_aod(pm25: float) -> float:
    """Estimate aerosol optical depth from surface PM2.5 concentration.

    Rough linear proxy: AOD ~ PM2.5 (ug/m3) * PM25_TO_AOD. Clamped to a
    physically plausible range [0, 2.5].
    """
    pm25 = max(0.0, float(pm25 or 0.0))
    return float(np.clip(pm25 * PM25_TO_AOD, 0.0, 2.5))


def surface_radiation_attenuation(pm25: float) -> float:
    """Fraction of solar radiation transmitted to the surface.

    Uses Beer-Lambert form  T = exp(-tau) with tau ~ AOD. Returns a value in
    (0, 1]; lower means more radiation blocked by aerosols.
    """
    aod = estimate_aod(pm25)
    return float(np.exp(-aod))


def pbl_suppression_factor(pm25: float, hour: int = 12) -> float:
    """Multiplier on PBL height due to aerosol radiative effect.

    Aerosol-induced PBL suppression is strongest during daytime, when solar
    heating normally drives convective growth that aerosols attenuate. At night
    (stable boundary layer) the effect is small. Returns a factor in [0.8, 1.0].
    """
    aod = estimate_aod(pm25)
    attenuation = surface_radiation_attenuation(pm25)
    daytime = _daytime_weight(hour)
    suppression = AOD_TO_PBL_SUPPRESSION * aod * attenuation * daytime
    return float(np.clip(1.0 - suppression, 0.8, 1.0))


def surface_temperature_damping(pm25: float, hour: int = 12) -> float:
    """Multiplier on the (temperature - nighttime baseline) diurnal signal.

    Aerosols reduce daytime solar heating, damping the diurnal temperature
    amplitude. Returns a value in [0.85, 1.0] applied to the diurnal swing.
    """
    attenuation = surface_radiation_attenuation(pm25)
    daytime = _daytime_weight(hour)
    damping = 1.0 - (1.0 - attenuation) * 0.4 * daytime
    return float(np.clip(damping, 0.85, 1.0))


def boundary_stability_index(pm25: float, pbl_height: float, wind_speed: float, hour: int) -> float:
    """Composite stability index in [0, 1] where 1 = highly stable / trapped.

    Combines the suppressed PBL (aerosol feedback) with existing inversion
    conditions and low wind. Higher values indicate strong trapping that
    favours pollutant accumulation.
    """
    base_pbl = float(pbl_height or 600.0)
    suppressed_pbl = base_pbl * pbl_suppression_factor(pm25, hour)
    pbl_term = np.clip(1.0 - suppressed_pbl / 600.0, 0.0, 1.0)

    wind = float(wind_speed or 4.0)
    wind_term = np.clip(1.0 - wind / 8.0, 0.0, 1.0)

    daytime = _daytime_weight(hour)
    stability = 0.5 * pbl_term + 0.3 * wind_term + 0.2 * (1.0 - daytime)
    return float(np.clip(stability, 0.0, 1.0))


def corrected_pbl_height(pm25: float, pbl_height: float, hour: int) -> float:
    """Return the aerosol-suppressed effective PBL height (m)."""
    base = float(pbl_height or 600.0)
    return base * pbl_suppression_factor(pm25, hour)


def _daytime_weight(hour: int) -> float:
    """Weight favouring daytime when solar-driven mixing dominates (0-1)."""
    hour = int(hour or 12) % 24
    if 7 <= hour <= 18:
        # cosine peak near solar noon (13h)
        return float(np.clip(np.cos(2 * np.pi * (hour - 13) / (2 * 11)), 0.0, 1.0))
    return 0.0


def coupling_feedback_score(pm25: float, pbl_height: float, wind_speed: float, hour: int) -> dict:
    """Compute the full set of two-way coupling diagnostics.

    Returns a dict describing both the chemistry->meteorology forcing and the
    resulting meteorology->chemistry trapping feedback.
    """
    aod = estimate_aod(pm25)
    attenuation = surface_radiation_attenuation(pm25)
    suppressed_pbl = corrected_pbl_height(pm25, pbl_height, hour)
    stability = boundary_stability_index(pm25, pbl_height, wind_speed, hour)
    pbl_supp = pbl_suppression_factor(pm25, hour)

    # Feedback multiplier: stronger stability -> stronger pollutant retention
    feedback_multiplier = 1.0 + stability * 0.4

    return {
        "aod_est": round(aod, 4),
        "radiation_transmittance": round(attenuation, 4),
        "pbl_suppression_factor": round(pbl_supp, 4),
        "corrected_pbl_height": round(suppressed_pbl, 1),
        "stability_coupling_index": round(stability, 4),
        "feedback_multiplier": round(feedback_multiplier, 4),
        "coupling_strength": "strong" if stability >= 0.6 else ("moderate" if stability >= 0.35 else "weak"),
    }


# ---------------------------------------------------------------- DataFrame pipe

_COUPLING_FEATURES = [
    "aod_est",
    "radiation_transmittance",
    "pbl_suppression_factor",
    "corrected_pbl_height",
    "stability_coupling_index",
    "feedback_multiplier",
]


def add_coupling_features(df: pd.DataFrame, pm25_col: str = "pm25") -> pd.DataFrame:
    """Add two-way coupling diagnostic features to a dataframe.

    These features encode the aerosol chemistry -> meteorology feedback so that
    downstream ML forecasters can learn the coupled dynamics.

    Adds:
      - aod_est : estimated aerosol optical depth
      - radiation_transmittance : fraction of solar radiation reaching surface
      - pbl_suppression_factor : multiplier on PBL height from aerosol forcing
      - corrected_pbl_height : aerosol-suppressed effective PBL height (m)
      - stability_coupling_index : composite trapping/stability metric (0-1)
      - feedback_multiplier : pollutant retention feedback (>1 = more trapped)
    """
    df = df.copy()
    if pm25_col not in df.columns:
        for c in _COUPLING_FEATURES:
            df[c] = 0.0
        return df

    hour_col = "hour" if "hour" in df.columns else 12
    pbl_col = "pbl_height" in df.columns
    wind_col = "wind_speed" in df.columns

    pm25 = df[pm25_col].fillna(0.0)

    aod = (pm25 * PM25_TO_AOD).clip(0.0, 2.5)
    transmittance = np.exp(-aod)

    df["aod_est"] = aod.values
    df["radiation_transmittance"] = transmittance.values

    hours = df[hour_col].values if isinstance(hour_col, str) else np.full(len(df), hour_col)
    daytime = np.array([_daytime_weight(int(h)) for h in hours])
    pbl_supp = np.clip(1.0 - AOD_TO_PBL_SUPPRESSION * aod.values * transmittance.values * daytime, 0.8, 1.0)
    df["pbl_suppression_factor"] = pbl_supp

    base_pbl = df["pbl_height"].fillna(600.0).values if pbl_col else np.full(len(df), 600.0)
    df["corrected_pbl_height"] = base_pbl * pbl_supp

    wind = df["wind_speed"].fillna(4.0).values if wind_col else np.full(len(df), 4.0)
    pbl_term = np.clip(1.0 - (base_pbl * pbl_supp) / 600.0, 0.0, 1.0)
    wind_term = np.clip(1.0 - wind / 8.0, 0.0, 1.0)
    stability = np.clip(0.5 * pbl_term + 0.3 * wind_term + 0.2 * (1.0 - daytime), 0.0, 1.0)
    df["stability_coupling_index"] = stability
    df["feedback_multiplier"] = 1.0 + stability * 0.4

    return df
