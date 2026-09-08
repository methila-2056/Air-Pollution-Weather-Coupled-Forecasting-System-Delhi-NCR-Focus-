"""Load the real coupled dataset + trained metrics into the AeroCast-NCR backend DB.

Usage:
    python -m backend.scripts.load_data [--csv data/processed/coupled_dataset.csv]
"""

import argparse
import json
from pathlib import Path

import pandas as pd

import backend.app.models.db_models as dbm  # noqa: E402, F401  (registers tables)
from backend.app.database import Base, SessionLocal, engine  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "processed" / "coupled_dataset.csv"
MODELS_DIR = PROJECT_ROOT / "models"


def load_coupled_data(db, csv_path: Path) -> dict:
    from backend.app.models.db_models import PollutionReading, Station, WeatherReading
    from backend.app.services.aqi_calculator import calculate_aqi

    stations = {s.name: s for s in db.query(Station).all()}
    station_coords = {
        "Anand Vihar": (28.6492, 77.2918),
        "RK Puram": (28.5601, 77.1835),
        "ITO": (28.6290, 77.2410),
        "Dwarka": (28.5921, 77.0460),
        "Punjabi Bagh": (28.6692, 77.1285),
    }
    raw_to_display = {
        "Anand_Vihar": "Anand Vihar",
        "RK_Puram": "RK Puram",
        "Punjabi_Bagh": "Punjabi Bagh",
    }

    for name, (lat, lon) in station_coords.items():
        if name not in stations:
            st = Station(name=name, latitude=lat, longitude=lon, city="Delhi NCR")
            db.add(st)
            db.flush()
            stations[name] = st

    existing_ts: dict[int, set] = {}
    for sid, ts in db.query(PollutionReading.station_id, PollutionReading.timestamp).all():
        existing_ts.setdefault(sid, set()).add(ts)

    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    counts = {"pollution": 0, "weather": 0}

    batch_size = 5000
    rows = []
    for _, r in df.iterrows():
        st = stations[raw_to_display.get(r["station"], r["station"])]
        ts = r["timestamp"]
        if ts in existing_ts.get(st.id, set()):
            continue
        existing_ts.setdefault(st.id, set()).add(ts)

        pm25 = _safe(r.get("pm25"))
        pm10 = _safe(r.get("pm10"))
        o3 = _safe(r.get("o3"))
        no2 = _safe(r.get("no2"))
        so2 = _safe(r.get("so2"))
        co = _safe(r.get("co"))
        aqi_val = calculate_aqi(pm25, pm10, o3, no2, so2, co)[0]

        poll = PollutionReading(
            station_id=st.id,
            timestamp=ts,
            pm25=pm25,
            pm10=pm10,
            o3=o3,
            no2=no2,
            so2=so2,
            co=co,
            aqi=aqi_val,
        )
        rows.append(poll)
        counts["pollution"] += 1

        weather = WeatherReading(
            station_id=st.id,
            timestamp=ts,
            temperature=_safe(r.get("temperature_2m")),
            humidity=_safe(r.get("relative_humidity_2m")),
            pressure_msl=_safe(r.get("pressure_msl")),
            surface_pressure=_safe(r.get("surface_pressure")),
            wind_speed=_safe(r.get("wind_speed_10m")),
            wind_direction=_safe(r.get("wind_direction_10m")),
            precipitation=_safe(r.get("precipitation")),
            cloud_cover=_safe(r.get("cloud_cover")),
            pbl_height=_safe(r.get("boundary_layer_height")),
        )
        rows.append(weather)
        counts["weather"] += 1

        if len(rows) >= batch_size:
            db.add_all(rows)
            db.commit()
            rows = []

    if rows:
        db.add_all(rows)
        db.commit()

    return counts


