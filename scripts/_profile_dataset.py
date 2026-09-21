"""One-off profiler for the training-dataset build (logs to a file)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import SessionLocal
from backend.app.models.db_models import FireReading, PollutionReading, Station, WeatherReading
from ml.preprocessing.training_dataset import (
    add_atmosphere_and_temporal_features,
    add_fire_features,
    add_target_lags_and_rolling,
    align_observations,
    chronological_split,
    flag_outliers,
)

LOG = Path(__file__).resolve().parent.parent / "scripts" / "_profile_dataset.log"


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def df_from_model(db, model, cols):
    rows = db.query(model).all()
    return __import__("pandas").DataFrame({c: [getattr(r, c) for r in rows] for c in cols})


def main() -> None:
    LOG.write_text("", encoding="utf-8")
    db = SessionLocal()

    t0 = time.time()
    stations = df_from_model(db, Station, ["id", "name", "latitude", "longitude"])
    stations["station"] = stations["name"]
    poll = df_from_model(db, PollutionReading, ["station_id", "timestamp", "pm25"])
    wx = df_from_model(db, WeatherReading, [
        "station_id", "timestamp", "temperature", "humidity", "pressure", "pressure_msl",
        "surface_pressure", "wind_speed", "wind_direction", "precipitation", "cloud_cover",
        "pbl_height", "temperature_1000hPa", "temperature_925hPa", "temperature_850hPa",
        "temperature_700hPa"])
    fires = df_from_model(db, FireReading, ["latitude", "longitude", "acq_date", "frp"])
    fires.rename(columns={"latitude": "lat", "longitude": "lon"}, inplace=True)
    db.close()
    log(f"load db: {time.time()-t0:.1f}s shapes {poll.shape} {wx.shape} {fires.shape}")

    id_to_name = dict(zip(stations["id"], stations["station"], strict=True))
    poll["station"] = poll["station_id"].map(id_to_name)
    wx["station"] = wx["station_id"].map(id_to_name)
    poll = poll.dropna(subset=["station"])
    wx = wx.dropna(subset=["station"])
    stats = stations[["station", "latitude", "longitude"]]

    t0 = time.time()
    df, report = align_observations(poll, wx, stats)
    log(f"align: {time.time()-t0:.1f}s rows={len(df)}")
    del poll, wx

    t0 = time.time()
    df = add_atmosphere_and_temporal_features(df)
    log(f"atmosphere: {time.time()-t0:.1f}s")

    t0 = time.time()
    df = add_fire_features(df, fires)
    log(f"fire: {time.time()-t0:.1f}s")

    t0 = time.time()
    df = add_target_lags_and_rolling(df)
    log(f"lags: {time.time()-t0:.1f}s")

    t0 = time.time()
    df, oc = flag_outliers(df)
    log(f"outliers: {time.time()-t0:.1f}s")

    t0 = time.time()
    df = chronological_split(df)
    log(f"split: {time.time()-t0:.1f}s")

    log(f"DONE rows={len(df)}")


if __name__ == "__main__":
    main()
