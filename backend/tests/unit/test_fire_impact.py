"""Unit tests for stubble-fire impact geometry (SIH26082 PS #3 fire source)."""

import numpy as np
import pandas as pd
import pytest

from ml.features.fire_impact import (
    DEFAULT_MAX_DISTANCE_KM,
    add_fire_features,
    compute_fire_impact,
    haversine_distance,
)

DELHI_LAT, DELHI_LON = 28.6139, 77.2090


def _fires():
    return pd.DataFrame([
        {"lat": 30.5, "lon": 76.1, "frp": 100.0},   # north-west (upwind for dir 0)
        {"lat": 28.0, "lon": 74.6, "frp": 40.0},    # south-west
        {"lat": 28.0, "lon": 79.0, "frp": 250.0},   # far east
    ])


class TestHaversine:
    def test_zero_distance_for_same_point(self):
        assert haversine_distance(DELHI_LAT, DELHI_LON, DELHI_LAT, DELHI_LON) == pytest.approx(0.0)

    def test_delhi_mumbai_distance(self):
        d = haversine_distance(DELHI_LAT, DELHI_LON, 19.0760, 72.8777)
        assert 1100.0 < d < 1200.0


class TestComputeFireImpact:
    def test_empty_fires_return_zero(self):
        impact = compute_fire_impact(pd.DataFrame(), DELHI_LAT, DELHI_LON, 0.0, 2.0)
        assert impact["fire_count"] == 0
        assert impact["fire_impact_score"] == 0.0
        assert impact["wind_aligned_fire_count"] == 0

    def test_fires_beyond_radius_excluded(self):
        far = pd.DataFrame([{"lat": 21.0, "lon": 60.0, "frp": 999.0}])
        impact = compute_fire_impact(far, DELHI_LAT, DELHI_LON, 0.0, 2.0)
        assert impact["fire_count"] == 0

    def test_upwind_fire_counted_when_wind_from_north(self):
        impact = compute_fire_impact(_fires(), DELHI_LAT, DELHI_LON, wind_dir=0.0, wind_speed=2.0)
        assert impact["fire_count"] == 3
        assert impact["wind_aligned_fire_count"] >= 1
        assert 0.0 <= impact["fire_impact_score"] <= 1.0

    def test_impact_score_increases_with_frp(self):
        low = compute_fire_impact(_fires(), DELHI_LAT, DELHI_LON, 0.0, 2.0)["fire_impact_score"]
        boosted = _fires().copy()
        boosted["frp"] *= 10
        high = compute_fire_impact(boosted, DELHI_LAT, DELHI_LON, 0.0, 2.0)["fire_impact_score"]
        assert high >= low


class TestAddFireFeatures:
    def test_no_fires_preserves_zero_columns(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-11-01", periods=2, freq="1h", tz="UTC"),
            "latitude": [DELHI_LAT] * 2,
            "longitude": [DELHI_LON] * 2,
            "wind_direction": [0.0] * 2,
            "wind_speed": [2.0] * 2,
        })
        out = add_fire_features(df, fires_df=None)
        assert (out["fire_count"] == 0).all()
        assert (out["fire_impact_score"] == 0.0).all()

    def test_fires_within_window_are_applied(self):
        ts = pd.Timestamp("2025-11-01 12:00:00", tz="UTC")
        df = pd.DataFrame({
            "timestamp": [ts],
            "latitude": [DELHI_LAT],
            "longitude": [DELHI_LON],
            "wind_direction": [0.0],
            "wind_speed": [2.0],
        })
        fires = pd.DataFrame([
            {"acq_date": ts, "lat": 30.0, "lon": 76.5, "frp": 150.0},
            {"acq_date": ts + pd.Timedelta(hours=3), "lat": 29.0, "lon": 77.0, "frp": 80.0},
        ])
        out = add_fire_features(df, fires_df=fires)
        assert out.loc[0, "fire_count"] == 1  # only the in-window fire
        assert out.loc[0, "fire_impact_score"] > 0.0