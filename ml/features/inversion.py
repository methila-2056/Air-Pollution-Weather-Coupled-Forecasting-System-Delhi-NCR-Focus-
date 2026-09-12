"""Temperature inversion detection.

Two complementary methods are provided:

* **Vertical lapse-rate inversion** (:mod:`ml.features.atmospheric_profile`) —
  the scientifically defensible method required by SIH26082: compute the
  vertical temperature gradient from standard pressure-level temperatures
  (1000/925/850/700 hPa) and detect layers where temperature *increases* with
  height. This is the authoritative method when vertical data is present.

* **PBL-height proxy** (legacy, kept backward compatible) — infers inversion
  from planetary boundary layer height (lower PBL => stronger trapping). This
  remains the documented fallback when no vertical profile is available.

Both are described in ``docs/SIH_GAP_AUDIT.md`` §E and used consistently at
training time and in the live API.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_inversion(pbl_height: float, hour: int = 12) -> tuple:
    """Detect inversion conditions from PBL height and hour of day.

    Args:
        pbl_height: Planetary boundary layer height in meters.
        hour: Hour of day (0-23) for diurnal correction.

    Returns:
        Tuple of (is_inversion: bool, category: str, strength: float).
        - is_inversion: True if any inversion detected (PBL < 500m).
        - category: One of "none", "weak", "moderate", "strong".
        - strength: Normalized 0-1, where 1 = strongest.
    """
    if pbl_height is None or (isinstance(pbl_height, float) and np.isnan(pbl_height)):
        return False, "unknown", 0.0

    if pbl_height < 150:
        category = "strong"
        is_inversion = True
    elif pbl_height < 300:
        category = "moderate"
        is_inversion = True
    elif pbl_height < 500:
        category = "weak"
        is_inversion = True
    else:
        category = "none"
        is_inversion = False

    strength = max(0.0, min(1.0, (500.0 - pbl_height) / 500.0))

    diurnal_factor = _diurnal_inversion_factor(hour)
    strength = min(1.0, strength * diurnal_factor)

    return is_inversion, category, float(strength)


def _diurnal_inversion_factor(hour: int) -> float:
    """Compute diurnal multiplier for inversion strength.

    Inversions are naturally stronger during nighttime and early morning
    (stable boundary layer) and weaker during daytime (convective mixing).

    Returns a multiplier in [0.7, 1.3]:
      - Night/early morning (22-8):  factor ~1.1-1.3 (amplify)
      - Daytime (10-16):             factor ~0.7-0.9 (suppress)
      - Evening (17-21):             factor ~0.9-1.1 (transition)
    """
    if 0 <= hour <= 5:
        return 1.3
    elif 6 <= hour <= 8:
        return 1.2
    elif 9 <= hour <= 10:
        return 1.05
    elif 11 <= hour <= 15:
        return 0.75
    elif 16 <= hour <= 17:
        return 0.9
    elif 18 <= hour <= 20:
        return 1.05
    elif 21 <= hour <= 23:
        return 1.2
    return 1.0


def add_inversion_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add inversion detection features to the dataframe.

    Adds columns:
      - inversion_detected: Binary (1/0) indicating inversion.
      - inversion_strength: Normalized strength 0-1.
      - inversion_category: Categorical label (none/weak/moderate/strong).
    """
    df = df.copy()
    if "pbl_height" not in df.columns:
        df["inversion_detected"] = 0
        df["inversion_strength"] = 0.0
        df["inversion_category"] = "none"
        return df

    hour_col = "hour" if "hour" in df.columns else None
    if hour_col is None:
        if "timestamp" in df.columns:
            dt = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
            hour_col = "_tmp_hour"
            df[hour_col] = dt.dt.hour

    results = df.apply(
        lambda row: detect_inversion(row["pbl_height"], row[hour_col] if hour_col else 12),
        axis=1,
    )

    df["inversion_detected"] = results.apply(lambda r: int(r[0]))
    df["inversion_category"] = results.apply(lambda r: r[1])
    df["inversion_strength"] = results.apply(lambda r: r[2])

    if hour_col == "_tmp_hour":
        df.drop(columns=[hour_col], inplace=True)

    return df


# --------------------------------------------------------------------------
# Lapse-rate + PBL-classification features (SIH26082 §4)
# --------------------------------------------------------------------------

#: Column names for the vertical temperature profile. When present (as e.g.
#: ``temperature_925hPa``, ``temperature_850hPa``), lapse-rate inversion is used.
PRESSURE_LEVEL_COL_PREFIX = "temperature_{}hPa"
PRESSURE_LEVELS = [1000, 925, 850, 700]

#: Column names for geopotential heights (used for inversion_base/top reporting).
GEOPOTENTIAL_COL_PREFIX = "geopotential_height_{}hPa"


def _extract_temp_by_level(df_row) -> dict:
    """Pull {pressure_hPa: temperature} from a DataFrame row when available."""
    temps = {}
    for p in PRESSURE_LEVELS:
        col = PRESSURE_LEVEL_COL_PREFIX.format(p)
        if col in df_row.index:
            val = df_row.get(col)
            if pd.notna(val):
                try:
                    temps[p] = float(val)
                except (TypeError, ValueError):
                    continue
    return temps


def add_lapse_rate_inversion_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lapse-rate inversion features from vertical temperature columns.

    Expected optional input columns: ``temperature_{1000,925,850,700}hPa``
    (degC) from the Open-Meteo pressure-level feed. When none are present the
    existing PBL-proxy columns are returned unchanged.

    Adds:
      - inversion_source            : "lapse_rate" | "pbl_proxy"
      - inversion_base_pressure     : hPa (strongest layer base) or None
      - inversion_top_pressure      : hPa (strongest layer top) or None
      - strongest_layer_gradient    : K/100 hPa or None
      - low_pbl_flag                : bool
      - pbl_category                : strong_trapping/.../good_dispersion/unknown
      - dispersion_condition        : TRAPPED/LIMITED/MODERATE/GOOD/UNKNOWN
    """
    from .atmospheric_profile import combine_inversion

    df = df.copy()

    def _row_analysis(row):
        temps = _extract_temp_by_level(row)
        pbl = row.get("pbl_height")
        if pd.notna(pbl):
            try:
                pbl = float(pbl)
            except (TypeError, ValueError):
                pbl = None
        return combine_inversion(pbl, temps if temps else None)

    analyses = df.apply(_row_analysis, axis=1)

    for key in (
        "inversion_source",
        "inversion_base_pressure",
        "inversion_top_pressure",
        "strongest_layer_gradient",
        "low_pbl_flag",
        "pbl_category",
        "dispersion_condition",
    ):
        df[key] = analyses.apply(lambda a, k=key: a.get(k))

    # Refresh the base inversion columns from the (possibly lapse-rate) analysis.
    df["inversion_detected"] = analyses.apply(lambda a: int(bool(a.get("inversion_detected"))))
    df["inversion_strength"] = analyses.apply(lambda a: float(a.get("inversion_strength", 0.0)))
    df["inversion_category"] = analyses.apply(lambda a: str(a.get("inversion_category", "none")))

    return df
