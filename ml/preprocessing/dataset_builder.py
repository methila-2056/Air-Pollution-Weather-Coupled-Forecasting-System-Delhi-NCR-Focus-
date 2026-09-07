"""Coupled dataset builder for AeroCast-NCR.

Loads all processed data sources, merges on timestamp + station,
forward-fills gaps up to 3 hours, drops rows with >3 consecutive NaN,
and produces the final coupled training dataset.
"""

import os
from typing import Optional

import numpy as np
import pandas as pd

from .pollution_processor import process_pollution, POLLUTANT_RANGES
from .weather_processor import process_weather
from .fire_processor import process_fire, haversine_distance
from .atmosphere_processor import process_atmosphere

FINAL_SCHEMA = [
    "timestamp", "station", "latitude", "longitude",
    "pm25", "pm10", "o3", "no2", "so2", "co", "aqi",
    "temperature", "humidity", "pressure_msl", "surface_pressure",
    "wind_speed", "wind_direction", "precipitation", "cloud_cover",
    "pbl_height",
    "fire_count", "fire_frp", "nearest_fire_distance",
]


def merge_pollution_weather(
    pollution: pd.DataFrame, weather: pd.DataFrame
) -> pd.DataFrame:
    """Merge pollution and weather data on timestamp + station."""
    if weather.empty:
        return pollution
    merge_cols = ["timestamp", "station"]
    available = [c for c in merge_cols if c in pollution.columns and c in weather.columns]
    if len(available) < 2:
        merge_cols = ["timestamp"]
        available = [c for c in merge_cols if c in pollution.columns and c in weather.columns]
    if not available:
        return pollution
    weather_dedup = weather.drop_duplicates(subset=[c for c in available if c in weather.columns], keep="last")
    merged = pd.merge(
        pollution, weather_dedup, on=available, how="left", suffixes=("", "_wx")
    )
    return merged


def merge_fire_aggregates(merged: pd.DataFrame, fires: pd.DataFrame) -> pd.DataFrame:
    """Compute fire aggregates per station-hour and merge."""
    if fires.empty:
        merged["fire_count"] = 0
        merged["fire_frp"] = 0.0
        merged["nearest_fire_distance"] = 9999.0
        return merged

    if "acq_timestamp" not in fires.columns and "acq_date" in fires.columns:
        fires = fires.copy()
        fires.rename(columns={"acq_date": "acq_timestamp"}, inplace=True)

    if "acq_timestamp" not in fires.columns:
        merged["fire_count"] = 0
        merged["fire_frp"] = 0.0
        merged["nearest_fire_distance"] = 9999.0
        return merged

    fires = fires.copy()
    fires["acq_timestamp"] = pd.to_datetime(fires["acq_timestamp"], utc=True, errors="coerce")
    fires.dropna(subset=["acq_timestamp"], inplace=True)
    fires["fire_hour"] = fires["acq_timestamp"].dt.floor("h")

    merged = merged.copy()
    merged["fire_count"] = 0
    merged["fire_frp"] = 0.0
    merged["nearest_fire_distance"] = 9999.0

    station_coords = {}
    if "station" in merged.columns and "latitude" in merged.columns:
        for _, row in merged[["station", "latitude", "longitude"]].dropna().drop_duplicates().iterrows():
            station_coords[row["station"]] = (row["latitude"], row["longitude"])

    has_lat_lon = "lat" in fires.columns and "lon" in fires.columns
    has_frp = "frp" in fires.columns

    unique_hours = merged["timestamp"].dropna().unique()
    for hour in unique_hours:
        hour_fires = fires[fires["fire_hour"] == hour]
        if hour_fires.empty:
            continue
        mask = merged["timestamp"] == hour
        if "station" in merged.columns:
            for station in merged.loc[mask, "station"].unique():
                if station not in station_coords:
                    continue
                s_lat, s_lon = station_coords[station]
                s_mask = mask & (merged["station"] == station)
                if has_lat_lon:
                    dists = hour_fires.apply(
                        lambda r: haversine_distance(s_lat, s_lon, r["lat"], r["lon"]),
                        axis=1,
                    )
                    within_500 = dists <= 500
                    count = int(within_500.sum())
                    frp_sum = float(hour_fires.loc[within_500, "frp"].sum()) if has_frp and count > 0 else 0.0
                    min_dist = float(dists.min()) if len(dists) > 0 else 9999.0
                else:
                    count = len(hour_fires)
                    frp_sum = float(hour_fires["frp"].sum()) if has_frp else 0.0
                    min_dist = 9999.0
                merged.loc[s_mask, "fire_count"] = count
                merged.loc[s_mask, "fire_frp"] = frp_sum
                merged.loc[s_mask, "nearest_fire_distance"] = min_dist
        else:
            if has_lat_lon:
                dists = hour_fires.apply(
                    lambda r: haversine_distance(
                        merged.loc[mask, "latitude"].mean(),
                        merged.loc[mask, "longitude"].mean(),
                        r["lat"], r["lon"],
                    ),
                    axis=1,
                )
                within_500 = dists <= 500
                count = int(within_500.sum())
                frp_sum = float(hour_fires.loc[within_500, "frp"].sum()) if has_frp and count > 0 else 0.0
                min_dist = float(dists.min()) if len(dists) > 0 else 9999.0
            else:
                count = len(hour_fires)
                frp_sum = float(hour_fires["frp"].sum()) if has_frp else 0.0
                min_dist = 9999.0
            merged.loc[mask, "fire_count"] = count
            merged.loc[mask, "fire_frp"] = frp_sum
            merged.loc[mask, "nearest_fire_distance"] = min_dist

    return merged


