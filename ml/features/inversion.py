"""Temperature inversion detection from PBL height data.

Uses planetary boundary layer (PBL) height as a proxy for atmospheric
inversion conditions. Lower PBL indicates stronger trapping of pollutants.

Inversion categories:
  - PBL < 150m:  Strong inversion
  - PBL 150-300m: Moderate inversion
  - PBL 300-500m: Weak inversion
  - PBL > 500m:  No inversion

inversion_strength is normalized 0-1 where 1 = strongest inversion.
Diurnal tendency makes inversions stronger at night/early morning.
"""

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
