"""Pollution-event detection engine for AeroCast-NCR.

Detects three event classes from the *trained* PM2.5 forecast series plus the
currently stored atmospheric conditions. No live network calls and no invented
numbers: every event is driven by the deployed XGBoost predictions and by
observations already in the database, and every threshold is declared below
(and echoed by the API in ``methodology.threshold_documentation``).

Detected event types
--------------------
``pollution_surge``     Forecast PM2.5 rises >= ``SURGE_MIN_RELATIVE_INCREASE_PCT``
                        (30%) above the observed 24h baseline AND reaches the
                        24h National Ambient Air Quality Standard (60 µg/m3).
``pollution_relief``    Forecast PM2.5 drops >= ``RELIEF_MIN_RELATIVE_DECREASE_PCT``
                        (25%) below the observed 24h baseline AND the current
                        atmosphere favours dispersion (good ventilation, a deep
                        PBL with at least light wind, or the drop is a >=45%
                        washout).
``high_risk_episode``   Forecast PM2.5 stays in the CPCB "Very Poor" PM2.5 tier
                        (>= ``PM25_VERY_POOR_MIN_UGM3`` = 121 µg/m3) for >=
                        ``EPISODE_SUSTAINED_HOURS`` (24) consecutive forecast
                        hours, AND at least one atmospheric risk contributor is
                        currently active (poor ventilation / shallow PBL /
                        temperature inversion / stagnant wind / elevated
                        regional transport risk).

Threshold provenance
--------------------
* 60 µg/m3  — India's National Ambient Air Quality Standards (NAAQS) 24h limit
              for PM2.5 (notified under the Environment (Protection) Act).
* 121 µg/m3 — CPCB Air Quality Index sub-index breakpoint: PM2.5 enters the
              "Very Poor" band (121–250 µg/m3).
* 250 µg/m3 — CPCB AQI "Severe" band for PM2.5.
* 30%/25%/45% relative-change figures are operational conventions defined in
  ``docs/events.md`` (they filter ordinary diurnal variability while flagging
  meaningful forecast changes) — not government limits, and labelled as such.
* Atmospheric risk thresholds reuse the documented bands of
  ``atmosphere_service`` (ventilation < 3000 m2/s poor; PBL < 300 m shallow;
  wind < 2 m/s light; inversion via lapse-rate or labelled PBL proxy).
  Regional transport risk uses the documented ``transport_risk_service`` bands
  (>= HIGH means elevated).

Confidence / uncertainty
------------------------
Every event carries a ``confidence`` object built from the model's own
split-conformal prediction interval at the event's trigger point: the larger
the margin between the predicted value and the trigger threshold relative to
the conformal half-width, the higher the confidence label (high/medium/low).
The interval bounds, the peak-horizon held-out R2, the coverage target and the
uncertainty method are attached so the number is never free-floating.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

logger = logging.getLogger("aerocast.pollution_events")

METHODOLOGY_VERSION = "1.0.0"

EVENT_TYPES = ("pollution_surge", "pollution_relief", "high_risk_episode")

# ---------------------------------------------------------------------------
# Documented concentration thresholds (µg/m3) — from national standards.
# ---------------------------------------------------------------------------
NAAQS_PM25_24H_UGM3 = 60.0  # India NAAQS 24h PM2.5 limit
PM25_VERY_POOR_MIN_UGM3 = 121.0  # CPCB AQI PM2.5 "Very Poor" band lower bound
PM25_SEVERE_MIN_UGM3 = 250.0  # CPCB AQI PM2.5 "Severe" band lower bound

# ---------------------------------------------------------------------------
# Operational relative-change conventions (documented in docs/events.md).
# ---------------------------------------------------------------------------
SURGE_MIN_RELATIVE_INCREASE_PCT = 30.0
RELIEF_MIN_RELATIVE_DECREASE_PCT = 25.0
RELIEF_WASHOUT_DECREASE_PCT = 45.0
EPISODE_SUSTAINED_HOURS = 24

# ---------------------------------------------------------------------------
# Atmospheric risk-factor thresholds (reuse atmosphere_service bands).
# ---------------------------------------------------------------------------
# Ventilation coefficient bands (m2/s) mirror atmosphere_service: poor < 3000.
VENT_POOR_M2S = 3000.0
# PBL height below which near-ground trapping is at least "moderate" (m).
PBL_SHALLOW_M = 300.0
# Wind speed below which ventilation is at most "light" (m/s).
WIND_LIGHT_MPS = 2.0
# Regional transport risk bands counted as "elevated" (transport_risk_service).
TRANSPORT_RISK_HIGH_BANDS = {"HIGH", "VERY HIGH"}

SEVERITIES_CARDINAL = {"mild", "moderate", "severe", "minor", "significant", "high", "emergency"}


def _float(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _round(v, nd: int) -> float | None:
    f = _float(v)
    return round(f, nd) if f is not None else None


def _contiguous_activating_runs(series: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> list[list[dict[str, Any]]]:
    """Split ``series`` into contiguous runs of points that satisfy ``predicate``.

    Forecast points are hourly; points more than ~1 hour apart break a run. This
    keeps "sustained/contiguous" semantics honest when only sparse horizons are
    served (e.g. 1/6/12/24…).
    """
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    for p in series:
        if predicate(p):
            gap = float("inf")
            if current and prev is not None:
                gap = abs((p["timestamp"] - prev["timestamp"]).total_seconds()) / 3600.0
            if current and gap > 1.0:
                runs.append(current)
                current = []
            current.append(p)
        else:
            if current:
                runs.append(current)
                current = []
        prev = p
    if current:
        runs.append(current)
    return runs


def _max_point(run: list[dict[str, Any]]) -> tuple[dict[str, Any], float]:
    best = max(run, key=lambda p: _float(p.get("predicted_pm25")) or 0.0)
    return best, _float(best.get("predicted_pm25"))


def _min_point(run: list[dict[str, Any]]) -> tuple[dict[str, Any], float]:
    best = min(run, key=lambda p: _float(p.get("predicted_pm25")) or 1e18)
    return best, _float(best.get("predicted_pm25"))


def _surge_severity(peak: float) -> tuple[str, str]:
    if peak >= PM25_SEVERE_MIN_UGM3:
        return "severe", f"Severe surge — expected peak {peak:.0f} µg/m3 lies in the CPCB 'Severe' PM2.5 tier (>=250 µg/m3)"
    if peak >= PM25_VERY_POOR_MIN_UGM3:
        return "moderate", f"Moderate surge — expected peak {peak:.0f} µg/m3 lies in the CPCB 'Very Poor' tier (121–250 µg/m3)"
    return "mild", f"Mild surge — expected peak {peak:.0f} µg/m3 exceeds the 24h NAAQS limit (60 µg/m3) but stays below the 'Very Poor' tier"


def _relief_severity(drop_pct: float, trough: float) -> tuple[str, str]:
    if drop_pct >= RELIEF_WASHOUT_DECREASE_PCT or trough < NAAQS_PM25_24H_UGM3:
        return "significant", f"Significant relief — forecast minimum {trough:.0f} µg/m3 is {drop_pct:.0f}% below baseline and reaches within the 24h NAAQS limit (60 µg/m3)"
    return "minor", f"Minor relief — forecast minimum {trough:.0f} µg/m3 is {drop_pct:.0f}% below baseline (>=25%) but stays above the 24h NAAQS limit"


def _episode_severity(peak: float, n_active_factors: int) -> tuple[str, str]:
    if peak >= PM25_SEVERE_MIN_UGM3 or n_active_factors >= 2:
        return "emergency", f"Emergency episode — sustained 'Very Poor' tier with forecast peak {peak:.0f} µg/m3 and {n_active_factors} active atmospheric risk contributor(s)"
    return "high", f"High-risk episode — 'Very Poor' tier sustained for >=24h with {n_active_factors} active atmospheric risk contributor(s)"


def _uncertainty_confidence(
    trigger_point: dict[str, Any],
    margin: float,
    *,
    test_r2: float | None,
    coverage_target: float | None,
    uncertainty_method: str | None,
) -> dict[str, Any]:
    lo = _float(trigger_point.get("pm25_lower_bound"))
    hi = _float(trigger_point.get("pm25_upper_bound"))
    half = None if (lo is None or hi is None) else (hi - lo) / 2.0
    if margin is None:
        label, basis = "unknown", "No margin computable (trigger threshold or value missing)."
    elif half is None:
        label, basis = "medium", "No conformal interval for this forecast horizon; uncertainty is unquantified."
    elif margin >= half:
        label = "high"
        basis = (
            f"Predicted value clears the trigger threshold by {margin:.1f} µg/m3, "
            f"which is >= the conformal half-width {half:.1f} µg/m3 — the event is robust to model uncertainty."
        )
    elif margin >= 0.5 * half:
        label = "medium"
        basis = (
            f"Predicted value clears the trigger threshold by {margin:.1f} µg/m3 but the "
            f"conformal half-width is {half:.1f} µg/m3 — the event is plausible but not robust within the model interval."
        )
    else:
        label = "low"
        basis = (
            f"Predicted value clears the trigger threshold by only {margin:.1f} µg/m3 vs a conformal "
            f"half-width of {half:.1f} µg/m3 — the event sits inside the model's prediction interval."
        )
    return {
        "label": label,
        "basis": basis,
        "margin_ugm3": _round(margin, 2),
        "conformal_half_width_ugm3": _round(half, 2),
        "lower_bound_ugm3": lo,
        "upper_bound_ugm3": hi,
        "test_r2": _float(test_r2),
        "coverage_target": _float(coverage_target),
        "uncertainty_method": uncertainty_method,
    }


def _event_status(start_time, end_time, now) -> str:
    if start_time is None:
        return "forecast"
    if now is None:
        return "forecast"
    if now >= start_time and (end_time is None or now <= end_time):
        return "active"
    return "forecast"


def _risk_factors(
    atmosphere: dict[str, Any],
    transport_risk_level: str | None,
    transport_risk_score: int | None,
) -> list[dict[str, Any]]:
    """Active pollution-trapping contributors, values from stored observations."""
    wind = atmosphere.get("wind") or {}
    pbl = atmosphere.get("pbl") or {}
    vent = atmosphere.get("ventilation") or {}
    inv = atmosphere.get("inversion") or {}
    ws = _float(wind.get("wind_speed_mps"))
    pbl_m = _float(pbl.get("pbl_height_m"))
    vc = _float(vent.get("ventilation_coefficient_m2s"))

    out: list[dict[str, Any]] = []
    if vc is not None:
        active = vc < VENT_POOR_M2S
        out.append({
            "factor": "low_ventilation",
            "status": "active" if active else "not_contributing",
            "value": vc,
            "evidence": f"ventilation_coefficient = wind {ws} m/s x PBL {pbl_m} m = {vc} m2/s",
            "description": "Weak horizontal+vertical mixing limits pollutant dispersal (poor band <3000 m2/s).",
        })
    if pbl_m is not None:
        active = pbl_m < PBL_SHALLOW_M
        out.append({
            "factor": "shallow_pbl",
            "status": "active" if active else "not_contributing",
            "value": pbl_m,
            "evidence": f"stored pbl_height = {pbl_m} m",
            "description": "A shallow boundary layer (<300 m) confines pollution near the surface.",
        })
    out.append({
        "factor": "inversion",
        "status": "active" if bool(inv.get("detected")) else "not_contributing",
        "value": _float(inv.get("strength")),
        "evidence": (
            f"inversion source={inv.get('source')}, category={inv.get('category')}, strength={_float(inv.get('strength'))}"
            if inv else "no stored vertical temperature profile for inversion detection"
        ),
        "description": "A temperature inversion caps vertical mixing and traps pollutants.",
    })
    if ws is not None:
        active = ws < WIND_LIGHT_MPS
        out.append({
            "factor": "stagnant_wind",
            "status": "active" if active else "not_contributing",
            "value": ws,
            "evidence": f"stored wind_speed = {ws} m/s",
            "description": "Light/calm wind (<2 m/s) slows horizontal ventilation.",
        })
    if transport_risk_level is not None:
        active = transport_risk_level in TRANSPORT_RISK_HIGH_BANDS
        out.append({
            "factor": "regional_transport",
            "status": "active" if active else "not_contributing",
            "value": transport_risk_score,
            "evidence": f"Estimated Regional Pollution Transport Risk level = {transport_risk_level}",
            "description": "Upwind fire plumes can compound local accumulation (elevated at HIGH/VERY HIGH).",
        })
    return out


def _dispersion_factors(atmosphere: dict[str, Any]) -> list[dict[str, Any]]:
    """Dispersion-favouring contributors present in the stored atmosphere."""
    wind = atmosphere.get("wind") or {}
    pbl = atmosphere.get("pbl") or {}
    vent = atmosphere.get("ventilation") or {}
    ws = _float(wind.get("wind_speed_mps"))
    pbl_m = _float(pbl.get("pbl_height_m"))
    vc = _float(vent.get("ventilation_coefficient_m2s"))

    out: list[dict[str, Any]] = []
    if vc is not None:
        good = vc >= 2.0 * VENT_POOR_M2S  # >=6000 m2/s (documented VENT_MODERATE), reuse threshold spirit
        out.append({
            "factor": "ventilation",
            "status": "supporting" if good else ("partial" if vc >= VENT_POOR_M2S else "not_supporting"),
            "value": vc,
            "evidence": f"ventilation_coefficient = wind {ws} m/s x PBL {pbl_m} m = {vc} m2/s",
            "description": "Higher ventilation coefficients (>=6000 m2/s) indicate effective dispersal.",
        })
    if pbl_m is not None:
        deep = pbl_m >= PBL_SHALLOW_M
        out.append({
            "factor": "boundary_layer_depth",
            "status": "supporting" if deep else "not_supporting",
            "value": pbl_m,
            "evidence": f"stored pbl_height = {pbl_m} m",
            "description": "A deeper PBL (>300 m) leaves more room for vertical mixing.",
        })
    if ws is not None:
        out.append({
            "factor": "wind",
            "status": "supporting" if ws >= WIND_LIGHT_MPS else "not_supporting",
            "value": ws,
            "evidence": f"stored wind_speed = {ws} m/s",
            "description": "Winds >=2 m/s advect and dilute surface pollution.",
        })
    return out


def detect_events_from_series(
    series: list[dict[str, Any]],
    baseline_pm25: float | None,
    atmosphere: dict[str, Any],
    *,
    station_name: str | None = None,
    transport_risk_level: str | None = None,
    transport_risk_score: int | None = None,
    uncertainty_method: str | None = "split-conformal",
    coverage_target: float | None = None,
    test_metrics: dict[int, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Detect pollution events from a forecast series + current atmosphere.

    ``series`` is a list of ``{timestamp, forecast_horizon, predicted_pm25,
    pm25_lower_bound, pm25_upper_bound}`` maps (as produced by
    :func:`pm25_forecast_service.forecast_pm25`). Pure and deterministic — no
    database access — so the *rules* are unit-testable directly.
    """
    points = [p for p in series if _float(p.get("predicted_pm25")) is not None]
    points = sorted(points, key=lambda p: p["timestamp"])
    if not points:
        return []

    baseline = _float(baseline_pm25)
    test_metrics = test_metrics or {}
    now = now or datetime.now(UTC).replace(tzinfo=None)

    def _r2(point: dict[str, Any]) -> float | None:
        met = test_metrics.get(point.get("forecast_horizon")) or {}
        return _float(met.get("test_r2"))

    events: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ surge
    if baseline is not None and baseline > 0:
        rel_threshold = baseline * (1.0 + SURGE_MIN_RELATIVE_INCREASE_PCT / 100.0)
        surge_threshold = max(rel_threshold, NAAQS_PM25_24H_UGM3)
        runs = _contiguous_activating_runs(points, lambda p: (p.get("predicted_pm25") or 0.0) >= surge_threshold)
        if runs:
            run = max(runs, key=lambda r: _float(_max_point(r)[1]) or 0.0)
            peak_pt, peak = _max_point(run)
            margin = peak - surge_threshold
            increase_pct = (peak - baseline) / baseline * 100.0
            severity, sev_label = _surge_severity(peak)
            factors = _risk_factors(atmosphere, transport_risk_level, transport_risk_score)
            factors.insert(0, {
                "factor": "relative_increase",
                "status": "triggering",
                "value": round(increase_pct, 1),
                "evidence": (
                    f"observed 24h baseline {baseline} µg/m3 -> forecast peak {peak} µg/m3 "
                    f"(+{round(increase_pct, 1)}%)"
                ),
                "description": f"Forecast peak is >= {SURGE_MIN_RELATIVE_INCREASE_PCT:.0f}% above the observed baseline and reaches the 24h NAAQS limit.",
            })
            effective_end = run[-1]["timestamp"] if run[-1] is not points[-1] else None
            events.append({
                "event_type": "pollution_surge",
                "station": station_name,
                "status": _event_status(run[0]["timestamp"], effective_end, now),
                "start_time": run[0]["timestamp"],
                "end_time": effective_end,
                "expected_peak": round(peak, 2),
                "expected_peak_time": peak_pt["timestamp"],
                "expected_trough": None,
                "expected_trough_time": None,
                "severity": severity,
                "severity_label": sev_label,
                "confidence": _uncertainty_confidence(
                    peak_pt, margin,
                    test_r2=_r2(peak_pt), coverage_target=coverage_target,
                    uncertainty_method=uncertainty_method,
                ),
                "contributing_factors": factors,
            })

    # ----------------------------------------------------------------- relief
    if baseline is not None and baseline > 0:
        rel_threshold = baseline * (1.0 - RELIEF_MIN_RELATIVE_DECREASE_PCT / 100.0)
        runs = _contiguous_activating_runs(points, lambda p: (p.get("predicted_pm25") or 0.0) <= rel_threshold)
        if runs:
            run = max(runs, key=lambda r: -(_float(_min_point(r)[1]) or 0.0))
            trough_pt, trough = _min_point(run)
            drop_pct = (baseline - trough) / baseline * 100.0
            dispersive = _dispersion_supported(atmosphere, drop_pct)
            if dispersive:
                margin = rel_threshold - trough
                severity, sev_label = _relief_severity(drop_pct, trough)
                factors = _dispersion_factors(atmosphere)
                factors.insert(0, {
                    "factor": "relative_decrease",
                    "status": "triggering",
                    "value": round(drop_pct, 1),
                    "evidence": (
                        f"observed 24h baseline {baseline} µg/m3 -> forecast minimum {trough} µg/m3 "
                        f"({round(drop_pct, 1)}% lower)"
                    ),
                    "description": f"Forecast minimum is >= {RELIEF_MIN_RELATIVE_DECREASE_PCT:.0f}% below the observed baseline with a dispersion-supporting atmosphere.",
                })
                effective_end = run[-1]["timestamp"] if run[-1] is not points[-1] else None
                events.append({
                    "event_type": "pollution_relief",
                    "station": station_name,
                    "status": _event_status(run[0]["timestamp"], effective_end, now),
                    "start_time": run[0]["timestamp"],
                    "end_time": effective_end,
                    "expected_peak": None,
                    "expected_peak_time": None,
                    "expected_trough": round(trough, 2),
                    "expected_trough_time": trough_pt["timestamp"],
                    "severity": severity,
                    "severity_label": sev_label,
                    "confidence": _uncertainty_confidence(
                        trough_pt, margin,
                        test_r2=_r2(trough_pt), coverage_target=coverage_target,
                        uncertainty_method=uncertainty_method,
                    ),
                    "contributing_factors": factors,
                })

    # ------------------------------------------------------------ episode
    if len(points) >= EPISODE_SUSTAINED_HOURS:
        runs = _contiguous_activating_runs(
            points, lambda p: (p.get("predicted_pm25") or 0.0) >= PM25_VERY_POOR_MIN_UGM3
        )
        long_runs = [r for r in runs if len(r) >= EPISODE_SUSTAINED_HOURS]
        if long_runs:
            run = max(long_runs, key=lambda r: _float(_max_point(r)[1]) or 0.0)
            peak_pt, peak = _max_point(run)
            risk = _risk_factors(atmosphere, transport_risk_level, transport_risk_score)
            active = [f for f in risk if f["status"] == "active"]
            if active:
                margin = peak - PM25_VERY_POOR_MIN_UGM3
                severity, sev_label = _episode_severity(peak, len(active))
                effective_end = run[-1]["timestamp"] if run[-1] is not points[-1] else None
                events.append({
                    "event_type": "high_risk_episode",
                    "station": station_name,
                    "status": _event_status(run[0]["timestamp"], effective_end, now),
                    "start_time": run[0]["timestamp"],
                    "end_time": effective_end,
                    "expected_peak": round(peak, 2),
                    "expected_peak_time": peak_pt["timestamp"],
                    "expected_trough": None,
                    "expected_trough_time": None,
                    "severity": severity,
                    "severity_label": sev_label,
                    "confidence": _uncertainty_confidence(
                        peak_pt, margin,
                        test_r2=_r2(peak_pt), coverage_target=coverage_target,
                        uncertainty_method=uncertainty_method,
                    ),
                    "contributing_factors": active,
                })

    return events


