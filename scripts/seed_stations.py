"""Seed the AeroCast-NCR database with stations + historic weather from CSV.

Idempotent: inserts any stations listed in ``database.DEFAULT_STATIONS`` that are
missing, then upserts weather rows from ``data/weather/<Raw>_weather.csv``
(skipping timestamps that already exist) for whichever of those stations have
a downloaded CSV.

Usage:
    python -m scripts.seed_stations [--weather-dir data/weather]
"""

import argparse
import os
import pathlib
import sys
from datetime import datetime

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Prefer a DATABASE_URL on the CLI/env; otherwise reuse the project .env.
_env_file = ROOT / ".env"
if not os.environ.get("DATABASE_URL") and _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL=") and not line.startswith("#"):
            os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

from backend.app.database import DEFAULT_STATIONS, SessionLocal  # noqa: E402
from backend.app.models.db_models import Station, WeatherReading  # noqa: E402


def _to_float(v):
    try:
        if v is None or (isinstance(v, (float, int)) and v != v):
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def seed_stations(db) -> int:
    existing = {s.name for s in db.query(Station).all()}
    added = 0
    for spec in DEFAULT_STATIONS:
        if spec["name"] in existing:
            continue
        db.add(Station(**spec))
        added += 1
    if added:
        db.commit()
    return added


def load_csv_weather(db, weather_dir: pathlib.Path) -> int:
    stations = {s.name: s for s in db.query(Station).all()}
    total = 0
    for csv_path in sorted(weather_dir.glob("*_weather.csv")):
        display = csv_path.name.replace("_weather.csv", "").replace("_", " ")
        station = stations.get(display)
        if station is None:
            print(f"  SKIP {csv_path.name}: station '{display}' not in DB")
            continue
        existing = {
            ts.replace(tzinfo=None) if ts.tzinfo else ts
            for (ts,) in db.query(WeatherReading.timestamp)
            .filter(WeatherReading.station_id == station.id)
            .all()
        }
        df = pd.read_csv(csv_path)
        if "time" not in df.columns:
            print(f"  SKIP {csv_path.name}: no 'time' column")
            continue
        rows = []
        for _, r in df.iterrows():
            ts = pd.to_datetime(r["time"], errors="coerce")
            if pd.isna(ts) or ts in existing:
                continue
            rows.append(WeatherReading(
                station_id=station.id,
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
        if rows:
            db.add_all(rows)
            db.commit()
            total += len(rows)
            print(f"  {csv_path.name}: +{len(rows)} weather rows for '{display}'")
        else:
            print(f"  {csv_path.name}: no new rows for '{display}'")
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weather-dir", type=pathlib.Path, default=ROOT / "data" / "weather")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        added = seed_stations(db)
        print(f"Stations added: {added}")
        total_w = load_csv_weather(db, args.weather_dir)
        print(f"Weather rows loaded: {total_w:,}")
        n_stations = db.query(Station).count()
        print(f"Total stations now: {n_stations}")
    finally:
        db.close()


if __name__ == "__main__":
    main()