import csv
import io
from datetime import UTC, datetime, timedelta

from app.models.db_models import PollutionReading, Station, WeatherReading


def _anand_id(db_session):
    from app.models.db_models import Station
    return db_session.query(Station).filter(Station.name == "Anand Vihar").first().id


def _weather_csv(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "station", "time", "temperature_2m", "relative_humidity_2m", "pressure_msl",
        "surface_pressure", "wind_speed_10m", "wind_direction_10m", "precipitation",
        "cloud_cover", "boundary_layer_height",
    ])
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _pollution_csv(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "station", "timestamp", "pm25", "pm10", "o3", "no2", "so2", "co", "aqi",
    ])
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("") if v is None else v for k, v in row.items()})
    return buf.getvalue()


def _old_ts(hours_back: int) -> str:
    base = datetime.now(UTC).replace(tzinfo=None).replace(minute=0, second=0, microsecond=0)
    return (base - timedelta(hours=hours_back)).strftime("%Y-%m-%d %H:%M:%S")


def test_export_weather_csv(client, db_session):
    response = client.get("/api/export/weather.csv")
    assert response.status_code == 422  # station_name is required

    response = client.get("/api/export/weather.csv", params={"station_name": "Anand Vihar", "hours": 72})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "content-disposition" in response.headers
    lines = response.text.splitlines()
    assert lines[0].startswith("station,time,temperature_2m")
    assert len(lines) >= 13  # header + 12 seeded rows
    assert lines[1].startswith("Anand Vihar,")


def test_export_pollution_csv(client, db_session):
    response = client.get("/api/export/pollution.csv", params={"station_name": "Anand Vihar", "hours": 72})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.splitlines()
    assert lines[0] == "station,timestamp,pm25,pm10,o3,no2,so2,co,aqi"
    assert len(lines) >= 13
    first = lines[1].split(",")
    assert first[0] == "Anand Vihar"
    assert float(first[2]) > 0  # pm25


def test_export_unknown_station_404(client, db_session):
    response = client.get("/api/export/weather.csv", params={"station_name": "No Such Station", "hours": 72})
    assert response.status_code == 404


def test_import_weather_inserts_and_is_idempotent(client, db_session):
    payload = _weather_csv([
        {"station": "Anand Vihar", "time": _old_ts(30), "temperature_2m": "11.5", "relative_humidity_2m": "88",
         "pressure_msl": "1014.2", "surface_pressure": "994.0", "wind_speed_10m": "3.1",
         "wind_direction_10m": "210", "precipitation": "0.0", "cloud_cover": "65", "boundary_layer_height": "180"},
        {"station": "Anand Vihar", "time": _old_ts(31), "temperature_2m": "11.0", "relative_humidity_2m": "89",
         "pressure_msl": "1014.0", "surface_pressure": "993.8", "wind_speed_10m": "2.9",
         "wind_direction_10m": "205", "precipitation": "0.0", "cloud_cover": "60", "boundary_layer_height": "170"},
        {"station": "RK Puram", "time": _old_ts(30), "temperature_2m": "12.0", "relative_humidity_2m": "70",
         "pressure_msl": "1013.0", "surface_pressure": "992.0", "wind_speed_10m": "4.0",
         "wind_direction_10m": "180", "precipitation": "0.0", "cloud_cover": "10", "boundary_layer_height": "500"},
    ])

    first = client.post("/api/import/weather", content=payload, headers={"Content-Type": "text/csv"})
    assert first.status_code == 200, first.text
    summary = first.json()
    assert summary["dataset"] == "weather"
    assert summary["rows"] == 3
    assert summary["inserted"] == 3
    assert summary["updated"] == 0
    assert summary["unchanged"] == 0
    assert summary["unknown_stations"] == []

    second = client.post("/api/import/weather", content=payload, headers={"Content-Type": "text/csv"})
    assert second.status_code == 200
    replayed = second.json()
    assert replayed["inserted"] == 0
    assert replayed["updated"] == 0
    assert replayed["unchanged"] == 3

    anand_count = db_session.query(WeatherReading).filter(WeatherReading.station_id == _anand_id(db_session), WeatherReading.wind_speed == 3.1).count()
    assert anand_count == 1


