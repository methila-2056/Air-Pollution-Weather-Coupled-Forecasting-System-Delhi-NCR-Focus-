"""Vertical atmospheric analysis — lapse-rate inversion and PBL classification.

Implements the scientifically defensible inversion detection required by
SIH26082: instead of (or in addition to) the PBL-height *proxy*, inversion is
detected from the **vertical temperature profile** by computing the atmospheric
temperature gradient with height.

Physical basis
--------------
In a "normal" tropospheric lapse the temperature *decreases* with height
(environmental lapse rate ~ -6.5 K/km). A **temperature inversion** occurs when
temperature *increases* with height over some layer, i.e. a *positive* vertical
temperature gradient. This traps pollutants close to the ground (stable layer),
which is exactly the phenomenon the problem statement asks us to track.

Conventions
-----------
* Temperatures are supplied as a mapping pressure_hPa -> temperature(degC or K).
* We require at least two levels to form a gradient. Levels are sorted by
  pressure (descending), i.e. from surface to top.
* gradient = dT / d(log p) approximated as (T2 - T1)/(ln p1 - ln p2) over the
  layer. Because pressure *decreases* upward, a positive temperature increase
  upward corresponds to a positive dT/d(ln p) with our sign convention
  (see ``_coarse_gradient``).

Units are transparent: temperatures in degC (callers are expected to pass degC
as returned by Open-Meteo). All derived strengths are normalised to [0, 1].
"""

from __future__ import annotations

import numpy as np

#: Pressure levels used for inversion analysis, surface -> top.
DEFAULT_LEVELS_HPA: list[float] = [1000, 925, 850, 700]

#: Inversion categories by gradient strength (K / 100 hPa), applied to the
#: strongest (most positive) layer gradient.
STRONG_INVERSION_THRESHOLD_K = 1.5  # > 1.5 K/100hPa -> strong
MODERATE_INVERSION_THRESHOLD_K = 0.6  # > 0.6  K/100hPa -> moderate
WEAK_INVERSION_THRESHOLD_K = 0.0  # > 0.0  K/100hPa -> weak inversion (T increases w/ height)

#: PBL height (m) classification used for the PBL proxy fallback.
PBL_STRONG_M = 150.0
PBL_MODERATE_M = 300.0
PBL_WEAK_M = 500.0
PBL_CLIMATOLOGICAL_DEFAULT_M = 600.0


def _level_pairs(levels_hpa: list[float]) -> list[tuple[float, float]]:
    """Return adjacent (base_pressure, top_pressure) pairs.

    Levels are sorted descending by pressure (base -> top). Each pair is
    ``(base_level, top_level)`` where base has *higher* pressure.
    """
    ordered = sorted(levels_hpa, reverse=True)  # base (highest p) first
    return [(base, top) for base, top in zip(ordered, ordered[1:], strict=False)]


def _coarse_gradient(t_base: float, t_top: float, p_base: float, p_top: float) -> float | None:
    """Approximate vertical temperature gradient over a layer (K per 100 hPa).

    A linear-in-pressure gradient (transparent, standard for layer reporting)::

        dT/dp = (T_top - T_base) / (p_base - p_top)     [K / hPa]
        gradient = dT/dp * 100                          [K / 100 hPa]

    With p_base > p_top (base is higher pressure / lower altitude), a warmer
    layer aloft (T_top > T_base) gives a **positive** gradient == temperature
    inversion (temperature increases with height).
    """
    if p_base is None or p_top is None or t_base is None or t_top is None:
        return None
    if not (p_base > 0 and p_top > 0) or p_base <= p_top:
        return None
    try:
        dp = float(p_base) - float(p_top)
        if abs(dp) < 1e-9:
            return None
        grad = (float(t_top) - float(t_base)) / dp * 100.0  # per 100 hPa
        return float(grad)
    except (TypeError, ValueError):
        return None


def compute_lapse_rates(temp_by_level: dict[float, float]) -> dict[tuple[float, float], float]:
    """Compute layer gradient (K/100 hPa) for each adjacent level pair.

    Args:
        temp_by_level: mapping pressure_hPa -> temperature(degC).

    Returns:
        dict mapping (base_pressure, top_pressure) -> gradient.
    """
    present = {p: t for p, t in (temp_by_level or {}).items() if t is not None}
    if len(present) < 2:
        return {}
    grades: dict[tuple[float, float], float] = {}
    for p_base, p_top in _level_pairs(list(present.keys())):
        g = _coarse_gradient(present[p_base], present[p_top], p_base, p_top)
        if g is not None:
            grades[(p_base, p_top)] = g
    return grades


