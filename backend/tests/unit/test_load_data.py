"""Unit tests for the chunked, memory-safe demo dataset loaders.

Regression guard for the OOM crash-loop fix: ``load_coupled_data`` /
``load_fire_data`` must stream the CSV in chunks and insert in batches (so a
512 MB free-tier Render instance can hydrate without being killed), dedupe on a
second run, and never hand back fabricated rows.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
from app.models.db_models import FireReading, PollutionReading, WeatherReading

from backend.scripts.load_data import load_coupled_data, load_fire_data


def _coupled_csv(path, station="Anand Vihar", n=5):
    base = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=5)
    hours = [(base + timedelta(hours=i)).isoformat() for i in range(n)]
    rows = {
        "timestamp": hours,
        "temperature_2m": [22.0] * n,
        "relative_humidity_2m": [61.0] * n,
        "pressure_msl": [1013.0] * n,
        "surface_pressure": [993.0] * n,
        "wind_speed_10m": [1.5] * n,
        "wind_direction_10m": [315.0] * n,
        "precipitation": [0.0] * n,
        "cloud_cover": [40.0] * n,
        "boundary_layer_height": [180.0] * n,
        "station": [station] * n,
        "latitude": [28.6492] * n,
        "longitude": [77.2918] * n,
        "pm25": [120.0] * n,
        "pm10": [200.0] * n,
        "no2": [60.0] * n,
        "o3": [40.0] * n,
        "so2": [10.0] * n,
        "co": [2.0] * n,
    }
    pd.DataFrame(rows).to_csv(path, index=False)


def _fire_csv(path, n=3):
    rows = {
        "latitude": [30.1, 30.2, 30.3][:n],
        "longitude": [76.1, 76.2, 76.3][:n],
        "acq_date": ["2026-09-18", "2026-09-18", "2026-09-18"][:n],
        "acq_time": [300, 400, 500][:n],
        "confidence": ["high", "nominal", "low"][:n],
        "frp": [90.0, 40.0, 18.0][:n],
        "satellite": ["SNPP", "SNPP", "SNPP"][:n],
        "daynight": ["D", "D", "N"][:n],
    }
    pd.DataFrame(rows).to_csv(path, index=False)


def _pollution_count(db_session):
    return db_session.query(PollutionReading).count()


def _weather_count(db_session):
    return db_session.query(WeatherReading).count()


class TestLoadCoupledDataChunked:
    def test_inserts_all_rows_across_chunks(self, db_session, tmp_path):
        csv_path = tmp_path / "coupled.csv"
        _coupled_csv(csv_path, n=5)
        p0, w0 = _pollution_count(db_session), _weather_count(db_session)

        counts = load_coupled_data(db_session, csv_path, chunksize=2)

        assert counts == {"pollution": 5, "weather": 5}
        assert _pollution_count(db_session) == p0 + 5
        assert _weather_count(db_session) == w0 + 5

    def test_idempotent_on_second_run(self, db_session, tmp_path):
        csv_path = tmp_path / "coupled.csv"
        _coupled_csv(csv_path, n=5)
        load_coupled_data(db_session, csv_path, chunksize=2)
        p1, w1 = _pollution_count(db_session), _weather_count(db_session)
        load_coupled_data(db_session, csv_path, chunksize=2)
        assert _pollution_count(db_session) == p1
        assert _weather_count(db_session) == w1

    def test_chunk_boundaries_do_not_duplicate(self, db_session, tmp_path):
        csv_path = tmp_path / "coupled.csv"
        _coupled_csv(csv_path, n=7)
        counts = load_coupled_data(db_session, csv_path, chunksize=3)
        assert counts == {"pollution": 7, "weather": 7}

    def test_intra_chunk_duplicates_insert_once(self, db_session, tmp_path):
        base = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=5)
        csv_path = tmp_path / "coupled.csv"
        stamps = [(base + timedelta(hours=i)).isoformat() for i in range(7)]
        rows = [
            {
                "timestamp": stamp,
                "temperature_2m": 22.0,
                "relative_humidity_2m": 61.0,
                "pressure_msl": 1013.0,
                "surface_pressure": 993.0,
                "wind_speed_10m": 1.5,
                "wind_direction_10m": 315.0,
                "precipitation": 0.0,
                "cloud_cover": 40.0,
                "boundary_layer_height": 180.0,
                "station": "Anand Vihar",
                "latitude": 28.6492,
                "longitude": 77.2918,
                "pm25": 120.0,
                "pm10": 200.0,
                "no2": 60.0,
                "o3": 40.0,
                "so2": 10.0,
                "co": 2.0,
            }
            for stamp in stamps
        ]
        rows.append({**rows[1], "pm25": 175.0})
        pd.DataFrame(rows).to_csv(csv_path, index=False)

        p0, w0 = _pollution_count(db_session), _weather_count(db_session)
        load_coupled_data(db_session, csv_path, chunksize=2)
        assert _pollution_count(db_session) == p0 + 7
        assert _weather_count(db_session) == w0 + 7


class TestLoadFireDataChunked:
    def test_inserts_all_rows(self, db_session, tmp_path):
        csv_path = tmp_path / "fires.csv"
        _fire_csv(csv_path, n=3)
        before = db_session.query(FireReading).count()
        assert load_fire_data(db_session, csv_path, chunksize=2) == 3
        assert db_session.query(FireReading).count() == before + 3

    def test_idempotent_on_second_run(self, db_session, tmp_path):
        csv_path = tmp_path / "fires.csv"
        _fire_csv(csv_path, n=3)
        load_fire_data(db_session, csv_path, chunksize=2)
        after_first = db_session.query(FireReading).count()
        load_fire_data(db_session, csv_path, chunksize=2)
        assert db_session.query(FireReading).count() == after_first

    def test_missing_file_is_empty(self, db_session, tmp_path):
        assert load_fire_data(db_session, tmp_path / "nope.csv") == 0
