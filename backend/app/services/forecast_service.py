import os
import logging
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from ..services.aqi_calculator import calculate_aqi, get_dominant_pollutant
from ..utils.helpers import haversine_distance, is_winter, get_season

logger = logging.getLogger("aerocast.forecast")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "models")

DEFAULT_HORIZONS = [1, 6, 12, 24, 48, 72]

ALL_POLLUTANTS = ["pm25", "pm10", "o3", "no2", "so2", "co"]

FEATURE_NAMES = [
    "pm25_lag1", "pm10_lag1", "o3_lag1", "no2_lag1", "so2_lag1", "co_lag1",
    "temperature", "humidity", "pressure_msl", "wind_speed", "wind_direction",
    "precipitation", "cloud_cover", "pbl_height", "inversion_strength",
    "fire_impact_score", "fire_count_100km", "nearest_fire_km",
    "hour", "is_winter", "day_of_year", "aqi_lag1", "season",
]

def load_model(model_name: str):
    path = os.path.join(MODEL_DIR, f"{model_name}.joblib")
    if os.path.exists(path):
        try:
            payload = joblib.load(path)
            if isinstance(payload, dict) and "model" in payload:
                model_obj = payload["model"]
                if not hasattr(model_obj, "predict"):
                    logger.warning("Model payload for %s has no predict attribute", model_name)
                return model_obj
            return payload
        except Exception as exc:
            logger.warning("Failed to load model %s: %s", model_name, exc)
    return None

def available_models() -> list[str]:
    if not os.path.isdir(MODEL_DIR):
        return []
    return sorted(f for f in os.listdir(MODEL_DIR) if f.endswith(".joblib"))

def load_pollutant_model(pollutant: str, horizon_hours: int = None):
    for model_type in ("xgboost", "random_forest", "rf", "persistence", "gbm"):
        suffixes = [f"_{horizon_hours}h", f"_{horizon_hours}", ""]
        if horizon_hours is None:
            suffixes = [""]
        for suffix in suffixes:
            name = f"{model_type}_{pollutant}{suffix}"
            model = load_model(name)
            if model is not None:
                return model
    return None

def _model_predict(model, features: dict) -> float:
    if model is None:
        return None
    try:
        cols = None
        for attr in ("feature_names_", "feature_names_in_"):
            if hasattr(model, attr):
                names = getattr(model, attr)
                if names is not None and len(names):
                    cols = list(names)
                    break
        if cols is None and hasattr(model, "model"):
            inner = model.model
            if hasattr(inner, "feature_names_in_"):
                names = inner.feature_names_in_
                if names is not None and len(names):
                    cols = list(names)
        if cols is None:
            cols = FEATURE_NAMES
        arr = np.array([[features.get(c, 0.0) for c in cols]], dtype=float)
        raw = model.predict(arr)
        val = float(np.ravel(raw)[0])
        return None if (np.isnan(val) or np.isinf(val)) else max(0.0, val)
    except Exception as exc:
        logger.warning("Prediction failed for %s: %s", type(model).__name__, exc)
        return None

def _fallback_pm25(features: dict, h: int) -> float:
    base = features.get("pm25_lag1", 50) or 50
    decay = max(0.55, 1.0 - 0.006 * h)
    wind = features.get("wind_speed", 5) or 5
    wind_penalty = 1.0 + max(0.0, 2.0 - wind) * 0.04
    pbl = features.get("pbl_height", 500) or 500
    pbl_factor = 1.0 + max(0.0, (400 - pbl) / 400) * 0.35
    fire = features.get("fire_impact_score", 0) or 0
    fire_factor = 1.0 + fire * 0.15
    return base * decay * wind_penalty * pbl_factor * fire_factor

def _fallback_pm10(pm25_pred: float, features: dict, h: int) -> float:
    base = features.get("pm10_lag1", 0) or 0
    if not base:
        base = pm25_pred * 1.9
    return max(base * (1.0 - 0.004 * h), pm25_pred * 1.5)

def _fallback_o3(features: dict, h: int) -> float:
    temp = features.get("temperature", 25) or 25
    solar = 1.0 + max(0.0, (temp - 20) / 20) * 0.3
    return max(10.0, 45 * solar * (1.0 - 0.002 * h))

def _fallback_no2(features: dict) -> float:
    disp = 1.0 + (features.get("wind_speed", 5) or 5) * 0.05
    return max(5.0, 48 / disp)