def _dispersion_supported(atmosphere: dict[str, Any], drop_pct: float) -> bool:
    """Relief only counts when the current atmosphere supports dispersion (or
    the forecast drop is a >= ``RELIEF_WASHOUT_DECREASE_PCT`` washout)."""
    if drop_pct >= RELIEF_WASHOUT_DECREASE_PCT:
        return True
    wind = atmosphere.get("wind") or {}
    pbl = atmosphere.get("pbl") or {}
    vent = atmosphere.get("ventilation") or {}
    vc = _float(vent.get("ventilation_coefficient_m2s"))
    ws = _float(wind.get("wind_speed_mps"))
    pbl_m = _float(pbl.get("pbl_height_m"))
    if vc is not None and vc >= 2.0 * VENT_POOR_M2S:
        return True
    if pbl_m is not None and ws is not None and pbl_m >= PBL_SHALLOW_M and ws >= WIND_LIGHT_MPS:
        return True
    return False


def _parse_ts(v) -> datetime | None:
    """Normalise a forecast timestamp to a naive-UTC datetime.

    The PM2.5 forecaster serialises ``timestamp`` as an ISO-8601 string
    (e.g. ``2026-09-08T09:00:00Z``); the event rules require real datetimes
    for run-gap arithmetic and status comparisons. Accepts datetime objects,
    ISO strings with/without ``Z``, and returns ``None`` on unparsable input.
    """
    from datetime import datetime as _dt

    if v is None:
        return None
    if isinstance(v, _dt):
        return v.replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, str):
        try:
            dt = _dt.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt.replace(tzinfo=None)
    return None


