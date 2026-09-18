"""Pollution 17/17-coverage tests (WS-1): aliases, coverage endpoint, pooled fallback."""

from datetime import UTC, datetime, timedelta

from app.database import DEFAULT_STATIONS
from app.models.db_models import PollutionReading, Station
from app.services import cpcb_service, forecast_service


def station_by_name(db, name: str) -> Station:
    return db.query(Station).filter(Station.name == name).first()


def test_aliases_cover_all_17_curated_stations():
    for spec in DEFAULT_STATIONS:
        canonical = cpcb_service._canonical_station_name(spec["name"])
        assert canonical == spec["name"], f"{spec['name']!r} does not round-trip (-> {canonical!r})"


def _annotation(raw: str, city: str) -> str:
    """Mirror normalize_records: short-name strip, then canonical alias."""
    return cpcb_service._canonical_station_name(cpcb_service._short_station_name(raw, city))


def test_alias_mapping_for_17th_station_monitors():
    cases = {
        ("Teri Gram", "Gurugram"): "Teri Gram",
        ("Vikas Sadan, Gurugram - HSPCB", "Gurugram"): "Teri Gram",
        ("Sector - 62, Noida - UPPCB", "Noida"): "Noida Sector-62",
        ("Sector 62, Noida - UPPCB", "Noida"): "Noida Sector-62",
        ("Sector 11", "Faridabad"): "Faridabad",
        ("Sector 11, Faridabad - HSPCB", "Faridabad"): "Faridabad",
        ("IMD Lodhi Road", "Delhi"): "Lodhi Road",
        ("Dwarka-Sector 8", "Delhi"): "Dwarka",
        ("Anand Vihar, Delhi - DPCC", "Delhi"): "Anand Vihar",
    }
    for (raw, city), expected in cases.items():
        assert _annotation(raw, city) == expected, f"{raw!r} -> {_annotation(raw, city)!r}"


def test_coverage_endpoint_reports_seeded_db(client, db_session):
    resp = client.get("/api/pollution/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stations_total"] == len(DEFAULT_STATIONS)
    assert body["stations_with_readings"] >= 1
    by_name = {s["station"]: s for s in body["stations"]}
    anand = by_name["Anand Vihar"]
    assert anand["readings"] >= 1
    assert anand["last_timestamp"] is not None
    assert "data_gov_in" in anand["sources"] or anand["sources"]  # sources present


def test_pooled_features_for_sparse_station(db_session):
    # Seed DB only has real readings for Anand Vihar; every other station is
    # sparse/empty, so pooling against the regional core must engage.
    sparse = station_by_name(db_session, "Mundka")
    sparse_id = sparse.id
    # Give Mundka a tiny amount of local history so the local path engages.
    base = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    db_session.add(PollutionReading(station_id=sparse_id, timestamp=base, pm25=120.0, pm10=210.0, aqi=200))
    db_session.commit()

    spark = db_session.query(PollutionReading).filter(PollutionReading.station_id == sparse_id).count()
    assert spark < forecast_service.SPARSE_READINGS_THRESHOLD

    features, meta = forecast_service.build_features_from_db_with_meta(db_session, sparse_id)
    assert meta["pooled"] is True
    assert "Anand Vihar" in meta["composite_sources"]
    assert features["pm25_lag1"] > 0, "pooled features must carry real regional signal"


def test_non_sparse_station_is_not_pooled(db_session):
    # A station with abundant local history must stay local (not pooled).
    anand = station_by_name(db_session, "Anand Vihar")
    base = datetime.now(UTC).replace(tzinfo=None)
    for i in range(forecast_service.SPARSE_READINGS_THRESHOLD + 10):
        ts = base - timedelta(hours=i)
        db_session.add(PollutionReading(station_id=anand.id, timestamp=ts,
                                        pm25=100.0, pm10=200.0, o3=50.0,
                                        no2=40.0, so2=15.0, co=1.5, aqi=150))
    db_session.commit()
    features, meta = forecast_service.build_features_from_db_with_meta(db_session, anand.id)
    assert meta["pooled"] is False
    assert len(features) > 10