def _fallback_so2(features: dict) -> float:
    base = features.get("so2_lag1") or 15.0
    disp = 1.0 + max(0.0, (features.get("wind_speed", 5) or 5) - 3.0) * 0.03
    precip = features.get("precipitation", 0) or 0
    washout = max(0.6, 1.0 - precip * 0.15)
    return max(2.0, base * washout / disp)

def _fallback_co(features: dict) -> float:
    base = features.get("co_lag1") or 1.4
    disp = 1.0 + (features.get("wind_speed", 5) or 5) * 0.04
    return max(0.2, base / disp)

def predict_pollutants(features: dict, horizons=None) -> list[dict]:
    if horizons is None:
        horizons = DEFAULT_HORIZONS
    predictions = []
    for h in horizons:
        pm25_model = load_pollutant_model("pm25", h)
        pm10_model = load_pollutant_model("pm10", h)
        o3_model = load_pollutant_model("o3", h)
        no2_model = load_pollutant_model("no2", h)
        so2_model = load_pollutant_model("so2", h)
        co_model = load_pollutant_model("co", h)

        pm25_pred = _model_predict(pm25_model, features)
        if pm25_pred is None:
            pm25_pred = _fallback_pm25(features, h)
        pm10_pred = _model_predict(pm10_model, features)
        if pm10_pred is None:
            pm10_pred = _fallback_pm10(pm25_pred, features, h)
        o3_pred = _model_predict(o3_model, features)
        if o3_pred is None:
            o3_pred = _fallback_o3(features, h)
        no2_pred = _model_predict(no2_model, features)
        if no2_pred is None:
            no2_pred = _fallback_no2(features)
        so2_pred = _model_predict(so2_model, features)
        if so2_pred is None:
            so2_pred = _fallback_so2(features)
        co_pred = _model_predict(co_model, features)
        if co_pred is None:
            co_pred = _fallback_co(features)

        aqi_val, category, dominant = calculate_aqi(
            pm25_pred, pm10_pred, o3_pred, no2_pred, so2_pred, co_pred,
        )
        predictions.append({
            "horizon_hours": int(h),
            "pm25_pred": round(pm25_pred, 1),
            "pm10_pred": round(pm10_pred, 1),
            "o3_pred": round(o3_pred, 1),
            "no2_pred": round(no2_pred, 1),
            "so2_pred": round(so2_pred, 1),
            "co_pred": round(co_pred, 2),
            "aqi_pred": aqi_val,
            "aqi_category": category,
            "dominant_pollutant": dominant,
        })
    return predictions

def _fire_features(station_lat: float, station_lon: float, fires) -> dict:
    count_100 = 0
    distances = []
    impact = 0.0
    for f in fires:
        d = haversine_distance(station_lat, station_lon, f.latitude, f.longitude)
        distances.append(d)
        if d <= 100:
            count_100 += 1
        if f.frp:
            impact += f.frp * max(0.0, 1 - d / 500)
    nearest = min(distances) if distances else None
    return {
        "fire_count_100km": count_100,
        "nearest_fire_km": round(nearest, 1) if nearest is not None else None,
        "fire_impact_score": round(min(1.0, impact / 1000.0), 4),
    }

def _flush_json_value(v):
    """Coerce numpy/pandas values to plain JSON-safe python numbers."""
    import math
    if v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0


