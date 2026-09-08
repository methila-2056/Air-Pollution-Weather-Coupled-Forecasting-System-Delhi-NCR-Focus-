"""Live data refresh service for AeroCast-NCR.

Fetches the latest weather (Open-Meteo), active fires (NASA FIRMS public CSV),
and CPCB pollution (opencity.in CKAN) readings and upserts them into the
backend database so forecasts always run on the most recent observations.
"""

import asyncio
import logging
from datetime import datetime, timedelta

import pandas as pd
import requests

logger = logging.getLogger("aerocast.refresh")

STATIONS = {
    "Anand_Vihar": (28.6492, 77.2918),
    "RK_Puram": (28.5601, 77.1835),
    "ITO": (28.6290, 77.2410),
    "Dwarka": (28.5921, 77.0460),
    "Punjabi_Bagh": (28.6692, 77.1285),
}

REGION = {"min_lon": 73.5, "min_lat": 27.5, "max_lon": 78.5, "max_lat": 33.0}

FIRMS_CSV = (
    "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2"
    "/csv/SUOMI_VIIRS_C2_Global_24h.csv"
)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CKAN_BASE = "https://data.opencity.in/api/3/action/datastore_search"
CKAN_RESOURCES = {
    "Anand_Vihar": "5ef3f66f-2bb0-4593-91db-ba6e693a77f3",
    "RK_Puram": "d9dfd28d-038d-448f-8e33-5e6f6b32d15c",
    "ITO": "890f786d-fb9f-475e-8516-191bfa1b01ea",
    "Dwarka": "495db3d4-5683-4b1d-9b7d-34ecb887ca13",
    "Punjabi_Bagh": "82080ddc-e094-4a3a-8421-242ec6bc8a45",
}

HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,pressure_msl,surface_pressure,"
    "wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,"
    "boundary_layer_height"
)

DEFAULT_LOOKBACK_DAYS = 3
HTTP_TIMEOUT = 60


def _to_float(v):
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _existing_timestamps(db, model_cls, station_id) -> set:
    return {
        ts
        for (ts,) in db.query(model_cls.timestamp)
        .filter(model_cls.station_id == station_id)
        .all()
    }