def load_fire_data(db, fire_csv: Path) -> int:
    if not fire_csv.exists():
        return 0
    from backend.app.models.db_models import FireReading

    df = pd.read_csv(fire_csv, low_memory=False)

    acq_time = (
        pd.to_numeric(df.get("acq_time"), errors="coerce")
        .fillna(0)
        .astype(int)
        .astype(str)
        .str.zfill(4)
    )
    dt = pd.to_datetime(
        df["acq_date"].astype(str) + " " + acq_time,
        format="%Y-%m-%d %H%M",
        errors="coerce",
    )
    dt = dt.fillna(pd.to_datetime(df["acq_date"], errors="coerce"))

    lat = pd.to_numeric(df.get("latitude"), errors="coerce")
    lon = pd.to_numeric(df.get("longitude"), errors="coerce")

    existing = {
        (r.latitude, r.longitude)
        for r in db.query(FireReading.latitude, FireReading.longitude).all()
    }

    payloads = []
    for ax, ny, ts, conf, frp_v, sat, dn in zip(
        lat,
        lon,
        dt,
        df.get("confidence", pd.Series(dtype="str")),
        df.get("frp"),
        df.get("satellite", pd.Series(dtype="str")),
        df.get("daynight", pd.Series(dtype="str")),
        strict=True,
    ):
        key = (_clean(ax), _clean(ny))
        if key[0] is None or key[1] is None or key in existing:
            continue
        ts_v = None if pd.isna(ts) else ts
        payloads.append({
            "latitude": key[0],
            "longitude": key[1],
            "acq_date": ts_v,
            "confidence": "" if conf is None else str(conf),
            "frp": _clean(frp_v),
            "satellite": _clean(sat),
            "daynight": _clean(dn),
        })
        existing.add(key)

    if payloads:
        db.bulk_insert_mappings(FireReading, payloads)
        db.commit()
    return len(payloads)


def load_metrics(db, metrics_path: Path) -> int:
    if not metrics_path.exists():
        return 0
    from backend.app.models.db_models import ModelMetrics

    existing = {
        (m.model_name, m.pollutant, m.horizon_hours)
        for m in db.query(ModelMetrics.model_name, ModelMetrics.pollutant, ModelMetrics.horizon_hours).all()
    }

    with open(metrics_path, encoding="utf-8") as fh:
        entries = json.load(fh)

    count = 0
    for e in entries:
        key = (e["model"], e["target"], e["horizon"])
        if key in existing:
            continue
        existing.add(key)
        db.add(ModelMetrics(
            model_name=e["model"],
            pollutant=e["target"],
            horizon_hours=e["horizon"],
            mae=e["test_mae"],
            rmse=e["test_rmse"],
            r2=e["test_r2"],
            mape=e["test_mape"],
        ))
        count += 1
    db.commit()
    return count


def load_alerts_seed(db) -> int:
    from backend.app.models.db_models import Alert, Station

    stations = {s.name: s.id for s in db.query(Station).all()}
    if not stations:
        return 0
    existing = db.query(Alert).count()
    if existing > 0:
        return 0

    cozy = stations.get("Anand Vihar", 1)
    alerts = [
        Alert(
            station_id=cozy,
            alert_level="INFO",
            title="Monitoring Active",
            description="All 5 Delhi NCR monitoring stations reporting hourly data.",
            recommendation="Continue monitoring hourly forecasts.",
        ),
        Alert(
            station_id=cozy,
            alert_level="WATCH",
            title="Winter Regime Active",
            description="Cold-season conditions favour pollution accumulation; inversion and PBL trends are being tracked.",
            factors="Seasonal meteorological conditions",
            recommendation="Review inversion strength and fire activity panels.",
        ),
    ]
    db.add_all(alerts)
    db.commit()
    return len(alerts)


def main():
    parser = argparse.ArgumentParser(description="Load real CPCB/Open-Meteo/FIRMS data into backend DB.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--fire-csv", default=str(PROJECT_ROOT / "data" / "fire" / "firms_fires.csv"))
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables.")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("Loading coupled dataset ...")
        counts = load_coupled_data(db, Path(args.csv))
        print(f"  Pollution readings : {counts['pollution']:,}")
        print(f"  Weather readings   : {counts['weather']:,}")

        print("Loading fire data ...")
        n_fire = load_fire_data(db, Path(args.fire_csv))
        print(f"  Fire records       : {n_fire:,}")

        print("Loading model metrics ...")
        n_metrics = load_metrics(db, MODELS_DIR / "metrics.json")
        print(f"  Metric entries     : {n_metrics:,}")

        print("Seeding alerts ...")
        n_alerts = load_alerts_seed(db)
        print(f"  Seed alerts        : {n_alerts:,}")
    finally:
        db.close()

    print("\nBackend database load complete.")


def _safe(v):
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _clean(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    return v


if __name__ == "__main__":
    main()
