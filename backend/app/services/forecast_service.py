import os
import logging
import joblib
import numpy as np
from datetime import datetime, timedelta
from ..services.aqi_calculator import calculate_aqi, get_dominant_pollutant
from ..utils.helpers import haversine_distance, is_winter, get_season

logger = logging.getLogger("aerocast.forecast")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "models")

DEFAULT_HORIZONS = [1, 6, 12, 24, 48, 72]

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

def predict_pollutants(features: dict, horizons=None) -> list[dict]:
    if horizons is None:
        horizons = DEFAULT_HORIZONS
    predictions = []
    for h in horizons:
        pm25_model = load_pollutant_model("pm25", h)
        pm10_model = load_pollutant_model("pm10", h)
        o3_model = load_pollutant_model("o3", h)
        no2_model = load_pollutant_model("no2", h)

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

        aqi_val, category, dominant = calculate_aqi(
            pm25_pred, pm10_pred, o3_pred, no2_pred,
            features.get("so2_lag1"), features.get("co_lag1"),
        )
        predictions.append({
            "horizon_hours": int(h),
            "pm25_pred": round(pm25_pred, 1),
            "pm10_pred": round(pm10_pred, 1),
            "o3_pred": round(o3_pred, 1),
            "no2_pred": round(no2_pred, 1),
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

def build_features_from_db(db, station_id: int) -> dict:
    from ..models.db_models import Station, PollutionReading, WeatherReading, FireReading

    features = {name: 0.0 for name in FEATURE_NAMES}
    features["season"] = "winter"

    station = db.query(Station).filter(Station.id == station_id).first()
    station_lat = station.latitude if station else 28.6139
    station_lon = station.longitude if station else 77.2090

    poll = (
        db.query(PollutionReading)
        .filter(PollutionReading.station_id == station_id)
        .order_by(PollutionReading.timestamp.desc())
        .first()
    )
    if poll:
        features.update({
            "pm25_lag1": poll.pm25 or 0.0,
            "pm10_lag1": poll.pm10 or 0.0,
            "o3_lag1": poll.o3 or 0.0,
            "no2_lag1": poll.no2 or 0.0,
            "so2_lag1": poll.so2 or 0.0,
            "co_lag1": poll.co or 0.0,
            "aqi_lag1": poll.aqi or 0.0,
        })
        ts = poll.timestamp
    else:
        ts = datetime.utcnow()

    weather = (
        db.query(WeatherReading)
        .filter(WeatherReading.station_id == station_id)
        .order_by(WeatherReading.timestamp.desc())
        .first()
    )
    if weather:
        pbl = weather.pbl_height or 500.0
        features.update({
            "temperature": weather.temperature or 0.0,
            "humidity": weather.humidity or 0.0,
            "pressure_msl": weather.pressure_msl or 0.0,
            "wind_speed": weather.wind_speed or 0.0,
            "wind_direction": weather.wind_direction or 0.0,
            "precipitation": weather.precipitation or 0.0,
            "cloud_cover": weather.cloud_cover or 0.0,
            "pbl_height": pbl,
            "inversion_strength": round(max(0.0, (500 - pbl) / 500), 4),
        })

    fires = db.query(FireReading).limit(500).all()
    features.update(_fire_features(station_lat, station_lon, fires))

    if ts.tzinfo is not None:
        ts = ts.astimezone().replace(tzinfo=None)
    features["hour"] = ts.hour
    features["is_winter"] = int(is_winter(ts))
    features["day_of_year"] = ts.timetuple().tm_yday
    features["season"] = get_season(ts)

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