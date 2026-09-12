"""Unit tests for the live-data refresh service (all network I/O mocked)."""

from datetime import datetime, timedelta
from unittest import mock

import pandas as pd
from app.models.db_models import (
    FireReading,
    PollutionReading,
    Station,
    WeatherReading,
)
from app.services import refresh_service as rs


class FakeResp:
    def __init__(self, json_data=None, text="", ok=True, status_code=200):
        self._json = json_data
        self.text = text
        self.ok = ok
        self.status_code = status_code

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


def _fresh_hourly(base, n=2, repeats=False):
    times = [(base + timedelta(hours=i + 1)).strftime("%Y-%m-%dT%H:%M") for i in range(n)]
    if repeats:
        times.append(times[0])
    n_times = len(times)
    return {
        "time": times,
        "temperature_2m": [22.0] * n_times,
        "relative_humidity_2m": [61.0] * n_times,
        "pressure_msl": [1013.0] * n_times,
        "surface_pressure": [993.0] * n_times,
        "wind_speed_10m": [1.5] * n_times,
        "wind_direction_10m": [315.0] * n_times,
        "precipitation": [0.0] * n_times,
        "cloud_cover": [40.0] * n_times,
        "boundary_layer_height": [180.0] * n_times,
    }


def _stations(session):
    return {s.name: s for s in session.query(Station).all()}


NUM_STATIONS = 5  # DEFAULT_STATIONS in app.database


class TestRefreshWeather:
    def test_upserts_and_dedups_within_batch(self, db_session):
        base = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        hourly = _fresh_hourly(base, n=2, repeats=True)  # 3 timestamps, 2 unique per station
        with mock.patch.object(rs.requests, "get", return_value=FakeResp(json_data={"hourly": hourly})):
            count = rs.refresh_weather(db_session)
        assert count == NUM_STATIONS * 2

        station = _stations(db_session)["Anand Vihar"]
        present = {
            r.timestamp for r in db_session.query(WeatherReading).filter(
                WeatherReading.station_id == station.id
            ).all()
        }
        assert (base + timedelta(hours=1)) in present
        assert (base + timedelta(hours=2)) in present

    def test_timestamps_normalized_to_naive_utc(self, db_session):
        # Simulate a raw response that carries an explicit +05:30 offset (older
        # Asia/Kolkata fetch). The service must request UTC and normalise stored
        # datetimes to naive UTC (no tzinfo, wall clock == UTC).
        hourly = {
            "time": ["2026-09-12T05:30:00+05:30", "2026-09-12T06:30:00+05:30"],
            "temperature_2m": [27.3, 27.2],
            "relative_humidity_2m": [90.0, 91.0],
            "pressure_msl": [1009.5, 1009.9],
            "surface_pressure": [989.0, 989.4],
            "wind_speed_10m": [6.4, 7.8],
            "wind_direction_10m": [72.0, 61.0],
            "precipitation": [0.3, 0.3],
            "cloud_cover": [40.0, 40.0],
            "boundary_layer_height": [245.0, 285.0],
        }
        with mock.patch.object(rs.requests, "get", return_value=FakeResp(json_data={"hourly": hourly})) as mocker:
            df = rs._get_weather_df("Anand_Vihar", 28.6492, 77.2918, "2026-09-01", "2026-09-13")

        # open-meteo was called with timezone=UTC
        args, kwargs = mocker.call_args
        assert kwargs["params"]["timezone"] == "UTC"

        times = pd.to_datetime(df["time"]).tolist() if not df.empty else []
        assert times == [pd.Timestamp("2026-09-12 00:00:00"), pd.Timestamp("2026-09-12 01:00:00")]
        assert all(t.tzinfo is None for t in times)  # naive UTC by convention

    def test_second_batch_does_not_duplicate(self, db_session):
        base = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        hourly = _fresh_hourly(base, n=2)
        resp = FakeResp(json_data={"hourly": hourly})
        with mock.patch.object(rs.requests, "get", return_value=resp):
            first = rs.refresh_weather(db_session)
            second = rs.refresh_weather(db_session)
        assert first == NUM_STATIONS * 2
        assert second == 0  # every timestamp already stored