def merge_atmosphere(merged: pd.DataFrame, atmosphere: pd.DataFrame) -> pd.DataFrame:
    """Merge atmosphere/PBL data onto the merged dataset."""
    if atmosphere.empty:
        return merged
    merge_cols = []
    for col in ["timestamp", "station"]:
        if col in merged.columns and col in atmosphere.columns:
            merge_cols.append(col)
    if not merge_cols:
        return merged
    atm_dedup = atmosphere.drop_duplicates(subset=merge_cols, keep="last")
    atm_cols_to_merge = [c for c in ["pbl_height"] if c in atmosphere.columns]
    if not atm_cols_to_merge:
        return merged
    merge_keys = [c for c in merge_cols if c in atmosphere.columns]
    atm_subset = atmosphere[merge_keys + atm_cols_to_merge].copy()
    merged = pd.merge(merged, atm_subset, on=merge_keys, how="left", suffixes=("", "_atm"))
    return merged


def forward_fill_gaps(df: pd.DataFrame, max_gap_hours: int = 3) -> pd.DataFrame:
    """Forward-fill missing values up to max_gap_hours per station."""
    df = df.copy()
    if "station" in df.columns:
        grouped = df.groupby("station")
        for col in df.columns:
            if col in ["timestamp", "station"]:
                continue
            df[col] = grouped[col].transform(lambda x: x.ffill(limit=max_gap_hours))
    else:
        for col in df.columns:
            if col in ["timestamp", "station"]:
                continue
            df[col] = df[col].ffill(limit=max_gap_hours)
    return df


def drop_heavy_nan_rows(df: pd.DataFrame, max_consecutive: int = 3) -> pd.DataFrame:
    """Drop rows where more than max_consecutive NaN appear in key columns."""
    df = df.copy()
    key_cols = [c for c in FINAL_SCHEMA if c in df.columns and c not in ["timestamp", "station"]]
    if not key_cols:
        return df
    nan_count_per_row = df[key_cols].isna().sum(axis=1)
    threshold = len(key_cols) * 0.5
    df = df[nan_count_per_row <= threshold].copy()
    df.reset_index(drop=True, inplace=True)
    return df