def build_features_from_db(db, station_id: int) -> dict:
    """Reconstruct the true ML feature vector for a station.

    Queries the station's recent hourly pollution + weather history from the
    database (the same schema the training pipeline consumes) and runs the
    identical feature-engineering functions used at training time, so the API
    feeds trained models the exact feature names/values they expect.
    """
    from ..models.db_models import Station, PollutionReading, WeatherReading

    station = db.query(Station).filter(Station.id == station_id).first()
    station_name = station.name.replace(" ", "_") if station else "Anand_Vihar"

    poll_rows = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station_id)
        .order_by(PollutionReading.timestamp.desc())
        .limit(120)
        .all()
    )
    wx_rows = (
        db.query(WeatherReading)
        .filter(WeatherReading.station_id == station_id)
        .order_by(WeatherReading.timestamp.desc())
        .limit(120)
        .all()
    )
    if not poll_rows and not wx_rows:
        return {name: 0.0 for name in FEATURE_NAMES}

    poll = pd.DataFrame([{
        "timestamp": p.timestamp, "pm25": p.pm25, "pm10": p.pm10,
        "o3": p.o3, "no2": p.no2, "so2": p.so2, "co": p.co,
    } for p in poll_rows])
    wx = pd.DataFrame([{
        "timestamp": w.timestamp, "temperature": w.temperature,
        "humidity": w.humidity, "pressure_msl": w.pressure_msl,
        "surface_pressure": w.surface_pressure, "wind_speed": w.wind_speed,
        "wind_direction": w.wind_direction, "precipitation": w.precipitation,
        "cloud_cover": w.cloud_cover, "pbl_height": w.pbl_height,
    } for w in wx_rows])

    combined = poll
    if not wx.empty and not poll.empty:
        combined = poll.merge(wx, on="timestamp", how="outer", suffixes=("", "_wx"))

    if combined.empty:
        return {name: 0.0 for name in FEATURE_NAMES}

    combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True, errors="coerce")
    combined["station"] = station_name
    lat = station.latitude if station else 28.6139
    lon = station.longitude if station else 77.2090
    combined["latitude"] = lat
    combined["longitude"] = lon
    combined = combined.sort_values("timestamp").drop_duplicates("timestamp", keep="last")

    # Small helper module import (already installed; kept local to avoid heavy top-level import)
    from ml.features.feature_engineering import (
        add_temporal_features, add_pollution_lags, add_rolling_means,
        add_rolling_std, add_wind_decomposition, add_temperature_lags,
        add_humidity_lags, add_pollution_rate_of_change, add_composite_features,
    )
    from ml.features.inversion import add_inversion_features
    from ml.features.fire_impact import add_fire_features
    from ml.features.coupling import add_coupling_features

    eng = add_temporal_features(combined)
    eng = add_pollution_lags(eng)
    eng = add_rolling_means(eng)
    eng = add_rolling_std(eng)
    eng = add_wind_decomposition(eng)
    eng = add_temperature_lags(eng)
    eng = add_humidity_lags(eng)
    eng = add_inversion_features(eng)

    # Real fire features from the FIRMS records stored in the DB
    from ..models.db_models import FireReading
    fires = db.query(FireReading).order_by(FireReading.acq_date.desc()).limit(2000).all()
    if fires:
        fires_df = pd.DataFrame([{
            "lat": f.latitude, "lon": f.longitude,
            "frp": f.frp or 1.0,
            "acq_timestamp": f.acq_date,
        } for f in fires])
        eng = add_fire_features(eng, fires_df=fires_df)
        fire_count_latest = int((eng.iloc[-1] if not eng.empty else pd.Series()).get("fire_count", 0) or 0)
    else:
        eng = add_fire_features(eng)
        fire_count_latest = 0

    eng = add_pollution_rate_of_change(eng)
    eng = add_composite_features(eng)
    eng = add_coupling_features(eng)

    latest = eng.iloc[-1]
    features = {}
    for col in eng.columns:
        if col in ("timestamp", "station", "latitude", "longitude"):
            continue
        features[col] = _flush_json_value(latest.get(col))

    # Keep aliases used by fallbacks / AQI computation
    features.setdefault("fire_impact_score", min(1.0, fire_count_latest / 50.0))
    features["day_of_year"] = features.get("day_of_year", 1)
    features["is_winter"] = int(_flush_json_value(features.get("is_winter", 0)))
    return features

def get_weather_context(db, station_id: int) -> dict:
    from ..models.db_models import WeatherReading
    r = (
        db.query(WeatherReading)
        .filter(WeatherReading.station_id == station_id)
        .order_by(WeatherReading.timestamp.desc())
        .first()
    )
    if not r:
        return {}
    return {
        "temperature": r.temperature,
        "humidity": r.humidity,
        "pressure_msl": r.pressure_msl,
        "wind_speed": r.wind_speed,
        "wind_direction": r.wind_direction,
        "precipitation": r.precipitation,
        "cloud_cover": r.cloud_cover,
        "pbl_height": r.pbl_height,
    }