def _to_series(forecasts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": _parse_ts(f["timestamp"]),
            "forecast_horizon": f["forecast_horizon"],
            "predicted_pm25": _float(f.get("predicted_pm25")),
            "pm25_lower_bound": _float(f.get("pm25_lower_bound")),
            "pm25_upper_bound": _float(f.get("pm25_upper_bound")),
        }
        for f in forecasts
    ]


def _observed_24h_mean(db, station_id: int, release: datetime) -> float | None:
    from ..models.db_models import PollutionReading

    rows = (
        db.query(PollutionReading)
        .filter(
            PollutionReading.station_id == station_id,
            PollutionReading.timestamp > release - timedelta(hours=24),
            PollutionReading.timestamp <= release,
        )
        .all()
    )
    vals = [_float(r.pm25) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return round(float(np.mean(vals)), 2)


def _methodology() -> dict[str, Any]:
    return {
        "version": METHODOLOGY_VERSION,
        "approach": (
            "Rule-based detection over the trained per-horizon PM2.5 forecast series, "
            "combined with deterministic indicators of the currently stored atmosphere "
            "(ventilation, PBL, inversion, wind, regional transport risk). No ML in the "
            "rule layer and no invented numbers: driving values come from the deployed "
            "XGBoost models and stored observations."
        ),
        "rules": {
            "pollution_surge": (
                f"Forecast peak PM2.5 rises >= {SURGE_MIN_RELATIVE_INCREASE_PCT:.0f}% above the observed "
                f"24h baseline AND reaches >= {NAAQS_PM25_24H_UGM3:.0f} µg/m3 (24h NAAQS)."
            ),
            "pollution_relief": (
                f"Forecast minimum PM2.5 drops >= {RELIEF_MIN_RELATIVE_DECREASE_PCT:.0f}% below the observed "
                f"24h baseline AND the current atmosphere favours dispersion "
                f"(ventilation >= 6000 m2/s, or deep PBL >= 300 m with wind >= 2 m/s, "
                f"or the drop is a >= {RELIEF_WASHOUT_DECREASE_PCT:.0f}% washout)."
            ),
            "high_risk_episode": (
                f"Forecast PM2.5 stays >= {PM25_VERY_POOR_MIN_UGM3:.0f} µg/m3 (CPCB 'Very Poor' tier) for "
                f"at least {EPISODE_SUSTAINED_HOURS} consecutive forecast hours AND at least one atmospheric "
                f"risk contributor is active (poor ventilation < 3000 m2/s, PBL < {PBL_SHALLOW_M:.0f} m, "
                f"temperature inversion, wind < {WIND_LIGHT_MPS:.0f} m/s, or regional transport risk >= HIGH)."
            ),
        },
        "threshold_documentation": {
            "standards": {
                "naaqs_pm25_24h_ugm3": NAAQS_PM25_24H_UGM3,
                "source": "India National Ambient Air Quality Standards — 24h PM2.5 limit (CPCB notification under the Environment (Protection) Act).",
                "cpcb_aqi_pm25_very_poor_min_ugm3": PM25_VERY_POOR_MIN_UGM3,
                "cpcb_aqi_pm25_severe_min_ugm3": PM25_SEVERE_MIN_UGM3,
                "source_cpcb_aqi": "CPCB AQI sub-index breakpoints for 24h PM2.5 (Good 0-30, Satisfactory 31-60, Moderate 61-90, Poor 91-120, Very Poor 121-250, Severe >250).",
            },
            "operational_conventions": {
                "surge_relative_increase_pct": SURGE_MIN_RELATIVE_INCREASE_PCT,
                "relief_relative_decrease_pct": RELIEF_MIN_RELATIVE_DECREASE_PCT,
                "relief_washout_decrease_pct": RELIEF_WASHOUT_DECREASE_PCT,
                "episode_sustained_hours": EPISODE_SUSTAINED_HOURS,
                "note": "Relative-change thresholds and the 24h 'sustained' definition are operational conventions defined in docs/events.md (they filter diurnal variability), NOT government limits.",
            },
            "atmospheric_bands": {
                "ventilation_poor_below_m2s": VENT_POOR_M2S,
                "ventilation_good_from_m2s": 6000.0,
                "pbl_shallow_below_m": PBL_SHALLOW_M,
                "wind_light_below_mps": WIND_LIGHT_MPS,
                "source": "Thresholds reuse the documented bands in services/atmosphere_service.py (Delhi/IITM ventilation classification).",
            },
            "transport_risk_bands": {
                "elevated_from": sorted(TRANSPORT_RISK_HIGH_BANDS),
                "source": "Reuses transport_risk_service documented 0-100 bands (HIGH 61-80, VERY HIGH 81-100).",
            },
        },
        "confidence": (
            "label is high/medium/low based on the margin between the predicted value at the "
            "event's trigger point and the trigger threshold versus the split-conformal "
            "half-width at that same forecast horizon; interval bounds, peak-horizon held-out "
            "R2, coverage target and method are attached."
        ),
    }


def detect_current_events(db, station_name: str, horizon_hours: int = 48) -> dict[str, Any]:
    """Detect current/upcoming pollution events for one station.

    Assembles the real PM2.5 forecast via :func:`pm25_forecast_service.forecast_pm25`,
    the observed 24h baseline, the current atmosphere via
    :func:`atmosphere_service.analyze_station` and the regional transport risk via
    :func:`transport_risk_service.get_current_transport_risk`, then runs the
    documented rules. Raises the same exception types as ``forecast_pm25``
    (ValueError / RuntimeError) for the API layer to translate.
    """
    from ..models.db_models import Station
    from .atmosphere_service import analyze_station
    from .pm25_forecast_service import forecast_pm25
    from .transport_risk_service import get_current_transport_risk

    station = db.query(Station).filter(Station.name == station_name).first()
    if not station:
        raise ValueError(f"station_not_found: {station_name}")

    payload = forecast_pm25(db, station_name, horizon_hours)
    release = payload["release_time"].replace(tzinfo=None)

    now = datetime.now(UTC).replace(tzinfo=None)
    baseline = _observed_24h_mean(db, station.id, release)

    atmosphere = analyze_station(db, station, now=now)
    risk = get_current_transport_risk(db, fire_window_hours=72)
    risk_level = risk.get("risk_level")
    risk_score = risk.get("risk_score")
    if not risk_level or str(risk_level) == "UNAVAILABLE":
        risk_level, risk_score = None, None

    test_metrics = {
        p["forecast_horizon"]: {k: p.get(k) for k in ("test_mae", "test_rmse", "test_r2", "test_n")}
        for p in payload["forecasts"]
    }
    series = _to_series(payload["forecasts"])

    events = detect_events_from_series(
        series,
        baseline,
        atmosphere,
        station_name=station_name,
        transport_risk_level=risk_level,
        transport_risk_score=risk_score,
        uncertainty_method=payload.get("uncertainty_method"),
        coverage_target=payload.get("coverage_target"),
        test_metrics=test_metrics,
        now=release,
    )

    peak = max(series, key=lambda p: p["predicted_pm25"] or 0.0).get("predicted_pm25")

    notes: list[str] = []
    if horizon_hours < EPISODE_SUSTAINED_HOURS:
        notes.append(
            f"horizon_hours {horizon_hours} < {EPISODE_SUSTAINED_HOURS}; "
            "high_risk_episode detection requires at least 24 forecast hours and was skipped."
        )
    if baseline is None:
        notes.append(
            "no observed PM2.5 in the trailing 24h window; relative surge/relief detection skipped "
            "(baseline unavailable)."
        )

    atmo_summary = {
        "wind_speed_mps": (atmosphere.get("wind") or {}).get("wind_speed_mps"),
        "pbl_height_m": (atmosphere.get("pbl") or {}).get("pbl_height_m"),
        "ventilation_coefficient_m2s": (atmosphere.get("ventilation") or {}).get("ventilation_coefficient_m2s"),
        "inversion": {
            "detected": bool((atmosphere.get("inversion") or {}).get("detected")),
            "source": (atmosphere.get("inversion") or {}).get("source"),
            "strength": (atmosphere.get("inversion") or {}).get("strength"),
        },
        "trapping_index": (atmosphere.get("trapping") or {}).get("score"),
        "transport_risk_level": risk_level,
        "transport_risk_score": risk_score,
    }

    return {
        "station": station_name,
        "station_id": station.id,
        "generated_at": now,
        "release_time": release,
        "data_as_of": payload.get("data_as_of"),
        "model": payload.get("model", "xgboost"),
        "forecast_strategy": payload.get("forecast_strategy"),
        "uncertainty_method": payload.get("uncertainty_method"),
        "coverage_target": payload.get("coverage_target"),
        "horizon_hours": horizon_hours,
        "baseline_pm25_ugm3": baseline,
        "forecast_peak_pm25_ugm3": _round(peak, 2),
        "events": events,
        "atmosphere": atmo_summary,
        "methodology": _methodology(),
        "notes": notes,
    }
