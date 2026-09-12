"""Shared helpers for unit tests of the PM2.5 pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd

TINY_XGB = {
    "n_estimators": 10,
    "max_depth": 2,
    "learning_rate": 0.3,
    "tree_method": "hist",
    "verbosity": 0,
    "n_jobs": 1,
}


def _make_synthetic_df(n_stations: int = 3, n_hours: int = 720) -> pd.DataFrame:
    """Deterministic hourly PM2.5 panel with the engineered feature columns."""
    stations = [f"S{chr(65 + i)}" for i in range(n_stations)]
    rng = np.random.default_rng(42)
    frames = []
    for si, name in enumerate(stations):
        t = np.arange(n_hours)
        base_ts = pd.Timestamp("2024-01-01")
        ts = base_ts + pd.to_timedelta(
            pd.Series(t * 3600 * 1) + si * 3600 * 24, unit="s"
        )
        pm25 = (
            80
            + 60 * np.sin(2 * np.pi * t / 24)
            + 20 * np.sin(2 * np.pi * t / 168)
            + rng.normal(0, 8, n_hours)
        ).clip(5, 950)
        hour = ts.dt.hour
        temp = 22 + 10 * np.sin(2 * np.pi * (t % 24) / 24) + rng.normal(0, 1, n_hours)
        wind = (3 + 2 * np.sin(2 * np.pi * t / 24)).clip(0.1, None)
        wdir = 180 + 90 * np.sin(2 * np.pi * t / 24)
        pbl = (500 + 400 * np.sin(2 * np.pi * ((t + 12) % 24) / 24)).clip(100, 2000)
        df = pd.DataFrame({
            "station": name,
            "timestamp": ts,
            "hour": ts.dt.floor("h"),
            "pm25": np.round(pm25, 2),
            "temperature": np.round(temp, 2),
            "humidity": np.full(n_hours, 62.0),
            "pressure_msl": np.full(n_hours, 1013.0),
            "surface_pressure": np.full(n_hours, 993.0),
            "wind_speed": np.round(wind, 2),
            "wind_direction": np.round(wdir, 1),
            "wind_dir_sin": np.sin(np.deg2rad(wdir)),
            "wind_dir_cos": np.cos(np.deg2rad(wdir)),
            "pbl_height": np.round(pbl, 1),
            "ventilation_coefficient": np.round(wind * pbl, 1),
            "inversion_detected": (pbl < 400).astype(int),
            "inversion_strength": np.round(np.clip(1 - pbl / 2000, 0, 1), 3),
            "fire_count": np.zeros(n_hours, dtype=int),
            "fire_impact_score": np.zeros(n_hours),
            "nearest_fire_distance": np.full(n_hours, 501.0),
            "wind_aligned_fire_count": np.zeros(n_hours, dtype=int),
            "wind_alignment_pct": np.zeros(n_hours),
            "transport_time_hours": np.full(n_hours, np.nan),
            "transport_risk": np.zeros(n_hours),
            "stubble_impact_score": np.zeros(n_hours),
            "hour_of_day": hour,
            "day_of_week": ts.dt.dayofweek,
            "month": ts.dt.month,
            "day_of_year": ts.dt.dayofyear,
            "is_weekend": (ts.dt.dayofweek >= 5).astype(int),
            "hour_sin": np.sin(2 * np.pi * hour / 24),
            "hour_cos": np.cos(2 * np.pi * hour / 24),
            "dayofweek_sin": np.sin(2 * np.pi * ts.dt.dayofweek / 7),
            "dayofweek_cos": np.cos(2 * np.pi * ts.dt.dayofweek / 7),
            "month_sin": np.sin(2 * np.pi * ts.dt.month / 12),
            "month_cos": np.cos(2 * np.pi * ts.dt.month / 12),
        })
        df["pm25_lag1"] = df["pm25"].shift(1)
        df["pm25_lag3"] = df["pm25"].shift(3)
        df["pm25_lag6"] = df["pm25"].shift(6)
        df["pm25_lag12"] = df["pm25"].shift(12)
        df["pm25_lag24"] = df["pm25"].shift(24)
        for w in (3, 6, 12, 24):
            df[f"pm25_roll_mean_{w}h"] = df["pm25"].shift(1).rolling(w, min_periods=1).mean()
            df[f"pm25_roll_std_{w}h"] = df["pm25"].shift(1).rolling(w, min_periods=2).std()
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["hour", "station"]).reset_index(drop=True)
    n = len(out)
    labels = np.concatenate([
        np.full(int(round(n * 0.60)), "train"),
        np.full(int(round(n * 0.20)), "validation"),
        np.full(n - int(round(n * 0.60)) - int(round(n * 0.20)), "test"),
    ])
    out["split"] = labels
    return out