def get_fire_context(db) -> dict:
    from ..models.db_models import FireReading
    fires = db.query(FireReading).order_by(FireReading.acq_date.desc()).limit(500).all()
    if not fires:
        return {"fire_count": 0}
    distances = [
        haversine_distance(28.6139, 77.2090, f.latitude, f.longitude)
        for f in fires
    ]
    return {
        "fire_count": len(fires),
        "distance_nearest_fire": round(min(distances), 1),
        "mean_frp": round(sum((f.frp or 0.0) for f in fires) / len(fires), 2),
    }

def save_forecasts(db, station_id: int, predictions: list[dict], forecast_timestamp=None) -> list:
    from ..models.db_models import Forecast
    base_ts = forecast_timestamp or datetime.utcnow()
    rows = []
    for p in predictions:
        pbl = p.get("pbl_height") or 500.0
        rows.append(Forecast(
            station_id=station_id,
            forecast_timestamp=base_ts + timedelta(hours=p["horizon_hours"]),
            horizon_hours=p["horizon_hours"],
            pm25_pred=p.get("pm25_pred"),
            pm10_pred=p.get("pm10_pred"),
            o3_pred=p.get("o3_pred"),
            no2_pred=p.get("no2_pred"),
            so2_pred=p.get("so2_pred"),
            co_pred=p.get("co_pred"),
            aqi_pred=p.get("aqi_pred"),
            aqi_category=p.get("aqi_category"),
            dominant_pollutant=p.get("dominant_pollutant"),
            inversion_detected=1 if pbl < 500 else 0,
            inversion_strength=round(max(0.0, (500 - pbl) / 500), 4),
            pbl_height=pbl,
        ))
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows

def generate_forecast(db, station_id: int, horizons=None) -> tuple[list, list[dict]]:
    features = build_features_from_db(db, station_id)
    predictions = predict_pollutants(features, horizons)
    rows = save_forecasts(db, station_id, predictions)
    return rows, predictions


def coupled_single_step(features: dict, horizon_hours: int) -> dict:
    """Single-step hook used by the online coupling loop (horizon=1 stepping)."""
    return predict_pollutants(features, horizons=[horizon_hours])[0]


def generate_coupled_forecast(db, station_id: int, horizons=None) -> dict:
    """Run the time-stepped two-way coupled forecast (SO2/CO + AQI included).

    Returns {"coupled": [...], "uncoupled": [...], "feedback_path": [...]}.
    The coupled points are persisted (coupling_mode != None).
    """
    from ml.features.coupling import corrected_pbl_height, coupling_feedback_score
    from ml.features.coupled_loop import run_coupled_forecast as _run_coupled

    horizons = horizons or DEFAULT_HORIZONS
    features = build_features_from_db(db, station_id)
    base_pbl = features.get("pbl_height") or 600.0

    result = _run_coupled(
        coupled_single_step, features, horizons,
        start_hour=features.get("hour") or 12,
    )

    for point in result["coupled"]:
        c = point["coupling"]
        corrected = corrected_pbl_height(point["pm25_pred"], base_pbl, features.get("hour") or 12)
        point["pbl_effective"] = round(corrected, 1)
        point["coupling_stability"] = c["stability_coupling_index"]
        point["coupling"] = c

    return result


def save_coupled_forecasts(db, station_id: int, points: list[dict], forecast_timestamp=None) -> list:
    """Persist the coupled forecast points (including SO2/CO + coupling state)."""
    from ..models.db_models import Forecast
    base_ts = forecast_timestamp or datetime.utcnow()
    rows = []
    for p in points:
        pbl = p.get("pbl_height") or p.get("pbl_effective") or 500.0
        rows.append(Forecast(
            station_id=station_id,
            forecast_timestamp=base_ts + timedelta(hours=p["horizon_hours"]),
            horizon_hours=p["horizon_hours"],
            pm25_pred=p.get("pm25_pred"),
            pm10_pred=p.get("pm10_pred"),
            o3_pred=p.get("o3_pred"),
            no2_pred=p.get("no2_pred"),
            so2_pred=p.get("so2_pred"),
            co_pred=p.get("co_pred"),
            aqi_pred=p.get("aqi_pred"),
            aqi_category=p.get("aqi_category"),
            dominant_pollutant=p.get("dominant_pollutant"),
            inversion_detected=1 if pbl < 500 else 0,
            inversion_strength=round(max(0.0, (500 - pbl) / 500), 4),
            pbl_height=pbl,
            coupling_stability=p.get("coupling_stability"),
            coupling_mode="coupled" if p.get("coupling_stability") is not None else None,
        ))
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows