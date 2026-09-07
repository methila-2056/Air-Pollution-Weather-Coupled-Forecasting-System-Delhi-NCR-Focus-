"""Atmospheric (ERA5/Open-Meteo PBL) data preprocessing for AeroCast-NCR.

Loads ERA5 or Open-Meteo PBL height data, merges with station locations,
cleans and validates values, and saves processed data.
"""

import glob
import os
from typing import Optional

import numpy as np
import pandas as pd


COLUMN_ALIASES = {
    "time": "timestamp",
    "boundary_layer_height": "pbl_height",
    "datetime": "timestamp",
}

STATION_COORDS = {
    "Anand_Vihar": {"latitude": 28.6492, "longitude": 77.2918},
    "RK_Puram": {"latitude": 28.5601, "longitude": 77.1835},
    "ITO": {"latitude": 28.6290, "longitude": 77.2410},
    "Dwarka": {"latitude": 28.5921, "longitude": 77.0460},
    "Punjabi_Bagh": {"latitude": 28.6692, "longitude": 77.1285},
}

PBL_VALID_RANGE = (0, 5000)


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


def merge_with_stations(df: pd.DataFrame) -> pd.DataFrame:
    """Merge atmospheric data with station coordinates.

    If the dataframe already has per-station rows (with a 'station' column),
    attach coordinates. If it's a grid-level dataset, assign nearest station.
    """
    df = df.copy()
    if "station" in df.columns and "latitude" not in df.columns:
        coords_df = pd.DataFrame.from_dict(STATION_COORDS, orient="index").reset_index()
        coords_df.columns = ["station", "latitude", "longitude"]
        df = df.merge(coords_df, on="station", how="left")
    elif "station" not in df.columns and "latitude" in df.columns:
        stations_list = list(STATION_COORDS.keys())
        coords_array = np.array([[v["latitude"], v["longitude"]] for v in STATION_COORDS.values()])

        def _nearest_station(lat, lon):
            dists = np.sqrt((coords_array[:, 0] - lat) ** 2 + (coords_array[:, 1] - lon) ** 2)
            return stations_list[np.argmin(dists)]

        df["station"] = df.apply(lambda r: _nearest_station(r["latitude"], r["longitude"]), axis=1)
    return df


def validate_pbl(df: pd.DataFrame) -> pd.DataFrame:
    """Validate PBL height and fill outliers."""
    df = df.copy()
    if "pbl_height" not in df.columns:
        return df
    df["pbl_height"] = pd.to_numeric(df["pbl_height"], errors="coerce")
    lo, hi = PBL_VALID_RANGE
    outliers = (df["pbl_height"] < lo) | (df["pbl_height"] > hi)
    df.loc[outliers, "pbl_height"] = np.nan
    df["pbl_height"] = df["pbl_height"].interpolate(method="linear", limit=6)
    return df


def load_atmosphere_csv(path: str) -> pd.DataFrame:
    """Load a single atmosphere CSV and preprocess."""
    df = pd.read_csv(path)
    df = normalize_columns(df)
    df = parse_timestamps(df)
    df = merge_with_stations(df)
    df = validate_pbl(df)
    return df


def load_all_atmosphere(data_dir: str) -> pd.DataFrame:
    """Load and concatenate all atmosphere CSVs from a directory."""
    pattern = os.path.join(data_dir, "*atmosphere*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No atmosphere CSVs found in {data_dir}")
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            frame = load_atmosphere_csv(f)
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
    """Save processed atmosphere data to CSV."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} processed atmosphere rows to {output_path}")


def process_atmosphere(
    input_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Full pipeline: load, clean, validate, save."""
    if df is None:
        if input_dir is None:
            raise ValueError("Provide either input_dir or df")
        df = load_all_atmosphere(input_dir)
    if df.empty:
        print("No atmosphere data to process.")
        return df
    df = normalize_columns(df)
    df = parse_timestamps(df)
    df = merge_with_stations(df)
    df = validate_pbl(df)
    if output_path:
        save_processed(df, output_path)
    print(f"Atmosphere processing complete: {len(df)} rows, {df.shape[1]} columns")
    return df
