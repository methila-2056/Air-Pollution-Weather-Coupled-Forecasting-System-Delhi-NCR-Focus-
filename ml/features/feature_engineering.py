"""Feature engineering pipeline for AeroCast-NCR.

Generates temporal features, pollution lags, rolling statistics, wind
decomposition, temperature/humidity lags, and additional derived features.
Input: coupled_dataset.csv
Output: featured_dataset.csv
"""

import os
from typing import Optional

import numpy as np
import pandas as pd

from .inversion import add_inversion_features
from .fire_impact import add_fire_features


POLLUTANT_COLS = ["pm25", "pm10", "o3", "no2", "so2", "co"]
POLLUTANT_LAGS = [1, 3, 6, 12, 24]
ROLLING_WINDOWS = [3, 6, 12, 24]
STD_WINDOWS = [6, 24]
TEMPERATURE_LAGS = [1, 6, 24]
HUMIDITY_LAGS = [1, 6, 24]

# Standardize column names coming from the raw Open-Meteo weather CSVs
# (build_dataset.py) onto the canonical names used across the ML pipeline.
COLUMN_STANDARDIZATION = {
    "boundary_layer_height": "pbl_height",
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "pressure_msl": "pressure_msl",
}

SEASON_MAP = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Rename raw Open-Meteo columns to canonical ML-feature names.

    Maps e.g. boundary_layer_height -> pbl_height, temperature_2m -> temperature
    so downstream feature builders (inversion, ventilation, fire impact) and the
    model inference layer see consistent, documented column names.
    """
    df = df.copy()
    rename = {k: v for k, v in COLUMN_STANDARDIZATION.items() if k in df.columns}
    if rename:
        df.rename(columns=rename, inplace=True)
    return df


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add time-based features from the timestamp column.

    Features added:
      - hour: Hour of day (0-23)
      - day_of_week: Day of week (0=Monday, 6=Sunday)
      - month: Calendar month (1-12)
      - season: Categorical season (winter/spring/summer/autumn)
      - day_of_year: Day of year (1-366)
      - is_weekend: Binary flag for Saturday/Sunday
      - hour_sin, hour_cos: Cyclic encoding of hour
      - dayofweek_sin, dayofweek_cos: Cyclic encoding of day of week
      - month_sin, month_cos: Cyclic encoding of month
    """
    df = df.copy()
    if "timestamp" not in df.columns:
        return df
    dt = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["hour"] = dt.dt.hour
    df["day_of_week"] = dt.dt.dayofweek
    df["month"] = dt.dt.month
    df["season"] = df["month"].map(SEASON_MAP)
    season_dummies = pd.get_dummies(df["season"], prefix="season", dtype=int)
    df = pd.concat([df, season_dummies], axis=1)
    df["day_of_year"] = dt.dt.dayofyear
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dayofweek_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dayofweek_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    return df


def add_pollution_lags(df: pd.DataFrame, cols: Optional[list] = None, lags: Optional[list] = None) -> pd.DataFrame:
    """Add lagged features for pollutant columns.

    For each pollutant in *cols* and each lag in *lags*, creates a column
    named {pollutant}_lag{lag} containing the value from *lag* hours ago.
    """
    df = df.copy()
    cols = cols or POLLUTANT_COLS
    lags = lags or POLLUTANT_LAGS
    for col in cols:
        if col not in df.columns:
            continue
        for lag in lags:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
    return df


def add_rolling_means(df: pd.DataFrame, cols: Optional[list] = None, windows: Optional[list] = None) -> pd.DataFrame:
    """Add rolling mean features for pollutant columns.

    For each pollutant and each window size, creates {pollutant}_roll_mean_{window}h
    as the trailing mean over *window* hours.
    """
    df = df.copy()
    cols = cols or POLLUTANT_COLS
    windows = windows or ROLLING_WINDOWS
    for col in cols:
        if col not in df.columns:
            continue
        for w in windows:
            df[f"{col}_roll_mean_{w}h"] = df[col].rolling(window=w, min_periods=1).mean()
    return df


def add_rolling_std(df: pd.DataFrame, cols: Optional[list] = None, windows: Optional[list] = None) -> pd.DataFrame:
    """Add rolling standard deviation features for pollutant columns.

    For each pollutant and each window size, creates {pollutant}_roll_std_{window}h
    as the trailing standard deviation over *window* hours.
    """
    df = df.copy()
    cols = cols or ["pm25", "pm10"]
    windows = windows or STD_WINDOWS
    for col in cols:
        if col not in df.columns:
            continue
        for w in windows:
            df[f"{col}_roll_std_{w}h"] = df[col].rolling(window=w, min_periods=1).std()
    return df


def add_wind_decomposition(df: pd.DataFrame) -> pd.DataFrame:
    """Add sin/cos decomposition of wind direction.

    Features:
      - wind_dir_sin: sin(wind_direction) — east-west component
      - wind_dir_cos: cos(wind_direction) — north-south component
    """
    df = df.copy()
    if "wind_direction" in df.columns:
        wind_dir_rad = np.deg2rad(df["wind_direction"].fillna(0))
        df["wind_dir_sin"] = np.sin(wind_dir_rad)
        df["wind_dir_cos"] = np.cos(wind_dir_rad)
    return df


def add_temperature_lags(df: pd.DataFrame, lags: Optional[list] = None) -> pd.DataFrame:
    """Add lagged temperature features.

    Creates temperature_lag{h} for each lag hour h.
    """
    df = df.copy()
    lags = lags or TEMPERATURE_LAGS
    if "temperature" in df.columns:
        for lag in lags:
            df[f"temperature_lag{lag}"] = df["temperature"].shift(lag)
    return df


