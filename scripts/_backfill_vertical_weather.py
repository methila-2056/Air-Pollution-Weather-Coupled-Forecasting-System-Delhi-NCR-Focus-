"""One-off maintenance: fill vertical pressure-level columns + top up weather tail.

Open-Meteo's *archive* API does not publish pressure-level temperatures (they
come back NULL for all history). The *forecast* API publishes pressure-level
columns only for its recent nowcast window (~2 weeks). This script therefore:

  1. **Vertical backfill** — for every stored row in the recent window with
     ``temperature_925hPa IS NULL``, writes the six pressure-level columns
     wherever the Open-Meteo forecast API returns real (non-NULL) values.
     Rows where the source has no value are left NULL (honest limitation;
     ERA5/Copernicus CDS is documented as the production-grade historical
     upgrade).
  2. **Tail insert** — inserts genuinely-missing weather rows (timestamps
     strictly newer than the stored maximum, capped at 'now', UTC convention)
     so no gap remains before the current hour. Skips junk rows with no
     surface temperature.

Idempotent / safe:
  * never overwrites an existing pressure-level value,
  * only inserts timestamps newer than the stored max and <= now,
  * re-running converges to the same state.

Usage:
    python -m scripts._backfill_vertical_weather
"""

import logging
import pathlib
import sys
import time
from datetime import UTC, datetime

import pandas as pd
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa  # noqa: E402
from backend.app.database import SessionLocal  # noqa: E402
from backend.app.models.db_models import Station, WeatherReading  # noqa: E402
from backend.app.services.refresh_service import STATIONS, _to_float  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_vertical")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS = 92
FORECAST_DAYS = 5
DELAY = 0.4

FULL_VARS = (
    "temperature_2m,relative_humidity_2m,pressure_msl,surface_pressure,"
    "wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,"
    "boundary_layer_height,"
    "temperature_1000hPa,temperature_925hPa,temperature_850hPa,temperature_700hPa,"
    "geopotential_height_925hPa,geopotential_height_850hPa"
)

PL_COLS = [
    "temperature_1000hPa",
    "temperature_925hPa",
    "temperature_850hPa",
    "temperature_700hPa",
    "geopotential_height_925hPa",
    "geopotential_height_850hPa",
]


def fetch_nowcast(lat: float, lon: float) -> pd.DataFrame:
    params: dict = {
        "latitude": lat,
        "longitude": lon,
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "hourly": FULL_VARS,
        "timezone": "UTC",
    }
    for attempt in range(5):
        try:
            resp = requests.get(FORECAST_URL, params=params, timeout=120)
            resp.raise_for_status()
            hourly = resp.json().get("hourly", {})
            if not hourly or "time" not in hourly:
                return pd.DataFrame()
            df = pd.DataFrame(hourly)
            df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None)
            return df
        except Exception as exc:  # noqa: BLE001
            wait = 5 * (attempt + 1)
            logger.warning("  retry %d/5: %s (wait %ds)", attempt + 1, exc, wait)
            time.sleep(wait)
    logger.warning("  nowcast fetch FAILED for (%s, %s)", lat, lon)
    return pd.DataFrame()


