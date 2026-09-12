"""Unit tests for the NASA FIRMS integration (network I/O mocked)."""

from datetime import UTC, datetime
from unittest import mock

import pandas as pd
from app.models.db_models import FireReading
from app.services import firms_service as fs


class FakeResp:
    def __init__(self, text="", ok=True, status_code=200):
        self.text = text
        self.ok = ok
        self.status_code = status_code

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


_CORE_CSV = (
    "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,instrument,daynight\n"
)


def _csv(*rows: str) -> str:
    return _CORE_CSV + "".join(rows)


class TestParseAcqTime:
    def test_normal_hhmm(self):
        ts = fs._parse_acq_time({"acq_date": "2026-09-07", "acq_time": 1231})
        assert ts == pd.Timestamp("2026-09-07 12:31:00")

    def test_2400_rolls_to_next_day(self):
        ts = fs._parse_acq_time({"acq_date": "2026-09-07", "acq_time": 2400})
        assert ts == pd.Timestamp("2026-09-08 00:00:00")

    def test_9999_uses_date_midnight(self):
        ts = fs._parse_acq_time({"acq_date": "2026-09-07", "acq_time": 9999})
        assert ts == pd.Timestamp("2026-09-07 00:00:00")

    def test_empty_time_uses_date_midnight(self):
        ts = fs._parse_acq_time({"acq_date": "2026-09-07", "acq_time": ""})
        assert ts == pd.Timestamp("2026-09-07 00:00:00")

    def test_bad_date_returns_none(self):
        assert fs._parse_acq_time({"acq_date": "not-a-date", "acq_time": 1000}) is None
        assert fs._parse_acq_time({"acq_date": "", "acq_time": 1000}) is None


class TestNormalise:
    def test_drops_invalid_and_out_of_region(self):
        df = pd.DataFrame([
            {"latitude": 30.5, "longitude": 76.1, "acq_date": "2026-09-07",
             "acq_time": 1000, "confidence": "high", "frp": 90.0, "satellite": "SNPP", "daynight": "D"},
            {"latitude": 20.0, "longitude": 80.0, "acq_date": "2026-09-07",
             "acq_time": 1000, "confidence": "low", "frp": 5.0, "satellite": "SNPP", "daynight": "D"},
            {"latitude": 999.0, "longitude": 76.1, "acq_date": "2026-09-07",
             "acq_time": 1000, "confidence": "low", "frp": 5.0, "satellite": "SNPP", "daynight": "D"},
            {"latitude": 30.5, "longitude": 76.1, "acq_date": "bad-date",
             "acq_time": 1000, "confidence": "low", "frp": 5.0, "satellite": "SNPP", "daynight": "D"},
        ])
        records = fs.normalise_fire_records(df)
        assert len(records) == 1
        assert records[0]["acq_date"] == pd.Timestamp("2026-09-07 10:00:00").to_pydatetime()

    def test_rounds_coords_and_normalises_confidence_instrument(self):
        df = pd.DataFrame([
            {"latitude": 30.55555, "longitude": 76.11117, "acq_date": "2026-09-07",
             "acq_time": 900, "confidence": " LOW ", "frp": 90.0,
             "satellite": "Aqua", "instrument": "MODIS", "daynight": "D"},
        ])
        records = fs.normalise_fire_records(df)
        assert records[0]["latitude"] == 30.5556
        assert records[0]["longitude"] == 76.1112
        assert records[0]["confidence"] == "low"
        assert records[0]["instrument"] == "MODIS"

    def test_brightness_prefers_ti4_then_t31(self):
        both = pd.DataFrame([{"latitude": 30.5, "longitude": 76.1, "acq_date": "2026-09-07",
                              "acq_time": 1000, "confidence": "high", "satellite": "SNPP",
                              "bright_ti4": 310.2, "bright_t31": 300.1, "daynight": "D"}])
        assert fs.normalise_fire_records(both)[0]["brightness"] == 310.2
        only_modis = both.copy()
        only_modis["bright_ti4"] = None
        only_modis["bright_t31"] = [299.5]
        assert fs.normalise_fire_records(only_modis)[0]["brightness"] == 299.5

    def test_instrument_inferred_from_satellite_when_absent(self):
        df = pd.DataFrame([{"latitude": 30.5, "longitude": 76.1, "acq_date": "2026-09-07",
                            "acq_time": 1000, "confidence": "high", "satellite": "Terra", "daynight": "D"}])
        assert fs.normalise_fire_records(df)[0]["instrument"] == "MODIS"