class TestRefreshFire:
    def test_filters_to_region_and_dedups(self, db_session):
        seeded = (
            db_session.query(FireReading)
            .filter(FireReading.latitude == 30.5, FireReading.longitude == 76.1)
            .first()
        )
        # Re-emit the seeded hotspot with its exact acquisition time so the
        # dedup key (satellite, lat, lon, acq_time) matches and it is skipped.
        dup_date = seeded.acq_date.strftime("%Y-%m-%d")
        dup_time = seeded.acq_date.strftime("%H%M")
        csv_text = (
            "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,daynight\n"
            f"30.5,76.1,{dup_date},{dup_time},high,90.0,SNPP,D\n"     # duplicate of seed
            "29.0,75.0,2026-09-07,1000,nominal,50.0,SNPP,D\n"          # in-region, new
            "20.0,80.0,2026-09-07,0900,low,5.0,SNPP,D\n"               # outside region
        )
        with mock.patch.object(rs.requests, "get", return_value=FakeResp(text=csv_text)):
            count = rs.refresh_fire(db_session)
        assert count == 1

        keys = {(r.latitude, r.longitude) for r in db_session.query(FireReading).all()}
        assert (29.0, 75.0) in keys
        assert (20.0, 80.0) not in keys

    def test_empty_region_returns_zero(self, db_session):
        csv_text = (
            "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,daynight\n"
            "20.0,80.0,2026-09-07,0900,low,5.0,SNPP,D\n"
        )
        with mock.patch.object(rs.requests, "get", return_value=FakeResp(text=csv_text)):
            count = rs.refresh_fire(db_session)
        assert count == 0


class TestRefreshPollution:
    def test_upserts_reading_with_aqi(self, db_session):
        base = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        records = [{
            "datetime": (base + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "site": "Anand Vihar",
            "PM2.5 (ug/m3)": 120.0,
            "PM10 (ug/m3)": 200.0,
            "NO2 (ug/m3)": 90.0,
            "SO2 (ug/m3)": 16.0,
            "CO (mg/m3)": 2.0,
            "Ozone (ug/m3)": 55.0,
        }]
        resp = FakeResp(json_data={"result": {"records": records}})
        with mock.patch.object(rs.requests, "get", return_value=resp):
            count = rs.refresh_pollution(db_session)
        assert count == NUM_STATIONS

        station = _stations(db_session)["Anand Vihar"]
        row = (
            db_session.query(PollutionReading)
            .filter(PollutionReading.station_id == station.id)
            .order_by(PollutionReading.timestamp.desc())
            .first()
        )
        assert row.pm25 == 120.0
        assert row.aqi is not None and row.aqi > 0


class TestRunRefreshOnce:
    def test_dry_run_reports_summary_without_writing(self, db_session):
        base = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        hourly = _fresh_hourly(base, n=1)
        fire_csv = (
            "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,daynight\n"
            "29.0,75.0,2026-09-07,1000,nominal,50.0,SNPP,D\n"
        )
        pollution_records = [{
            "datetime": (base + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "site": "Anand Vihar",
            "PM2.5 (ug/m3)": 120.0,
            "PM10 (ug/m3)": 200.0,
            "NO2 (ug/m3)": 90.0,
            "SO2 (ug/m3)": 16.0,
            "CO (mg/m3)": 2.0,
            "Ozone (ug/m3)": 55.0,
        }]

        def fake_get(url, **kwargs):
            if url == rs.ARCHIVE_URL:
                return FakeResp(json_data={"hourly": hourly})
            if url == rs.FIRMS_CSV:
                return FakeResp(text=fire_csv)
            return FakeResp(json_data={"result": {"records": pollution_records}})

        weather_before = db_session.query(WeatherReading).count()
        fire_before = db_session.query(FireReading).count()
        pollution_before = db_session.query(PollutionReading).count()

        with mock.patch.object(rs.requests, "get", side_effect=fake_get):
            summary = rs.run_refresh_once(db_session, dry_run=True)

        assert set(summary) == {"weather", "fire", "pollution"}
        assert summary["weather"] == NUM_STATIONS
        assert summary["fire"] == 1
        assert summary["pollution"] == NUM_STATIONS

        assert db_session.query(WeatherReading).count() == weather_before
        assert db_session.query(FireReading).count() == fire_before
        assert db_session.query(PollutionReading).count() == pollution_before