def backfill_station(db, raw_name: str):
    display = raw_name.replace("_", " ")
    station = db.query(Station).filter(Station.name == display).first()
    if station is None:
        print(f"SKIP {raw_name}: station '{display}' not in DB")
        return 0, 0, 0
    lat, lon = STATIONS[raw_name]

    df = fetch_nowcast(lat, lon)
    if df.empty:
        print(f"SKIP {raw_name}: no nowcast data returned")
        return 0, 0, 0
    df.set_index("time", inplace=True)
    for col in PL_COLS:
        if col not in df.columns:
            df[col] = None

    max_ts = db.query(sa.func.max(WeatherReading.timestamp)).filter(WeatherReading.station_id == station.id).scalar()
    now = datetime.now(UTC).replace(tzinfo=None)

    # ── 1) Tail insert: strictly-new timestamps <= now, requiring surface temperature.
    inserted = 0
    if max_ts is not None and now > max_ts:
        tail_cut = max_ts + pd.Timedelta(hours=1)
        existing = {
            ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts
            for (ts,) in db.query(WeatherReading.timestamp).filter(WeatherReading.station_id == station.id).all()
        }
        rows = []
        for ts, r in df.iterrows():
            if ts > tail_cut and ts <= now and ts not in existing:
                if pd.isna(r.get("temperature_2m")):
                    continue
                rows.append(WeatherReading(
                    station_id=station.id,
                    timestamp=pd.Timestamp(ts),
                    temperature=_to_float(r.get("temperature_2m")),
                    humidity=_to_float(r.get("relative_humidity_2m")),
                    pressure_msl=_to_float(r.get("pressure_msl")),
                    surface_pressure=_to_float(r.get("surface_pressure")),
                    wind_speed=_to_float(r.get("wind_speed_10m")),
                    wind_direction=_to_float(r.get("wind_direction_10m")),
                    precipitation=_to_float(r.get("precipitation")),
                    cloud_cover=_to_float(r.get("cloud_cover")),
                    pbl_height=_to_float(r.get("boundary_layer_height")),
                    temperature_1000hPa=_to_float(r.get("temperature_1000hPa")),
                    temperature_925hPa=_to_float(r.get("temperature_925hPa")),
                    temperature_850hPa=_to_float(r.get("temperature_850hPa")),
                    temperature_700hPa=_to_float(r.get("temperature_700hPa")),
                    geopotential_height_925hPa=_to_float(r.get("geopotential_height_925hPa")),
                    geopotential_height_850hPa=_to_float(r.get("geopotential_height_850hPa")),
                ))
        if rows:
            db.add_all(rows)
            db.commit()
            inserted = len(rows)

    # ── 2) Vertical backfill: fill pressure columns on stale rows where source has values.
    lower = df.index.min()
    stale = (
        db.query(WeatherReading)
        .filter(
            WeatherReading.station_id == station.id,
            WeatherReading.temperature_925hPa.is_(None),
            WeatherReading.timestamp >= lower,
            WeatherReading.timestamp <= now,
        )
        .all()
    )
    updated = 0
    for rec in stale:
        src = df.loc[rec.timestamp] if rec.timestamp in df.index else None
        if src is None:
            continue
        vals = {c: _to_float(src.get(c)) for c in PL_COLS}
        if all(v is None for v in vals.values()):
            continue
        if vals["temperature_1000hPa"] is not None:
            rec.temperature_1000hPa = vals["temperature_1000hPa"]
        if vals["temperature_925hPa"] is not None:
            rec.temperature_925hPa = vals["temperature_925hPa"]
        if vals["temperature_850hPa"] is not None:
            rec.temperature_850hPa = vals["temperature_850hPa"]
        if vals["temperature_700hPa"] is not None:
            rec.temperature_700hPa = vals["temperature_700hPa"]
        if vals["geopotential_height_925hPa"] is not None:
            rec.geopotential_height_925hPa = vals["geopotential_height_925hPa"]
        if vals["geopotential_height_850hPa"] is not None:
            rec.geopotential_height_850hPa = vals["geopotential_height_850hPa"]
        updated += 1
    if updated:
        db.commit()

    still_missing = db.query(WeatherReading).filter(
        WeatherReading.station_id == station.id,
        WeatherReading.temperature_925hPa.is_(None),
        WeatherReading.timestamp >= lower,
        WeatherReading.timestamp <= now,
    ).count()

    print(f"{raw_name:24s} tail_inserted={inserted:>4} vertical_updated={updated:>5} still_missing(nowcast_window)={still_missing:>5}")
    return inserted, updated, still_missing


def main():
    db = SessionLocal()
    try:
        totals = {"inserted": 0, "updated": 0, "still": 0}
        for raw_name in STATIONS:
            ins, upd, stl = backfill_station(db, raw_name)
            totals["inserted"] += ins
            totals["updated"] += upd
            totals["still"] += stl
            time.sleep(DELAY)
        print("\n==== SUMMARY ====")
        print(f"tail rows inserted       : {totals['inserted']:,}")
        print(f"rows given vertical data : {totals['updated']:,}")
        print(f"rows still missing (win) : {totals['still']:,}")
    finally:
        db.close()


if __name__ == "__main__":
    main()