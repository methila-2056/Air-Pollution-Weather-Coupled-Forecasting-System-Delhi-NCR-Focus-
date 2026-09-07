"""Online time-stepped two-way weather-chemistry coupled forecast loop.

This is the lightweight surrogate for a full WRF-Chem online coupling. Instead
of treating meteorology as fixed external input, pollutants and meteorology are
advanced *together* hour by hour:

  for each hour step:
      1. predict next-hour pollutant concentrations from current features
         (meteorology -> chemistry forward path)
      2. derive the aerosol radiative forcing from the freshly forecast PM2.5
         (AOD, radiation attenuation, PBL suppression, boundary-layer stability)
      3. correct the meteorological fields (PBL height, temperature, inversion
         strength, stability coupling index)
      4. advance the pollution lags and re-enter the loop with the corrected
         meteorology (chemistry -> meteorology feedback path)

The result is a true sequential two-way coupling simulation, not a one-pass
statistical forecast.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Callable, Optional

import numpy as np

from .coupling import (
    estimate_aod,
    surface_radiation_attenuation,
    pbl_suppression_factor,
    surface_temperature_damping,
    boundary_stability_index,
    corrected_pbl_height,
    coupling_feedback_score,
)

# Predictor signature: predict(features: dict, horizon_hours: int) -> dict
# returning at minimum {"pm25_pred", "pm10_pred", "o3_pred", "no2_pred"} and
# optionally "so2_pred", "co_pred", "aqi_pred".


def _next_prediction(predict_func: Callable, features: dict) -> dict:
    """Get a single-hour-ahead prediction using the 1h forecasters."""
    return predict_func(features, horizon_hours=1)


def _apply_coupling_forcing(features: dict, pred: dict, hour: int) -> dict:
    """Advance + correct the feature vector using aerosol feedback physics."""
    f = deepcopy(features)

    pm25 = float(pred.get("pm25_pred") or pred.get("pm25") or f.get("pm25_lag1") or 0.0)
    pbl = float(f.get("pbl_height") or 600.0)
    wind = float(f.get("wind_speed") or 4.0)

    # chemistry -> meteorology: aerosol suppresses PBL, damps diurnal temp
    supp = pbl_suppression_factor(pm25, hour)
    corrected_pbl = corrected_pbl_height(pm25, pbl, hour)
    damping = surface_temperature_damping(pm25, hour)

    base_temp = float(f.get("temperature") or 20.0)
    # diurnal swing estimate: pull predicted temp toward the aerosol-damped value
    diurnal_swing = abs(base_temp - 13.0)  # rough baseline mid value
    damped_temp = 13.0 + (base_temp - 13.0) * damping

    stability = boundary_stability_index(pm25, pbl, wind, hour)
    aod = estimate_aod(pm25)
    transmittance = surface_radiation_attenuation(pm25)

    # update meteorological feature fields for the next step
    f["pbl_height"] = corrected_pbl
    f["corrected_pbl_height"] = corrected_pbl
    f["pbl_suppression_factor"] = supp
    f["aod_est"] = aod
    f["radiation_transmittance"] = transmittance
    f["temperature"] = damped_temp
    f["temperature_lag1"] = base_temp
    f["temperature_lag6"] = base_temp if "temperature_lag6" in f else f.get("temperature_lag6")
    f["inversion_strength"] = float(np.clip((500.0 - corrected_pbl) / 500.0, 0.0, 1.0))
    f["inversion_detected"] = int(corrected_pbl < 500)
    f["stability_coupling_index"] = stability
    f["feedback_multiplier"] = 1.0 + stability * 0.4

    # advance pollution lags: shift current predictions into lag-1 slots
    for slug in ("pm25", "pm10", "o3", "no2", "so2", "co"):
        pred_key = f"{slug}_pred"
        lag_key = f"{slug}_lag1"
        if pred_key in pred and pred.get(pred_key) is not None:
            f[lag_key] = float(pred[pred_key])
            f[slug] = float(pred[pred_key])
            for extra in (3, 6, 12):
                key = f"{slug}_lag{extra}"
                if key in f:
                    f[key] = f[key]  # keep historical; simple persistence
    # rolling means approximate with new lag1 value
    for slug in ("pm25", "pm10", "o3", "no2"):
        lag_key = f"{slug}_lag1"
        if lag_key in f:
            for w in (3, 6, 12, 24):
                key = f"{slug}_roll_mean_{w}h"
                if key in f:
                    f[key] = (float(f[key]) * (w - 1) + float(f[lag_key])) / w

    return f


def run_coupled_forecast(
    predict_func: Callable,
    features: dict,
    horizons: Optional[list] = None,
    start_hour: int = 12,
) -> dict:
    """Run the sequential two-way coupling forecast.

    Args:
        predict_func: callable(features, horizon_hours) -> dict of predictions.
            For the coupling loop it is invoked with horizon=1 at every step so
            the meteorology can be corrected in-between.
        features: starting feature vector (observed conditions).
        horizons: forecast horizons requested (hours after t0).
        start_hour: hour of day at t0 for the diurnal coupling factor.

    Returns:
        {
          "coupled": [ {horizon, predictions..., coupling: {...}} ... ],
          "uncoupled": [ dict of direct per-horizon predictions ],
          "feedback_path": [list of hourly (hour_index, pbl, pm25, stability)],
        }
    """
    horizons = sorted(horizons or [1, 6, 12, 24, 48, 72])
    hour = int(start_hour or 12) % 24

    coupled = []
    feedback_path = []
    state = deepcopy(features)
    running = {}   # last predicted concentrations

    # step continuously to the farthest horizon, record at requested horizons
    for h in range(1, max(horizons) + 1):
        pred = _next_prediction(predict_func, state)
        running = pred

        state = _apply_coupling_forcing(state, pred, hour)
        hour = (hour + 1) % 24

        diag = coupling_feedback_score(
            float(pred.get("pm25_pred") or 0.0),
            float(state.get("pbl_height") or 600.0),
            float(state.get("wind_speed") or 4.0),
            hour,
        )
        feedback_path.append({
            "t_plus": int(h),
            "pm25": round(float(pred.get("pm25_pred") or 0.0), 1),
            "pbl_effective": round(diag["corrected_pbl_height"], 1),
            "stability": round(diag["stability_coupling_index"], 4),
            "feedback_multiplier": round(diag["feedback_multiplier"], 4),
        })

        if h in horizons:
            coupled.append({
                "horizon_hours": h,
                "pm25_pred": float(pred.get("pm25_pred")),
                "pm10_pred": float(pred.get("pm10_pred")),
                "o3_pred": float(pred.get("o3_pred")),
                "no2_pred": float(pred.get("no2_pred")),
                "so2_pred": float(pred.get("so2_pred")) if pred.get("so2_pred") is not None else None,
                "co_pred": float(pred.get("co_pred")) if pred.get("co_pred") is not None else None,
                "aqi_pred": pred.get("aqi_pred"),
                "aqi_category": pred.get("aqi_category"),
                "dominant_pollutant": pred.get("dominant_pollutant"),
                "coupling": diag,
            })

    # direct (uncoupled) per-horizon predictions for skill comparison
    uncoupled = []
    for h in horizons:
        pred = predict_func(deepcopy(features), horizon_hours=h)
        uncoupled.append({
            "horizon_hours": h,
            "pm25_pred": float(pred.get("pm25_pred")),
            "pm10_pred": float(pred.get("pm10_pred")),
            "o3_pred": float(pred.get("o3_pred")),
            "no2_pred": float(pred.get("no2_pred")),
            "so2_pred": float(pred.get("so2_pred")) if pred.get("so2_pred") is not None else None,
            "co_pred": float(pred.get("co_pred")) if pred.get("co_pred") is not None else None,
            "aqi_pred": pred.get("aqi_pred"),
            "aqi_category": pred.get("aqi_category"),
            "dominant_pollutant": pred.get("dominant_pollutant"),
        })

    return {"coupled": coupled, "uncoupled": uncoupled, "feedback_path": feedback_path}