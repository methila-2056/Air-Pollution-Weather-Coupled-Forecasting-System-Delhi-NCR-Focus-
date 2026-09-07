"""Fire (FIRMS) data preprocessing for AeroCast-NCR.

Loads NASA FIRMS fire CSVs, parses acquisition date/time, filters by
confidence, computes distance to Delhi center, clusters fires by region,
and saves processed data.
"""

import glob
import math
import os
from typing import Optional

import numpy as np
import pandas as pd


DELHI_CENTER_LAT = 28.6139
DELHI_CENTER_LON = 77.2090

REGION_BOUNDARIES = {
    "Punjab": {"lat_min": 29.5, "lat_max": 32.5, "lon_min": 73.5, "lon_max": 77.0},
    "Haryana": {"lat_min": 27.5, "lat_max": 30.5, "lon_min": 74.5, "lon_max": 77.5},
    "Rajasthan": {"lat_min": 23.0, "lat_max": 30.5, "lon_min": 69.5, "lon_max": 76.5},
    "UP": {"lat_min": 24.0, "lat_max": 30.5, "lon_min": 77.0, "lon_max": 84.5},
    "Delhi_NCR": {"lat_min": 28.0, "lat_max": 29.0, "lon_min": 76.5, "lon_max": 77.5},
}

FIRMS_COLUMN_ALIASES = {
    "latitude": "lat",
    "longitude": "lon",
    "acq_date": "acq_date",
    "acq_time": "acq_time",
    "brightness": "brightness",
    "scan": "scan",
    "track": "track",
    "bright_t31": "bright_t31",
    "frp": "frp",
    "daynight": "daynight",
    "satellite": "satellite",
}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize FIRMS column names."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    rename_map = {c: FIRMS_COLUMN_ALIASES[c] for c in df.columns if c in FIRMS_COLUMN_ALIASES}
    df.rename(columns=rename_map, inplace=True)
    return df


def parse_acquisition_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Parse acq_date and acq_time into a single timestamp."""
    df = df.copy()
    if "acq_date" in df.columns:
        df["acq_date"] = pd.to_datetime(df["acq_date"], errors="coerce")
    if "acq_time" in df.columns and "acq_date" in df.columns:
        time_str = df["acq_time"].astype(str).str.zfill(4)
        hours = time_str.str[:2].astype(int, errors="ignore")
        minutes = time_str.str[2:].astype(int, errors="ignore")
        df["acq_timestamp"] = df["acq_date"] + pd.to_timedelta(hours, unit="h") + pd.to_timedelta(minutes, unit="m")
    elif "acq_date" in df.columns:
        df["acq_timestamp"] = df["acq_date"]
    return df


def filter_by_confidence(df: pd.DataFrame, min_confidence: str = "nominal") -> pd.DataFrame:
    """Filter fires to high and medium (nominal) confidence only."""
    df = df.copy()
    if "confidence" not in df.columns:
        return df
    confidence_levels = {"low": 0, "nominal": 1, "high": 2}
    min_level = confidence_levels.get(min_confidence.lower(), 0)
    df["confidence_num"] = df["confidence"].astype(str).str.lower().map(confidence_levels).fillna(0)
    df = df[df["confidence_num"] >= min_level].copy()
    df.drop(columns=["confidence_num"], inplace=True, errors="ignore")
    return df


def compute_distance_to_delhi(df: pd.DataFrame) -> pd.DataFrame:
    """Compute distance of each fire to Delhi center in km."""
    df = df.copy()
    if "lat" in df.columns and "lon" in df.columns:
        df["distance_to_delhi_km"] = df.apply(
            lambda row: haversine_distance(
                DELHI_CENTER_LAT, DELHI_CENTER_LON, row["lat"], row["lon"]
            ),
            axis=1,
        )
    return df


def assign_region(df: pd.DataFrame) -> pd.DataFrame:
    """Assign each fire to a geographic region based on lat/lon."""
    df = df.copy()
    if "lat" not in df.columns or "lon" not in df.columns:
        return df

    def _classify(row):
        lat, lon = row["lat"], row["lon"]
        for region, bounds in REGION_BOUNDARIES.items():
            if (
                bounds["lat_min"] <= lat <= bounds["lat_max"]
                and bounds["lon_min"] <= lon <= bounds["lon_max"]
            ):
                return region
        return "Other"

    df["fire_region"] = df.apply(_classify, axis=1)
    return df


def load_fire_csv(path: str) -> pd.DataFrame:
    """Load a single fire CSV and preprocess."""
    df = pd.read_csv(path)
    df = normalize_columns(df)
    df = parse_acquisition_datetime(df)
    df = filter_by_confidence(df)
    df = compute_distance_to_delhi(df)
    df = assign_region(df)
    df.dropna(subset=["lat", "lon"], inplace=True)
    return df


def load_all_fires(data_dir: str) -> pd.DataFrame:
    """Load and concatenate all fire CSVs from a directory."""
    pattern = os.path.join(data_dir, "*fire*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No fire CSVs found in {data_dir}")
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            frame = load_fire_csv(f)
            if not frame.empty:
                frames.append(frame)
                print(f"  Loaded {len(frame)} rows from {os.path.basename(f)}")
        except Exception as e:
            print(f"  Error loading {os.path.basename(f)}: {e}")
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined.drop_duplicates(subset=["lat", "lon", "acq_timestamp"], keep="last", inplace=True)
    combined.sort_values("acq_timestamp", inplace=True)
    combined.reset_index(drop=True, inplace=True)
    return combined


def save_processed(df: pd.DataFrame, output_path: str) -> None:
    """Save processed fire data to CSV."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} processed fire rows to {output_path}")


def process_fire(
    input_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Full pipeline: load, clean, filter, enrich, save."""
    if df is None:
        if input_dir is None:
            raise ValueError("Provide either input_dir or df")
        df = load_all_fires(input_dir)
    if df.empty:
        print("No fire data to process.")
        return df
    df = normalize_columns(df)
    df = parse_acquisition_datetime(df)
    df = filter_by_confidence(df)
    df = compute_distance_to_delhi(df)
    df = assign_region(df)
    df.dropna(subset=["lat", "lon"], inplace=True)
    if output_path:
        save_processed(df, output_path)
    print(f"Fire processing complete: {len(df)} rows, {df.shape[1]} columns")
    return df
