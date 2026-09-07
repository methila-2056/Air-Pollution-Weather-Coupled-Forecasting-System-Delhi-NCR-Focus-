"""Stubble-burning fire impact scoring for AeroCast-NCR.

Computes per-station, per-time-step fire impact features using
geographic proximity, FRP intensity, and wind alignment.

For each station-time pair:
  - fire_count: Number of fires within 500km radius
  - fire_impact_score: Normalized weighted sum (0-1)
  - nearest_fire_distance: Distance to closest fire in km
  - wind_aligned_fire_count: Count of fires that are upwind
"""

import math
from typing import Optional

import numpy as np
import pandas as pd


DELHI_CENTER_LAT = 28.6139
DELHI_CENTER_LON = 77.2090
EARTH_RADIUS_KM = 6371.0
DEFAULT_MAX_DISTANCE_KM = 500.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in km between two lat/lon points."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def _angle_between(station_lat: float, station_lon: float,
                   fire_lat: float, fire_lon: float) -> float:
    """Compute bearing angle (degrees) from fire to station.

    Returns angle in degrees [0, 360).
    """
    dlon = math.radians(fire_lon - station_lon)
    lat1_r = math.radians(station_lat)
    lat2_r = math.radians(fire_lat)
    y = math.sin(dlon) * math.cos(lat2_r)
    x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360


def _normalize_impact(raw_score: float, k: float = 1.0, mid: float = 1.0) -> float:
    """Normalize a raw weighted fire impact score into [0, 1].

    Uses a logistic-style mapping so that a typical values land in the
    mid range while extreme strong impacts approach 1.0.

    Args:
        raw_score: Sum of frp * cos(angle) / distance over contributing fires.
        k: Steepness of the curve.
        mid: Raw score value that maps to ~0.5.

    Returns:
        Normalized score in [0, 1].
    """
    if raw_score <= 0:
        return 0.0
    normalized = 1.0 / (1.0 + math.exp(-k * (raw_score - mid)))
    return min(1.0, max(0.0, normalized))


def _is_upwind(fire_lat: float, fire_lon: float,
               station_lat: float, station_lon: float,
               wind_dir: float) -> bool:
    """Check if a fire is upwind of the station.

    Wind direction is where wind blows FROM (meteorological convention).
    A fire is upwind if it lies in the direction the wind is coming from.
    """
    bearing = _angle_between(station_lat, station_lon, fire_lat, fire_lon)
    diff = abs(bearing - wind_dir)
    if diff > 180:
        diff = 360 - diff
    return diff <= 90


def compute_fire_impact(
    fires_df: pd.DataFrame,
    station_lat: float,
    station_lon: float,
    wind_dir: float,
    wind_speed: float,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
) -> dict:
    """Compute fire impact metrics for a single station-time point.

    Args:
        fires_df: DataFrame of fire observations (with lat, lon, frp columns).
        station_lat: Station latitude.
        station_lon: Station longitude.
        wind_dir: Meteorological wind direction in degrees (FROM direction).
        wind_speed: Wind speed in m/s.
        max_distance_km: Maximum fire radius to consider.

    Returns:
        Dictionary with keys: fire_count, fire_impact_score,
        nearest_fire_distance, wind_aligned_fire_count.
    """
    result = {
        "fire_count": 0,
        "fire_impact_score": 0.0,
        "nearest_fire_distance": max_distance_km + 1.0,
        "wind_aligned_fire_count": 0,
    }

    if fires_df is None or fires_df.empty:
        return result

    scores = []
    min_dist = float("inf")
    aligned_count = 0

    for _, fire in fires_df.iterrows():
        f_lat = fire.get("lat")
        f_lon = fire.get("lon")
        if pd.isna(f_lat) or pd.isna(f_lon):
            continue

        dist = haversine_distance(station_lat, station_lon, f_lat, f_lon)
        if dist > max_distance_km:
            continue

        if dist < min_dist:
            min_dist = dist

        frp = fire.get("frp", 1.0)
        if pd.isna(frp) or frp <= 0:
            frp = 1.0

        bearing = _angle_between(station_lat, station_lon, f_lat, f_lon)
        angle_diff = abs(bearing - wind_dir)
        if angle_diff > 180:
            angle_diff = 360 - angle_diff
        alignment = math.cos(math.radians(angle_diff))

        weight = (frp * max(alignment, 0.0)) / (dist + 1.0)
        scores.append(weight)

        if _is_upwind(f_lat, f_lon, station_lat, station_lon, wind_dir):
            aligned_count += 1

    count = len(scores)
    result["fire_count"] = count
    result["nearest_fire_distance"] = min_dist if min_dist < float("inf") else max_distance_km + 1.0
    result["wind_aligned_fire_count"] = aligned_count

    if count > 0:
        raw_score = sum(scores)
        result["fire_impact_score"] = _normalize_impact(raw_score)
    else:
        result["fire_impact_score"] = 0.0

    return result