class TestFetch:
    def test_public_csv_fallback_when_no_key(self):
        csv_text = _csv(
            "30.5,76.1,2026-09-07,1000,high,90.0,SNPP,VIIRS,D\n"
            "29.0,75.0,2026-09-07,1000,high,90.0,SNPP,VIIRS,D\n"
        )
        with mock.patch.object(fs.requests, "get", return_value=FakeResp(text=csv_text)):
            records, source = fs.fetch_fire_records(api_key="")
        assert "public 24h CSV" in source
        assert len(records) == 2

    def test_api_path_when_key_present(self):
        csv_text = _csv("30.5,76.1,2026-09-07,1000,high,90.0,SNPP,VIIRS,D\n")

        def fake_get(url, **kwargs):
            assert "/api/area/csv/" in url
            assert url.split("/")[-1] == fs.region_area()
            return FakeResp(text=csv_text)

        with mock.patch.object(fs.requests, "get", side_effect=fake_get):
            records, source = fs.fetch_fire_records(api_key="test-key", days=7)
        assert "area API" in source
        assert len(records) == 1

    def test_api_empty_falls_back_to_public(self):
        public = _csv("30.5,76.1,2026-09-07,1000,high,90.0,SNPP,VIIRS,D\n")
        seen = []

        def fake_get(url, **kwargs):
            if "api/area/csv" in url:
                return FakeResp(text="")  # API returns nothing -> fallback
            seen.append(url)
            return FakeResp(text=public)

        with mock.patch.object(fs.requests, "get", side_effect=fake_get):
            records, source = fs.fetch_fire_records(api_key="test-key")
        assert "public 24h CSV" in source
        assert len(records) == 1
        assert len(seen) == 2  # both public CSVs attempted

    def test_dedupes_within_batch(self):
        csv_text = _csv(
            "30.5,76.1,2026-09-07,1000,high,90.0,SNPP,VIIRS,D\n"
            "30.5,76.1,2026-09-07,1000,high,90.0,SNPP,VIIRS,D\n"
            "30.5,76.1,2026-09-07,1000,low,20.0,Aqua,MODIS,D\n"
        )
        with mock.patch.object(fs.requests, "get", return_value=FakeResp(text=csv_text)):
            records, _ = fs.fetch_fire_records(api_key="")
        assert len(records) == 2


class TestUpsert:
    def test_inserts_new_and_skips_stored(self, db_session):
        seeded = (
            db_session.query(FireReading)
            .filter(FireReading.latitude == 30.5, FireReading.longitude == 76.1)
            .first()
        )
        records = [
            {"satellite": "SNPP", "instrument": "VIIRS", "latitude": 30.5,
             "longitude": 76.1, "acq_date": seeded.acq_date, "confidence": "high",
             "frp": 90.0, "brightness": 310.0, "daynight": "D"},
            {"satellite": "SNPP", "instrument": "VIIRS", "latitude": 29.0,
             "longitude": 75.0, "acq_date": seeded.acq_date - pd.Timedelta(hours=1),
             "confidence": "nominal", "frp": 50.0, "brightness": None, "daynight": "D"},
        ]
        result = fs.upsert_fire_records(db_session, records, dry_run=False)
        assert result["retrieved"] == 2
        assert result["inserted"] == 1
        assert result["duplicates_skipped"] == 1
        stored = db_session.query(FireReading).filter(
            FireReading.latitude == 29.0, FireReading.longitude == 75.0
        ).count()
        assert stored == 1

    def test_dry_run_does_not_write(self, db_session):
        records = [
            {"satellite": "SNPP", "instrument": "VIIRS", "latitude": 29.0,
             "longitude": 75.0, "acq_date": datetime(2026, 9, 7, 10, 0, 0),
             "confidence": "nominal", "frp": 50.0, "brightness": None, "daynight": "D"},
        ]
        before = db_session.query(FireReading).count()
        fs.upsert_fire_records(db_session, records, dry_run=True)
        assert db_session.query(FireReading).count() == before

    def test_empty_records_returns_zeros(self, db_session):
        assert fs.upsert_fire_records(db_session, []) == {
            "retrieved": 0, "inserted": 0, "duplicates_skipped": 0,
        }


class TestToNaiveUtc:
    def test_strips_tzinfo_toward_utc(self):
        aware = datetime(2026, 9, 7, 12, 0, 0, tzinfo=datetime.now().astimezone().tzinfo)
        assert fs.to_naive_utc(aware) == aware.astimezone(UTC).replace(tzinfo=None)

    def test_keeps_naive_and_none(self):
        assert fs.to_naive_utc(None) is None
        naive = datetime(2026, 9, 7, 12, 0, 0)
        assert fs.to_naive_utc(naive) == naive
