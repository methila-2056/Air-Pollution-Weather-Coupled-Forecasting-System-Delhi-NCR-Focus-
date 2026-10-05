"""Unit tests for the live-data refresh service (all network I/O mocked)."""

from datetime import UTC, datetime, timedelta
from unittest import mock

import pandas as pd
from app.database import DEFAULT_STATIONS
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


def _fresh_hourly(times, repeats=False):
    stamps = list(times)
    if repeats:
        stamps.append(stamps[0])
    return _hourly_at(stamps)


def _hourly_at(times):
    """Build an Open-Meteo-shaped hourly frame for explicit datetimes."""
    n = len(times)
    return {
        "time": [t.strftime("%Y-%m-%dT%H:%M") for t in times],
        "temperature_2m": [22.0] * n,
        "relative_humidity_2m": [61.0] * n,
        "pressure_msl": [1013.0] * n,
        "surface_pressure": [993.0] * n,
        "wind_speed_10m": [1.5] * n,
        "wind_direction_10m": [315.0] * n,
        "precipitation": [0.0] * n,
        "cloud_cover": [40.0] * n,
        "boundary_layer_height": [180.0] * n,
    }


def _ckan_records(timestamp, pm25=120.0):
    """Build CKAN datastore records using the real feed's ``Timestamp`` field.

    ``opencity.in`` publishes the CPCB "Delhi Hourly Air Quality Reports"
    package with a naive, offset-free ``Timestamp`` column in IST wall-clock.
    """
    return [
        {
            "Timestamp": timestamp,
            "PM2.5 (ug/m3)": pm25,
            "PM10 (ug/m3)": 200.0,
            "NO2 (ug/m3)": 90.0,
            "SO2 (ug/m3)": 16.0,
            "CO (mg/m3)": 2.0,
            "Ozone (ug/m3)": 55.0,
        }
    ]


def _hour_floor():
    """Current UTC wall-clock truncated to the hour (always <= real now)."""
    return datetime.now(UTC).replace(tzinfo=None, minute=0, second=0, microsecond=0)


def _past_hours(n, offset=24):
    """Hours safely in the past and outside the seeded 12-hour fixture window.

    ``conftest`` seeds ``base_utc - 0..11h``, so past hours used by these tests
    start a full day back to avoid colliding with the fixture.
    """
    base = _hour_floor()
    return [base - timedelta(hours=offset + i) for i in range(n)]


def _future_hours(n):
    base = _hour_floor()
    return [base + timedelta(hours=1 + i) for i in range(n)]


def _weather_timestamps(session):
    return {r.timestamp for r in session.query(WeatherReading).all()}


def _pollution_timestamps(session, station_name):
    station = _stations(session)[station_name]
    return {
        r.timestamp
        for r in session.query(PollutionReading)
        .filter(PollutionReading.station_id == station.id)
        .all()
    }


def _stations(session):
    return {s.name: s for s in session.query(Station).all()}


NUM_STATIONS = len(DEFAULT_STATIONS)  # DEFAULT_STATIONS in app.database
NUM_POLLUTION_STATIONS = len(rs.CKAN_RESOURCES)  # pollution feeds cover the original monitors


