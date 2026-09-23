"""Regression tests for the naive-vs-aware datetime merge crash.

PostgreSQL returns ``DateTime(timezone=True)`` columns as tz-aware datetimes
while SQLite returns naive, and the regional composite is always naive UTC.
Merging the two raised ``ValueError`` on the Postgres path (production 500 on
pooled / data-sparse stations). These tests pin the normalisation.
"""

import pandas as pd
from app.services import forecast_service as fs

NAIVE_HOURS = ["2026-09-12 00:00:00", "2026-09-12 01:00:00", "2026-09-12 02:00:00"]


def test_as_naive_utc_converts_aware_to_naive():
    series = pd.Series(pd.to_datetime(NAIVE_HOURS, utc=True))
    assert series.dt.tz is not None

    out = fs._as_naive_utc(series)
    assert out.dt.tz is None
    assert list(out.dt.strftime("%Y-%m-%d %H:%M:%S")) == NAIVE_HOURS


def test_as_naive_utc_leaves_naive_wall_clock_unchanged():
    series = pd.Series(pd.to_datetime(NAIVE_HOURS))
    out = fs._as_naive_utc(series)
    assert out.dt.tz is None
    assert list(out.dt.strftime("%Y-%m-%d %H:%M:%S")) == NAIVE_HOURS


def test_merge_history_frames_accepts_mixed_tz_dtypes():
    # The exact production crash: naive-UTC composite pollution frame +
    # tz-aware weather frame (fresh from PostgreSQL).
    poll = pd.DataFrame({"timestamp": pd.to_datetime(NAIVE_HOURS), "pm25": [100.0, 110.0, 120.0]})
    wx = pd.DataFrame(
        {"timestamp": pd.to_datetime(NAIVE_HOURS, utc=True), "temperature": [20.0, 19.5, 19.0]}
    )

    combined = fs._merge_history_frames(poll, wx)

    assert {"pm25", "temperature"} <= set(combined.columns)
    assert combined["timestamp"].dt.tz is None
    assert pd.api.types.is_numeric_dtype(combined["pm25"])
    assert len(combined) == len(NAIVE_HOURS)


def test_merge_history_frames_joins_on_matching_stamps():
    poll = pd.DataFrame(
        {"timestamp": pd.to_datetime(["2026-09-12 00:00:00", "2026-09-12 02:00:00"]), "pm25": [100.0, 120.0]}
    )
    wx = pd.DataFrame(
        {"timestamp": pd.to_datetime(["2026-09-12 00:00:00", "2026-09-12 01:00:00"], utc=True), "temperature": [20.0, 19.5]}
    )

    combined = fs._merge_history_frames(poll, wx)

    assert len(combined) == 3  # outer join: all three stamps
    row = combined.set_index("timestamp").loc["2026-09-12 00:00:00"]
    assert row["pm25"] == 100.0
    assert row["temperature"] == 20.0