def add_humidity_lags(df: pd.DataFrame, lags: Optional[list] = None) -> pd.DataFrame:
    """Add lagged humidity features.

    Creates humidity_lag{h} for each lag hour h.
    """
    df = df.copy()
    lags = lags or HUMIDITY_LAGS
    if "humidity" in df.columns:
        for lag in lags:
            df[f"humidity_lag{lag}"] = df["humidity"].shift(lag)
    return df


def add_pollution_rate_of_change(df: pd.DataFrame) -> pd.DataFrame:
    """Add hourly rate of change for key pollutants (delta from previous hour)."""
    df = df.copy()
    for col in ["pm25", "pm10", "o3", "no2"]:
        if col in df.columns:
            df[f"{col}_delta_1h"] = df[col].diff(1)
    return df


def add_composite_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add composite interaction features."""
    df = df.copy()
    if "temperature" in df.columns and "humidity" in df.columns:
        df["temp_humidity_index"] = df["temperature"] * df["humidity"] / 100.0
    if "wind_speed" in df.columns and "pbl_height" in df.columns:
        df["ventilation_index"] = df["wind_speed"] * df["pbl_height"]
    if "pm25" in df.columns and "pm10" in df.columns:
        df["pm_ratio"] = df["pm25"] / df["pm10"].replace(0, np.nan)
    if "temperature" in df.columns and "humidity" in df.columns and "wind_speed" in df.columns:
        df["dispersion_potential"] = df["wind_speed"] * df["pbl_height"] / (df["temperature"] + 273.15) if "pbl_height" in df.columns else np.nan
    return df


FEATURE_DOCUMENTATION = {
    "hour": "Hour of day (0-23)",
    "day_of_week": "Day of week (0=Monday, 6=Sunday)",
    "month": "Calendar month (1-12)",
    "season": "Categorical season",
    "day_of_year": "Day of year (1-366)",
    "is_weekend": "1 if Saturday/Sunday, else 0",
    "hour_sin": "Cyclic sin encoding of hour (period=24)",
    "hour_cos": "Cyclic cos encoding of hour (period=24)",
    "dayofweek_sin": "Cyclic sin encoding of day of week (period=7)",
    "dayofweek_cos": "Cyclic cos encoding of day of week (period=7)",
    "month_sin": "Cyclic sin encoding of month (period=12)",
    "month_cos": "Cyclic cos encoding of month (period=12)",
    "pollutant_lag": "Value of pollutant at t-lag hours",
    "pollutant_roll_mean": "Trailing mean over window hours",
    "pollutant_roll_std": "Trailing std over window hours",
    "wind_dir_sin": "sin(wind_direction) — east-west component",
    "wind_dir_cos": "cos(wind_direction) — north-south component",
    "wind_u": "U (zonal) wind component in m/s",
    "wind_v": "V (meridional) wind component in m/s",
    "temperature_lag": "Temperature at t-lag hours",
    "humidity_lag": "Humidity at t-lag hours",
    "pollutant_delta_1h": "Hourly change in pollutant (t minus t-1)",
    "temp_humidity_index": "temperature * humidity / 100",
    "ventilation_index": "wind_speed * pbl_height",
    "pm_ratio": "PM2.5 / PM10 ratio",
    "inversion_detected": "1 if PBL < 500m indicating inversion",
    "inversion_strength": "Normalized inversion strength 0-1",
    "inversion_category": "none/weak/moderate/strong",
    "fire_impact_score": "Normalized fire impact weighted by wind alignment (0-1)",
    "wind_aligned_fire_count": "Count of fires that are upwind",
}


def get_feature_documentation() -> dict:
    """Return feature documentation dictionary."""
    return FEATURE_DOCUMENTATION.copy()


def run_feature_engineering(
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
    df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Run the full feature engineering pipeline.

    Args:
        input_path: Path to coupled_dataset.csv. Used if df is None.
        output_path: Where to save the featured dataset.
        df: Optional pre-loaded dataframe.

    Returns:
        DataFrame with all engineered features.
    """
    if df is None:
        if input_path is None:
            raise ValueError("Provide either input_path or df")
        print(f"Loading coupled dataset from {input_path} ...")
        df = pd.read_csv(input_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df.sort_values(["station", "timestamp"], inplace=True)
        df.reset_index(drop=True, inplace=True)

    df = standardize_column_names(df)

    print("Running feature engineering pipeline ...")
    n_before = len(df.columns)

    print("  [1/9] Temporal features ...")
    df = add_temporal_features(df)

    print("  [2/9] Pollution lags ...")
    df = add_pollution_lags(df)

    print("  [3/9] Rolling means ...")
    df = add_rolling_means(df)

    print("  [4/9] Rolling std ...")
    df = add_rolling_std(df)

    print("  [5/9] Wind decomposition ...")
    df = add_wind_decomposition(df)

    print("  [6/9] Temperature lags ...")
    df = add_temperature_lags(df)

    print("  [7/9] Humidity lags ...")
    df = add_humidity_lags(df)

    print("  [8/9] Inversion features ...")
    df = add_inversion_features(df)

    print("  [9/9] Fire impact features ...")
    df = add_fire_features(df)

    df = add_pollution_rate_of_change(df)
    df = add_composite_features(df)

    n_after = len(df.columns)
    print(f"\nFeature engineering complete: {n_before} -> {n_after} columns (+{n_after - n_before} features)")

    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "processed", "featured_dataset.csv"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved featured dataset to {output_path}")

    return df