def classify_gradient(gradients: dict[tuple[float, float], float]) -> dict[str, object]:
    """Classify inversion from a set of layer gradients.

    Returns a dict with:
      - inversion_detected       : bool
      - inversion_strength       : float in [0, 1] (based on strongest layer)
      - inversion_category       : none / weak / moderate / strong
      - inversion_base_pressure  : hPa or None
      - inversion_top_pressure   : hPa or None
      - strongest_layer_gradient : K/100 hPa of the strongest (most negative
                                   stability) layer, or None
      - profile_available        : bool (>=2 levels)
    """
    if not gradients:
        return {
            "inversion_detected": False,
            "inversion_strength": 0.0,
            "inversion_category": "none",
            "inversion_base_pressure": None,
            "inversion_top_pressure": None,
            "strongest_layer_gradient": None,
            "profile_available": False,
        }

    # Strongest layer == the layer with the most *positive* gradient (temperature
    # increasing most sharply upward) => the most trapping layer.
    (base_p, top_p), gmax = max(gradients.items(), key=lambda kv: (kv[1], kv[0]))

    if gmax > STRONG_INVERSION_THRESHOLD_K:
        category = "strong"
    elif gmax > MODERATE_INVERSION_THRESHOLD_K:
        category = "moderate"
    elif gmax > WEAK_INVERSION_THRESHOLD_K:
        category = "weak"
    else:
        category = "none"

    # Normalise strength: linear ramp from 0 at WEAK threshold up to 1 at a
    # physically strong cap (e.g. 4 K/100 hPa).
    strength = np.clip((gmax - WEAK_INVERSION_THRESHOLD_K) / (4.0 - WEAK_INVERSION_THRESHOLD_K), 0.0, 1.0)

    return {
        "inversion_detected": category != "none",
        "inversion_strength": round(float(strength), 4),
        "inversion_category": category,
        "inversion_base_pressure": base_p,
        "inversion_top_pressure": top_p,
        "strongest_layer_gradient": round(gmax, 4),
        "profile_available": True,
    }


def classify_pbl(
    pbl_height: float | None,
    *,
    low_pbl_threshold_m: float = PBL_MODERATE_M,
    pbl_valid: tuple[float, float] | None = None,
) -> dict[str, object]:
    """Classify the planetary boundary layer height.

    Returns:
      - low_pbl_flag       : bool (True when pbl <= low_pbl_threshold_m)
      - pbl_category       : strong_trapping / moderate_trapping / weak_trapping / good_dispersion / unknown
      - dispersion_condition: TRApped / LIMITED / MODERATE / GOOD / UNKNOWN
    """
    pbl_valid = pbl_valid or (0.0, 5000.0)
    if pbl_height is None or (isinstance(pbl_height, float) and np.isnan(pbl_height)):
        return {
            "low_pbl_flag": False,
            "pbl_category": "unknown",
            "dispersion_condition": "UNKNOWN",
        }
    lo, hi = pbl_valid
    if not (lo <= pbl_height <= hi):
        return {
            "low_pbl_flag": False,
            "pbl_category": "unknown",
            "dispersion_condition": "UNKNOWN",
        }

    low = pbl_height <= low_pbl_threshold_m
    if pbl_height < PBL_STRONG_M:
        cat, cond = "strong_trapping", "TRAPPED"
    elif pbl_height < PBL_MODERATE_M:
        cat, cond = "moderate_trapping", "LIMITED"
    elif pbl_height < PBL_WEAK_M:
        cat, cond = "weak_trapping", "MODERATE"
    else:
        cat, cond = "good_dispersion", "GOOD"

    return {
        "low_pbl_flag": bool(low),
        "pbl_category": cat,
        "dispersion_condition": cond,
    }


def combine_inversion(
    pbl_height: float | None,
    temp_by_level: dict[float, float] | None,
    *,
    pbl_valid: tuple[float, float] | None = None,
) -> dict[str, object]:
    """Combine vertical lapse-rate and PBL-proxy inversion status.

    When vertical data is available the lapse-rate result is authoritative
    (``source == "lapse_rate"``). When it is not, the PBL-height proxy is used
    and marked ``source == "pbl_proxy"`` so consumers can disclose the basis.

    Returns a flat dict with keys from classify_gradient()/classify_pbl() plus
    ``inversion_source``.
    """
    res = classify_gradient(compute_lapse_rates(temp_by_level or {}))
    pbl = classify_pbl(pbl_height, pbl_valid=pbl_valid)

    if res["profile_available"]:
        out = dict(res)
        out["inversion_source"] = "lapse_rate"
    else:
        # PBL-height proxy (documented fallback; see docs/SIH_GAP_AUDIT.md).
        is_inv = pbl_height is not None and pbl_height < PBL_WEAK_M
        if pbl_height is not None and not (isinstance(pbl_height, float) and np.isnan(pbl_height)):
            strength = np.clip((PBL_WEAK_M - pbl_height) / PBL_WEAK_M, 0.0, 1.0)
            if pbl_height < PBL_STRONG_M:
                cat = "strong"
            elif pbl_height < PBL_MODERATE_M:
                cat = "moderate"
            elif pbl_height < PBL_WEAK_M:
                cat = "weak"
            else:
                cat = "none"
        else:
            strength, cat = 0.0, "unknown"
        out = {
            "inversion_detected": bool(is_inv),
            "inversion_strength": round(float(strength), 4),
            "inversion_category": cat,
            "inversion_base_pressure": None,
            "inversion_top_pressure": None,
            "strongest_layer_gradient": None,
            "profile_available": False,
            "inversion_source": "pbl_proxy",
        }

    out.update(pbl)
    return out