def add_fire_features(
    df: pd.DataFrame,
    fires_df: Optional[pd.DataFrame] = None,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
) -> pd.DataFrame:
    """Add fire impact features to the main dataframe.

    For each row in df, computes fire impact using fires that occurred
    within +/-1 hour of the observation timestamp.

    Args:
        df: Main dataframe with station, timestamp, wind_direction, wind_speed.
        fires_df: Fire dataframe with acq_timestamp/acq_date, lat, lon, frp.
        max_distance_km: Maximum fire radius for consideration.

    Returns:
        DataFrame with added fire feature columns.
    """
    df = df.copy()

    df["fire_count"] = 0
    df["fire_impact_score"] = 0.0
    df["nearest_fire_distance"] = max_distance_km + 1.0
    df["wind_aligned_fire_count"] = 0

    if fires_df is None or fires_df.empty:
        return df

    fires = fires_df.copy()
    ts_col = "acq_timestamp" if "acq_timestamp" in fires.columns else "acq_date"
    if ts_col in fires.columns:
        fires[ts_col] = pd.to_datetime(fires[ts_col], utc=True, errors="coerce")
        fires.dropna(subset=[ts_col], inplace=True)
    else:
        return df

    if "timestamp" not in df.columns:
        return df

    df_ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    fire_ts = fires[ts_col]

    for idx in df.index:
        row_ts = df_ts.loc[idx]
        if pd.isna(row_ts):
            continue

        time_mask = (fire_ts >= row_ts - pd.Timedelta(hours=1)) & (fire_ts <= row_ts + pd.Timedelta(hours=1))
        nearby_fires = fires[time_mask]

        if nearby_fires.empty:
            continue

        station_lat = df.loc[idx, "latitude"] if "latitude" in df.columns else DELHI_CENTER_LAT
        station_lon = df.loc[idx, "longitude"] if "longitude" in df.columns else DELHI_CENTER_LON
        wind_dir = df.loc[idx, "wind_direction"] if "wind_direction" in df.columns else 0.0
        wind_spd = df.loc[idx, "wind_speed"] if "wind_speed" in df.columns else 0.0

        if pd.isna(station_lat) or pd.isna(station_lon):
            station_lat = DELHI_CENTER_LAT
            station_lon = DELHI_CENTER_LON
        if pd.isna(wind_dir):
            wind_dir = 0.0
        if pd.isna(wind_spd):
            wind_spd = 0.0

        impact = compute_fire_impact(nearby_fires, station_lat, station_lon, wind_dir, wind_spd, max_distance_km)
        df.loc[idx, "fire_count"] = impact["fire_count"]
        df.loc[idx, "fire_impact_score"] = impact["fire_impact_score"]
        df.loc[idx, "nearest_fire_distance"] = impact["nearest_fire_distance"]
        df.loc[idx, "wind_aligned_fire_count"] = impact["wind_aligned_fire_count"]

    return df