def test_import_pollution_computes_aqi_and_respects_provided(client, db_session):
    payload = _pollution_csv([
        {"station": "Anand Vihar", "timestamp": _old_ts(30), "pm25": "120", "pm10": "220", "o3": "60",
         "no2": "90", "so2": "18", "co": "2.4", "aqi": None},
        {"station": "ITO", "timestamp": _old_ts(30), "pm25": "80", "pm10": "", "o3": "", "no2": "",
         "so2": "", "co": "", "aqi": "199"},
    ])

    first = client.post("/api/import/pollution", content=payload, headers={"Content-Type": "text/csv"})
    assert first.status_code == 200, first.text
    summary = first.json()
    assert summary["dataset"] == "pollution"
    assert summary["inserted"] == 2
    assert summary["unknown_stations"] == []

    anand_ts = datetime.strptime(_old_ts(30), "%Y-%m-%d %H:%M:%S")
    anand = db_session.query(PollutionReading).filter(
        PollutionReading.station_id == _anand_id(db_session),
        PollutionReading.timestamp == anand_ts,
    ).first()
    assert anand is not None
    assert anand.pm25 == 120.0
    assert anand.aqi is not None and anand.aqi > 0  # computed from pollutants

    ipo_id = db_session.query(Station).filter(Station.name == "ITO").first().id
    ipo = db_session.query(PollutionReading).filter(
        PollutionReading.station_id == ipo_id,
        PollutionReading.timestamp == anand_ts,
    ).first()
    assert ipo is not None and ipo.aqi == 199  # provided value kept

    second = client.post("/api/import/pollution", content=payload, headers={"Content-Type": "text/csv"})
    assert second.status_code == 200
    replayed = second.json()
    assert replayed["inserted"] == 0
    assert replayed["unchanged"] == 2


def test_import_skips_unknown_stations(client, db_session):
    payload = _weather_csv([
        {"station": "Seemapuri (not curated)", "time": _old_ts(10), "temperature_2m": "20",
         "relative_humidity_2m": "40", "pressure_msl": "", "surface_pressure": "",
         "wind_speed_10m": "", "wind_direction_10m": "", "precipitation": "", "cloud_cover": "", "boundary_layer_height": ""},
        {"station": "Anand Vihar", "time": _old_ts(30), "temperature_2m": "21", "relative_humidity_2m": "41",
         "pressure_msl": "", "surface_pressure": "", "wind_speed_10m": "", "wind_direction_10m": "",
         "precipitation": "", "cloud_cover": "", "boundary_layer_height": ""},
    ])
    response = client.post("/api/import/weather", content=payload, headers={"Content-Type": "text/csv"})
    assert response.status_code == 200
    summary = response.json()
    assert summary["inserted"] == 1
    assert summary["unknown_stations"] == ["Seemapuri (not curated)"]
    assert summary["rows"] == 2


def test_import_weather_bad_timestamp_reported(client, db_session):
    payload = _weather_csv([
        {"station": "Anand Vihar", "time": "not-a-date", "temperature_2m": "20", "relative_humidity_2m": "40",
         "pressure_msl": "", "surface_pressure": "", "wind_speed_10m": "", "wind_direction_10m": "",
         "precipitation": "", "cloud_cover": "", "boundary_layer_height": ""},
    ])
    response = client.post("/api/import/weather", content=payload, headers={"Content-Type": "text/csv"})
    assert response.status_code == 200
    summary = response.json()
    assert summary["inserted"] == 0
    assert len(summary["errors"]) == 1
    assert "unparsable timestamp" in summary["errors"][0]


def test_import_validation_errors(client, db_session):
    no_station = client.post("/api/import/weather", content="time,temperature_2m\n2024-01-01 00:00:00,10",
                             headers={"Content-Type": "text/csv"})
    assert no_station.status_code == 400
    assert "station" in no_station.json()["detail"]

    no_rows = client.post("/api/import/weather", content="station,time\n", headers={"Content-Type": "text/csv"})
    assert no_rows.status_code == 400
    assert "no data rows" in no_rows.json()["detail"]


def test_export_import_roundtrip_is_unchanged(client, db_session):
    exported = client.get("/api/export/weather.csv", params={"station_name": "Anand Vihar", "hours": 24})
    assert exported.status_code == 200
    imported = client.post("/api/import/weather", content=exported.text, headers={"Content-Type": "text/csv"})
    assert imported.status_code == 200, imported.text
    summary = imported.json()
    assert summary["inserted"] == 0
    assert summary["updated"] == 0
    assert summary["unchanged"] >= 12

    pollution_export = client.get("/api/export/pollution.csv", params={"station_name": "Anand Vihar", "hours": 24})
    assert pollution_export.status_code == 200
    reimport = client.post("/api/import/pollution", content=pollution_export.text, headers={"Content-Type": "text/csv"})
    assert reimport.status_code == 200, reimport.text
    ps = reimport.json()
    assert ps["inserted"] == 0
    assert ps["updated"] == 0
    assert ps["unchanged"] >= 12