def _get_weather_df(station_name: str, lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "hourly": HOURLY_VARS,
        "timezone": "Asia/Kolkata",
    }
    try:
        resp = requests.get(ARCHIVE_URL, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        # Age out gracefully: fall back to forecast API for the next ~48h
        logger.warning("archive fetch failed (%s) — trying forecast", exc)
        f_params = {
            "latitude": lat,
            "longitude": lon,
            "forecast_days": 2,
            "hourly": "temperature_2m,relative_humidity_2m,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,boundary_layer_height",
            "timezone": "Asia/Kolkata",
        }
        resp = requests.get(FORECAST_URL, params=f_params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    hourly = data.get("hourly", {})
    if not hourly or "time" not in hourly:
        return pd.DataFrame()
    df = pd.DataFrame(hourly)
    df["time"] = pd.to_datetime(df["time"])
    raw_to_display = {
        "Anand_Vihar": "Anand Vihar",
        "RK_Puram": "RK Puram",
        "Punjabi_Bagh": "Punjabi Bagh",
    }
    df["station"] = raw_to_display.get(station_name, station_name.replace("_", " "))
    df["latitude"] = lat
    df["longitude"] = lon
    return df


def refresh_weather(db, dry_run: bool = False) -> int:
    """Upsert recent Open-Meteo weather readings; returns inserted row count."""
    from ..models.db_models import Station, WeatherReading

    stations = {s.name: s for s in db.query(Station).all()}
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    inserted = 0
    for raw_name, (lat, lon) in STATIONS.items():
        display = {
            "Anand_Vihar": "Anand Vihar",
            "RK_Puram": "RK Puram",
            "ITO": "ITO",
            "Dwarka": "Dwarka",
            "Punjabi_Bagh": "Punjabi Bagh",
        }[raw_name]
        if display not in stations:
            continue
        df = _get_weather_df(raw_name, lat, lon, start, end)
        if df.empty:
            continue
        existing = _existing_timestamps(db, WeatherReading, stations[display].id)
        rows = []
        for _, r in df.iterrows():
            ts = r["time"]
            if ts in existing:
                continue
            rows.append(WeatherReading(
                station_id=stations[display].id,
                timestamp=ts,
                temperature=_to_float(r.get("temperature_2m")),
                humidity=_to_float(r.get("relative_humidity_2m")),
                pressure_msl=_to_float(r.get("pressure_msl")),
                surface_pressure=_to_float(r.get("surface_pressure")),
                wind_speed=_to_float(r.get("wind_speed_10m")),
                wind_direction=_to_float(r.get("wind_direction_10m")),
                precipitation=_to_float(r.get("precipitation")),
                cloud_cover=_to_float(r.get("cloud_cover")),
                pbl_height=_to_float(r.get("boundary_layer_height")),
            ))
            existing.add(ts)
        if rows:
            db.add_all(rows)
            if not dry_run:
                db.commit()
            inserted += len(rows)
    return inserted


def refresh_fire(db, dry_run: bool = False) -> int:
    """Upsert recent NASA FIRMS active fires; returns inserted row count."""
    from ..models.db_models import FireReading

    resp = requests.get(FIRMS_CSV, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    df = pd.read_csv(pd.io.common.StringIO(resp.text))
    hits = (
        (df["longitude"] >= REGION["min_lon"])
        & (df["longitude"] <= REGION["max_lon"])
        & (df["latitude"] >= REGION["min_lat"])
        & (df["latitude"] <= REGION["max_lat"])
    )
    region = df[hits]
    if region.empty:
        return 0

    existing = {
        (r.latitude, r.longitude)
        for r in db.query(FireReading.latitude, FireReading.longitude).all()
    }
    rows = []
    for _, r in region.iterrows():
        key = (_to_float(r.get("latitude")), _to_float(r.get("longitude")))
        if key in existing:
            continue
        try:
            ts = pd.to_datetime(
                f"{r.get('acq_date')} {str(r.get('acq_time')).zfill(4)}",
                format="%Y-%m-%d %H%M",
                errors="coerce",
            )
        except Exception:
            ts = pd.to_datetime(r.get("acq_date"), errors="coerce")
        rows.append(FireReading(
            latitude=_to_float(r.get("latitude")),
            longitude=_to_float(r.get("longitude")),
            acq_date=ts if ts is not None and pd.notna(ts) else None,
            confidence=str(r.get("confidence", "")),
            frp=_to_float(r.get("frp")),
            satellite=str(r.get("satellite", "")),
            daynight=str(r.get("daynight", "")),
        ))
        existing.add(key)
    if rows:
        db.add_all(rows)
        if not dry_run:
            db.commit()
    return len(rows)


def refresh_pollution(db, dry_run: bool = False) -> int:
    """Upsert recent CPCB pollution readings from opencity.in CKAN; returns row count."""
    from ..models.db_models import PollutionReading, Station
    from ..services.aqi_calculator import calculate_aqi

    stations = {s.name: s for s in db.query(Station).all()}
    pmap = {
        "PM2.5 (ug/m3)": "pm25",
        "PM10 (ug/m3)": "pm10",
        "NO2 (ug/m3)": "no2",
        "SO2 (ug/m3)": "so2",
        "CO (mg/m3)": "co",
        "Ozone (ug/m3)": "o3",
    }
    inserted = 0
    for raw_name, resource_id in CKAN_RESOURCES.items():
        display = {
            "Anand_Vihar": "Anand Vihar",
            "RK_Puram": "RK Puram",
            "ITO": "ITO",
            "Dwarka": "Dwarka",
            "Punjabi_Bagh": "Punjabi Bagh",
        }[raw_name]
        if display not in stations:
            continue
        try:
            resp = requests.get(
                CKAN_BASE,
                params={"resource_id": resource_id, "limit": 500, "sort": "Timestamp desc"},
                timeout=HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            records = resp.json().get("result", {}).get("records", [])
        except Exception as exc:
            logger.warning("CKAN fetch failed for %s: %s", raw_name, exc)
            continue
        if not records:
            continue
        df = pd.DataFrame(records)
        if {"datetime", "site"} not in ({c for c in df.columns} , set()):
            pass
        ts_col = next((c for c in ["datetime", "time", "From Date", "timestamp", "Timestamp"] if c in df.columns), None)
        if not ts_col:
            continue
        existing = _existing_timestamps(db, PollutionReading, stations[display].id)
        rows = []
        for _, r in df.iterrows():
            ts = pd.to_datetime(r[ts_col], utc=False, errors="coerce")
            if ts is None or pd.isna(ts):
                continue
            ts = ts.tz_localize(None) if ts.tzinfo else ts
            if ts in existing:
                continue
            vals = {}
            for src, dst in pmap.items():
                vals[dst] = _to_float(r.get(src))
            aqi_val, _, _ = calculate_aqi(
                vals.get("pm25"), vals.get("pm10"), vals.get("o3"),
                vals.get("no2"), vals.get("so2"), vals.get("co"),
            )
            rows.append(PollutionReading(
                station_id=stations[display].id,
                timestamp=ts,
                pm25=vals.get("pm25"),
                pm10=vals.get("pm10"),
                o3=vals.get("o3"),
                no2=vals.get("no2"),
                so2=vals.get("so2"),
                co=vals.get("co"),
                aqi=aqi_val,
            ))
            existing.add(ts)
        if rows:
            db.add_all(rows)
            if not dry_run:
                db.commit()
            inserted += len(rows)
    return inserted


def run_refresh_once(db=None, dry_run: bool = False) -> dict:
    """Run one full refresh pass. Returns a summary dict.

    When `dry_run` is True the summaries reflect what *would* be inserted but
    nothing is committed to the database (the session is rolled back).
    """
    from ..database import SessionLocal

    close = db is None
    session = db if db is not None else SessionLocal()
    summary = {"weather": 0, "fire": 0, "pollution": 0}
    try:
        summary["weather"] = refresh_weather(session, dry_run=dry_run)
        summary["fire"] = refresh_fire(session, dry_run=dry_run)
        summary["pollution"] = refresh_pollution(session, dry_run=dry_run)
        if dry_run:
            session.rollback()
    except Exception as exc:
        logger.warning("live refresh failed partway: %s", exc, exc_info=True)
    finally:
        if close:
            session.close()
    logger.info("live refresh summary: %s", summary)
    return summary


async def refresh_loop(interval_hours: float = 3.0, stop: asyncio.Event | None = None):
    """Background loop that periodically refreshes live data."""
    while True:
        try:
            await asyncio.to_thread(run_refresh_once)
        except Exception as exc:
            logger.warning("refresh loop iteration failed: %s", exc)
        if stop is not None and stop.is_set():
            break
        await asyncio.sleep(interval_hours * 3600)
