"""Weather data preprocessing for AeroCast-NCR.

Loads Open-Meteo weather CSVs, parses hourly timestamps, converts wind units,
computes wind components, validates ranges, and saves processed data.
"""

import glob
import math
import os
from typing import Optional

import numpy as np
import pandas as pd


WEATHER_VALID_RANGES = {
    "temperature": (-60, 60),
    "humidity": (0, 100),
    "pressure_msl": (870, 1084),
    "surface_pressure": (870, 1084),
    "wind_speed": (0, 100),
    "wind_direction": (0, 360),
    "precipitation": (0, 500),
    "cloud_cover": (0, 100),
    "pbl_height": (0, 5000),
}

COLUMN_ALIASES = {
    "time": "timestamp",
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "boundary_layer_height": "pbl_height",
    "datetime": "timestamp",
}

WIND_SPEED_THRESHOLD_KMH = 30


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lowercase snake_case."""
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    rename_map = {c: COLUMN_ALIASES[c] for c in df.columns if c in COLUMN_ALIASES}
    df.rename(columns=rename_map, inplace=True)
    return df


def parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Parse timestamp column to datetime."""
    df = df.copy()
    ts_col = "timestamp"
    if ts_col not in df.columns:
        for fallback in ["time", "datetime", "date"]:
            if fallback in df.columns:
                df.rename(columns={fallback: ts_col}, inplace=True)
                break
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df.dropna(subset=[ts_col], inplace=True)
        df.sort_values(ts_col, inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def convert_wind_speed(df: pd.DataFrame) -> pd.DataFrame:
    """Convert wind speed from km/h to m/s if values appear to be in km/h."""
    df = df.copy()
    if "wind_speed" not in df.columns:
        return df
    df["wind_speed"] = pd.to_numeric(df["wind_speed"], errors="coerce")
    if df["wind_speed"].median() > WIND_SPEED_THRESHOLD_KMH:
        df["wind_speed"] = df["wind_speed"] / 3.6
        print("  Converted wind speed from km/h to m/s")
    return df


def compute_wind_components(df: pd.DataFrame) -> pd.DataFrame:
    """Compute u and v wind components from speed and direction."""
    df = df.copy()
    if "wind_speed" not in df.columns or "wind_direction" not in df.columns:
        return df
    wind_dir_rad = np.deg2rad(df["wind_direction"].fillna(0))
    df["wind_u"] = -df["wind_speed"].fillna(0) * np.sin(wind_dir_rad)
    df["wind_v"] = -df["wind_speed"].fillna(0) * np.cos(wind_dir_rad)
    return df


def validate_ranges(df: pd.DataFrame) -> pd.DataFrame:
    """Validate weather variables against physical ranges, flag outliers."""
    df = df.copy()
    df["weather_outlier_flags"] = ""
    for var, (lo, hi) in WEATHER_VALID_RANGES.items():
        if var not in df.columns:
            continue
        df[var] = pd.to_numeric(df[var], errors="coerce")
        out_of_range = (df[var] < lo) | (df[var] > hi)
        df.loc[out_of_range, "weather_outlier_flags"] = df.loc[
            out_of_range, "weather_outlier_flags"
        ].apply(lambda x: (x + "," if x else "") + f"{var}_oor")
        df[var] = df[var].clip(lower=lo, upper=hi)
    df["weather_outlier_flags"] = df["weather_outlier_flags"].str.rstrip(",")
    return df


def load_weather_csv(path: str) -> pd.DataFrame:
    """Load a single weather CSV and preprocess."""
    df = pd.read_csv(path)
    df = normalize_columns(df)
    df = parse_timestamps(df)
    df = convert_wind_speed(df)
    df = compute_wind_components(df)
    df = validate_ranges(df)
    return df


def load_all_weather(data_dir: str) -> pd.DataFrame:
    """Load and concatenate all weather CSVs from a directory."""
    pattern = os.path.join(data_dir, "*weather*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No weather CSVs found in {data_dir}")
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            frame = load_weather_csv(f)
            if not frame.empty:
                frames.append(frame)
                print(f"  Loaded {len(frame)} rows from {os.path.basename(f)}")
        except Exception as e:
            print(f"  Error loading {os.path.basename(f)}: {e}")
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined.drop_duplicates(subset=["timestamp", "station"], keep="last", inplace=True)
    combined.sort_values(["station", "timestamp"], inplace=True)
    combined.reset_index(drop=True, inplace=True)
    return combined


def save_processed(df: pd.DataFrame, output_path: str) -> None:
    """Save processed weather data to CSV."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} processed weather rows to {output_path}")


def process_weather(
    input_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Full pipeline: load, clean, validate, save."""
    if df is None:
        if input_dir is None:
            raise ValueError("Provide either input_dir or df")
        df = load_all_weather(input_dir)
    if df.empty:
        print("No weather data to process.")
        return df
    df = normalize_columns(df)
    df = parse_timestamps(df)
    df = convert_wind_speed(df)
    df = compute_wind_components(df)
    df = validate_ranges(df)
    if output_path:
        save_processed(df, output_path)
    print(f"Weather processing complete: {len(df)} rows, {df.shape[1]} columns")
    return df