def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the dataframe has all columns in FINAL_SCHEMA."""
    df = df.copy()
    for col in FINAL_SCHEMA:
        if col not in df.columns:
            df[col] = np.nan
    return df[FINAL_SCHEMA]


def build_coupled_dataset(
    pollution: pd.DataFrame,
    weather: pd.DataFrame,
    fire: pd.DataFrame,
    atmosphere: pd.DataFrame,
) -> pd.DataFrame:
    """Build the coupled dataset from all data sources."""
    print("Merging pollution + weather ...")
    merged = merge_pollution_weather(pollution, weather)
    print(f"  After merge: {len(merged)} rows")

    print("Computing fire aggregates ...")
    merged = merge_fire_aggregates(merged, fire)
    print(f"  After fire merge: {len(merged)} rows")

    print("Merging atmosphere/PBL data ...")
    merged = merge_atmosphere(merged, atmosphere)
    print(f"  After atmosphere merge: {len(merged)} rows")

    print("Forward-filling gaps (max 3 hours) ...")
    merged = forward_fill_gaps(merged, max_gap_hours=3)

    print("Dropping rows with heavy NaN ...")
    before = len(merged)
    merged = drop_heavy_nan_rows(merged)
    print(f"  Dropped {before - len(merged)} rows")

    merged = ensure_schema(merged)
    return merged


def print_statistics(df: pd.DataFrame) -> None:
    """Print dataset statistics."""
    print("\n=== Coupled Dataset Statistics ===")
    print(f"Total rows: {len(df)}")
    print(f"Total columns: {len(df.columns)}")
    if "station" in df.columns:
        print(f"Stations: {df['station'].nunique()}")
        print(f"  {df['station'].value_counts().to_dict()}")
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        print(f"Time range: {ts.min()} to {ts.max()}")
    numeric_cols = [c for c in df.columns if c not in ["timestamp", "station", "outlier_flags", "weather_outlier_flags"]]
    print(f"\nNumeric column statistics:")
    for col in numeric_cols[:15]:
        if col in df.columns and df[col].notna().any():
            print(f"  {col}: mean={df[col].mean():.2f}, std={df[col].std():.2f}, "
                  f"min={df[col].min():.2f}, max={df[col].max():.2f}, "
                  f"missing={df[col].isna().sum()} ({100 * df[col].isna().mean():.1f}%)")
    print(f"\nNaN summary:")
    for col in df.columns:
        n = df[col].isna().sum()
        if n > 0:
            print(f"  {col}: {n} ({100 * n / len(df):.1f}%)")
    print("==================================\n")


def process_and_build(
    raw_dir: str,
    output_path: Optional[str] = None,
) -> pd.DataFrame:
    """End-to-end: process each source, build coupled dataset, save."""
    print("=" * 60)
    print("AeroCast-NCR Coupled Dataset Builder")
    print("=" * 60)

    print("\n[1/4] Processing pollution data ...")
    pollution = process_pollution(input_dir=os.path.join(raw_dir, "pollution"))
    print(f"  Pollution: {len(pollution)} rows")

    print("\n[2/4] Processing weather data ...")
    weather = process_weather(input_dir=os.path.join(raw_dir, "weather"))
    print(f"  Weather: {len(weather)} rows")

    print("\n[3/4] Processing fire data ...")
    fire = process_fire(input_dir=os.path.join(raw_dir, "fire"))
    print(f"  Fire: {len(fire)} rows")

    print("\n[4/4] Processing atmosphere data ...")
    atmosphere = process_atmosphere(input_dir=os.path.join(raw_dir, "atmosphere"))
    print(f"  Atmosphere: {len(atmosphere)} rows")

    print("\nBuilding coupled dataset ...")
    dataset = build_coupled_dataset(pollution, weather, fire, atmosphere)

    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "processed", "coupled_dataset.csv"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    dataset.to_csv(output_path, index=False)
    print(f"\nSaved coupled dataset to {output_path}")

    print_statistics(dataset)
    return dataset
