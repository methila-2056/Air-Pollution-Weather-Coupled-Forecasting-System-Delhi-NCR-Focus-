"""Pollution data preprocessing for AeroCast-NCR.

Loads raw CPCB pollution CSVs, normalizes column names, parses timestamps,
validates pollutant ranges, flags outliers, and saves processed data.
"""

import glob
import os
from typing import Optional

import numpy as np
import pandas as pd


POLLUTANT_RANGES = {
    "pm25": (0, 1000),
    "pm10": (0, 1000),
    "o3": (0, 1200),
    "no2": (0, 1000),
    "so2": (0, 2000),
    "co": (0, 50),
}

COLUMN_ALIASES = {
    "from date": "timestamp",
    "to date": "timestamp",
    "pm2.5": "pm25",
    "pm10": "pm10",
    "no2": "no2",
    "o3": "o3",
    "so2": "so2",
    "co": "co",
    "aqi": "aqi",
    "station": "station",
    "date": "timestamp",
    "time": "timestamp",
    "datetime": "timestamp",
}

STATION_COORDS = {
    "Anand_Vihar": {"latitude": 28.6492, "longitude": 77.2918},
    "RK_Puram": {"latitude": 28.5601, "longitude": 77.1835},
    "ITO": {"latitude": 28.6290, "longitude": 77.2410},
    "Dwarka": {"latitude": 28.5921, "longitude": 77.0460},
    "Punjabi_Bagh": {"latitude": 28.6692, "longitude": 77.1285},
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lowercase snake_case."""
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    rename_map = {}
    for col in df.columns:
        if col in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[col]
    df.rename(columns=rename_map, inplace=True)
    return df


def parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Parse timestamp column to datetime, coercing errors."""
    df = df.copy()
    if "timestamp" not in df.columns:
        for fallback in ["from_date", "to_date", "date", "time", "datetime"]:
            if fallback in df.columns:
                df.rename(columns={fallback: "timestamp"}, inplace=True)
                break
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df.dropna(subset=["timestamp"], inplace=True)
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def validate_pollutant_ranges(df: pd.DataFrame) -> pd.DataFrame:
    """Clamp pollutant values to valid ranges and flag out-of-range rows."""
    df = df.copy()
    df["outlier_flags"] = ""
    for pollutant, (lo, hi) in POLLUTANT_RANGES.items():
        if pollutant not in df.columns:
            continue
        df[pollutant] = pd.to_numeric(df[pollutant], errors="coerce")
        out_of_range = (df[pollutant] < lo) | (df[pollutant] > hi)
        df.loc[out_of_range, "outlier_flags"] += f"{pollutant}_oor,"
        df[pollutant] = df[pollutant].clip(lower=lo, upper=hi)
    df["outlier_flags"] = df["outlier_flags"].str.rstrip(",")
    return df


def flag_statistical_outliers(df: pd.DataFrame, z_thresh: float = 4.0) -> pd.DataFrame:
    """Flag statistical outliers using Z-score per pollutant."""
    df = df.copy()
    if "outlier_flags" not in df.columns:
        df["outlier_flags"] = ""
    for pollutant in POLLUTANT_RANGES:
        if pollutant not in df.columns:
            continue
        mean = df[pollutant].mean()
        std = df[pollutant].std()
        if std == 0 or pd.isna(std):
            continue
        z = (df[pollutant] - mean) / std
        is_outlier = z.abs() > z_thresh
        df.loc[is_outlier, "outlier_flags"] = df.loc[is_outlier, "outlier_flags"].apply(
            lambda x: (x + "," if x else "") + f"{pollutant}_zscore"
        )
    return df


def add_station_coords(df: pd.DataFrame) -> pd.DataFrame:
    """Add latitude and longitude columns based on station name."""
    df = df.copy()
    if "station" in df.columns:
        df["latitude"] = df["station"].map(lambda s: STATION_COORDS.get(s, {}).get("latitude"))
        df["longitude"] = df["station"].map(lambda s: STATION_COORDS.get(s, {}).get("longitude"))
    return df


def load_pollution_csv(path: str) -> pd.DataFrame:
    """Load a single pollution CSV and apply preprocessing."""
    df = pd.read_csv(path)
    df = normalize_columns(df)
    df = parse_timestamps(df)
    df = validate_pollutant_ranges(df)
    df = flag_statistical_outliers(df)
    df = add_station_coords(df)
    return df


def load_all_pollution(data_dir: str) -> pd.DataFrame:
    """Load and concatenate all pollution CSVs from a directory."""
    pattern = os.path.join(data_dir, "*pollution*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No pollution CSVs found in {data_dir}")
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            frame = load_pollution_csv(f)
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
    """Save processed pollution data to CSV."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} processed pollution rows to {output_path}")


def process_pollution(
    input_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Full pipeline: load, clean, validate, save.

    Either provide *input_dir* to load from CSVs or *df* to process in-memory.
    """
    if df is None:
        if input_dir is None:
            raise ValueError("Provide either input_dir or df")
        df = load_all_pollution(input_dir)
    if df.empty:
        print("No pollution data to process.")
        return df
    df = normalize_columns(df)
    df = parse_timestamps(df)
    df = validate_pollutant_ranges(df)
    df = flag_statistical_outliers(df)
    df = add_station_coords(df)
    if output_path:
        save_processed(df, output_path)
    print(f"Pollution processing complete: {len(df)} rows, {df.shape[1]} columns")
    return df