class TestRefreshWeather:
    def test_upserts_and_dedups_within_batch(self, db_session):
        # Historical hours: `refresh_weather` only persists analysis hours at or
        # before the captured `now`, so a fixture built from future hours would
        # be filtered out rather than stored.
        past = _past_hours(2)
        hourly = _fresh_hourly(past, repeats=True)  # 3 rows, 2 unique per station
        with mock.patch.object(rs.requests, "get", return_value=FakeResp(json_data={"hourly": hourly})):
            count = rs.refresh_weather(db_session)
        assert count == NUM_STATIONS * 2

        station = _stations(db_session)["Anand Vihar"]
        present = {
            r.timestamp for r in db_session.query(WeatherReading).filter(
                WeatherReading.station_id == station.id
            ).all()
        }
        assert past[0] in present
        assert past[1] in present

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
        hourly = _fresh_hourly(_past_hours(2))
        resp = FakeResp(json_data={"hourly": hourly})
        with mock.patch.object(rs.requests, "get", return_value=resp):
            first = rs.refresh_weather(db_session)
            second = rs.refresh_weather(db_session)
        assert first == NUM_STATIONS * 2
        assert second == 0  # every timestamp already stored

    def test_drops_future_hours_from_observations(self, db_session):
        """Hours that have not occurred yet must never enter weather_observations.

        The Open-Meteo *archive* API returns the complete current day when
        ``end_date`` is today, including hours still in the future. Those hours
        carry model output, not observations, so storing them misrepresents
        forecast values as measurements.
        """
        past = _past_hours(2)
        future = _future_hours(2)
        frame = _hourly_at(past + future)

        with mock.patch.object(rs.requests, "get", return_value=FakeResp(json_data={"hourly": frame})):
            count = rs.refresh_weather(db_session)

        stored = _weather_timestamps(db_session)
        assert count == NUM_STATIONS * len(past)
        for ts in past:
            assert ts in stored
        for ts in future:
            assert ts not in stored

    def test_retains_valid_past_hours(self, db_session):
        """The future filter must not discard legitimate past analysis hours."""
        past = _past_hours(3)
        frame = _hourly_at(past)

        with mock.patch.object(rs.requests, "get", return_value=FakeResp(json_data={"hourly": frame})):
            count = rs.refresh_weather(db_session)

        stored = _weather_timestamps(db_session)
        assert count == NUM_STATIONS * len(past)
        for ts in past:
            assert ts in stored

    def test_archive_failure_never_stores_forecast_values(self, db_session):
        """If the archive is unavailable the service must fail closed.

        The archive-failure fallback returns Open-Meteo *forecast* hours, which
        span now..now+48h. Those are model output for un-observed instants, so
        they cannot be persisted as observations. The refresh must write
        nothing at all rather than store forecast values.
        """
        forecast_frame = _hourly_at(_future_hours(4))

        def fake_get(url, **kwargs):
            if url == rs.ARCHIVE_URL:
                return FakeResp(ok=False, status_code=503)
            return FakeResp(json_data={"hourly": forecast_frame})

        before = _weather_timestamps(db_session)
        with mock.patch.object(rs.requests, "get", side_effect=fake_get):
            count = rs.refresh_weather(db_session)
        after = _weather_timestamps(db_session)

        assert count == 0
        assert after == before


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
        records = [{
            # naive IST wall-clock, as the CKAN feed publishes it
            "datetime": "2024-03-01 09:00:00",
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
        assert count == NUM_POLLUTION_STATIONS

        station = _stations(db_session)["Anand Vihar"]
        # 2024-03-01 09:00 IST == 2024-03-01 03:30 UTC. Select the ingested row by
        # its converted instant rather than by recency, so the assertion targets
        # this record instead of whichever seeded row happens to be newest.
        row = (
            db_session.query(PollutionReading)
            .filter(
                PollutionReading.station_id == station.id,
                PollutionReading.timestamp == datetime(2024, 3, 1, 3, 30),
            )
            .one()
        )
        assert row.pm25 == 120.0
        assert row.aqi is not None and row.aqi > 0

    def test_localizes_naive_ist_pollution_to_naive_utc(self, db_session):
        """The CKAN feed publishes naive IST; store it as naive UTC.

        ``opencity.in`` returns ``Timestamp`` with no offset, in IST
        wall-clock. This application persists naive UTC, so the IST wall-clock
        must be localized to Asia/Kolkata and converted, not stored verbatim.
        Storing it verbatim shifts every reading 5 h 30 m into the future.
        """
        resp = FakeResp(json_data={"result": {"records": _ckan_records("2024-01-01T00:15:00")}})
        with mock.patch.object(rs.requests, "get", return_value=resp):
            count = rs.refresh_pollution(db_session)
        assert count == NUM_POLLUTION_STATIONS

        stored = _pollution_timestamps(db_session, "Anand Vihar")
        # 2024-01-01 00:15 IST == 2023-12-31 18:45 UTC
        assert datetime(2023, 12, 31, 18, 45) in stored
        # the un-converted IST wall-clock must never reach a naive-UTC column
        assert datetime(2024, 1, 1, 0, 15) not in stored

    def test_converts_aware_pollution_offset_before_stripping(self, db_session):
        """An aware +05:30 timestamp must be converted, not merely stripped.

        Dropping the tzinfo without converting keeps IST wall-clock under a UTC
        contract. Conversion must agree with the naive-IST case above.
        """
        resp = FakeResp(
            json_data={"result": {"records": _ckan_records("2024-01-01T00:15:00+05:30")}}
        )
        with mock.patch.object(rs.requests, "get", return_value=resp):
            count = rs.refresh_pollution(db_session)
        assert count == NUM_POLLUTION_STATIONS

        stored = _pollution_timestamps(db_session, "Anand Vihar")
        # conversion must agree with the naive-IST case, not merely drop +05:30
        assert datetime(2023, 12, 31, 18, 45) in stored
        assert datetime(2024, 1, 1, 0, 15) not in stored


class TestRunRefreshOnce:
    def test_dry_run_reports_summary_without_writing(self, db_session):
        hourly = _fresh_hourly(_past_hours(1))
        fire_csv = (
            "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,daynight\n"
            "29.0,75.0,2026-09-07,1000,nominal,50.0,SNPP,D\n"
        )
        pollution_records = [{
            # naive IST wall-clock, as the CKAN feed publishes it
            "datetime": "2024-03-01 09:00:00",
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
        assert summary["pollution"] == NUM_POLLUTION_STATIONS

        assert db_session.query(WeatherReading).count() == weather_before
        assert db_session.query(FireReading).count() == fire_before
        assert db_session.query(PollutionReading).count() == pollution_before
