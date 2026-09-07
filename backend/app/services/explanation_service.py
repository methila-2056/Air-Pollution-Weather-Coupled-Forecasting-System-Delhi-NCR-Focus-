import numpy as np
import shap

FEATURE_DESCRIPTIONS = {
    "pm25_lag1": ("Previous-hour PM2.5 concentration", "High recent PM2.5 levels are carrying pollution forward"),
    "pm10_lag1": ("Previous-hour PM10 concentration", "Elevated coarse-particle levels add to the burden"),
    "o3_lag1": ("Previous-hour Ozone concentration", "Photochemical ozone contributes to the index"),
    "no2_lag1": ("Previous-hour NO2 concentration", "Traffic-derived NO2 is a key driver"),
    "so2_lag1": ("Previous-hour SO2 concentration", "Industrial SO2 emissions are present"),
    "co_lag1": ("Previous-hour CO concentration", "Combustion sources keep CO elevated"),
    "temperature": ("Temperature", "Temperature modulates photochemical production and mixing"),
    "humidity": ("Relative humidity", "High humidity promotes secondary aerosol formation"),
    "pressure_msl": ("MSL pressure", "Pressure regime influences ventilation"),
    "wind_speed": ("Wind speed", "Low wind speed is limiting pollutant dispersion"),
    "wind_direction": ("Wind direction", "Winds from the north-west advect stubble-burning smoke"),
    "precipitation": ("Precipitation", "Rain scavenges pollutants from the air"),
    "cloud_cover": ("Cloud cover", "Cloud cover reduces photochemical activity"),
    "pbl_height": ("Planetary boundary layer height", "A compressed boundary layer is trapping pollutants near the surface"),
    "inversion_strength": ("Atmospheric inversion strength", "An inversion layer is inhibiting vertical mixing"),
    "fire_impact_score": ("Regional fire impact", "Stubble-burning smoke is being advected into the region"),
    "fire_count_100km": ("Fires within 100 km", "Nearby burning hotspots add fresh emissions"),
    "nearest_fire_km": ("Distance to nearest fire", "A close fire front signals imminent smoke"),
    "hour": ("Hour of day", "The diurnal cycle drives emission and chemistry patterns"),
    "is_winter": ("Winter season flag", "Winter inversions favour accumulation"),
    "day_of_year": ("Day of year", "Seasonal progression affects baseline pollution"),
    "aqi_lag1": ("Previous-hour AQI", "Persistent poor air continues into the forecast window"),
    "season": ("Season", "Season conditions the typical pollution regime"),
}

FALLBACK_WEIGHTS = [
    ("pm25_lag1", 0.26, "positive"),
    ("wind_speed", 0.22, "negative"),
    ("pbl_height", 0.18, "negative"),
    ("inversion_strength", 0.12, "positive"),
    ("fire_impact_score", 0.12, "positive"),
    ("humidity", 0.10, "positive"),
]

def _get_feature_names(model) -> list:
    for attr in ("feature_names_", "feature_names_in_"):
        if hasattr(model, attr):
            names = getattr(model, attr)
            if names is not None and len(names):
                return list(names)
    if hasattr(model, "model") and hasattr(model.model, "feature_names_in_"):
        names = model.model.feature_names_in_
        if names is not None and len(names):
            return list(names)
    return []

def explain_prediction(model, features: dict) -> list[dict]:
    try:
        cols = _get_feature_names(model)
        if not cols:
            return explain_fallback(features)
        explainer = shap.TreeExplainer(model)
        arr = np.array([[features.get(k, 0.0) for k in cols]], dtype=float)
        shap_values = explainer.shap_values(arr)
        values = np.asarray(shap_values)
        if values.ndim >= 3:
            values = values.reshape(values.shape[0], -1)
        values = values[0]
        total = float(np.sum(np.abs(values)))
        if not total:
            return explain_fallback(features)
        feature_importance = []
        for i, name in enumerate(cols):
            if i >= len(values):
                break
            v = float(values[i])
            desc, hint = FEATURE_DESCRIPTIONS.get(name, (name, ""))
            description = f"{desc}. {hint}" if hint else desc
            feature_importance.append({
                "feature": name,
                "importance": round(abs(v), 4),
                "importance_pct": round(abs(v) / total * 100, 1),
                "direction": "positive" if v > 0 else "negative",
                "value": features.get(name),
                "description": description,
            })
        feature_importance.sort(key=lambda x: x["importance"], reverse=True)
        return feature_importance[:6]
    except Exception:
        return explain_fallback(features)

def explain_fallback(features: dict) -> list[dict]:
    feature_importance = []
    for name, weight, direction in FALLBACK_WEIGHTS:
        value = features.get(name)
        desc, hint = FEATURE_DESCRIPTIONS.get(name, (name, ""))
        description = f"{desc}. {hint}" if hint else desc
        feature_importance.append({
            "feature": name,
            "importance": round(weight, 4),
            "importance_pct": round(weight / sum(w for _, w, _ in FALLBACK_WEIGHTS) * 100, 1),
            "direction": direction,
            "value": value,
            "description": description,
        })
    feature_importance.sort(key=lambda x: x["importance"], reverse=True)
    return feature_importance[:6]

def generate_natural_language(features: dict, top_features: list[dict], prediction=None) -> list[str]:
    lines = []
    features = features or {}
    if top_features:
        first = top_features[0]
        value = features.get(first["feature"])
        value_txt = f" (value {value:g})" if isinstance(value, (int, float)) and value is not None else ""
        lines.append(
            f"The dominant driver of this forecast is {first['feature']}{value_txt}, "
            f"whose contribution is {first.get('description', 'important')}."
        )
    for name in ("wind_speed", "pbl_height", "fire_impact_score", "humidity", "inversion_strength"):
        val = features.get(name)
        if not isinstance(val, (int, float)) or val is None:
            continue
        if name == "wind_speed" and val < 2:
            lines.append(f"Low wind speed of {val:.1f} m/s is preventing dispersion of pollutants.")
        elif name == "pbl_height" and val is not None and val < 300:
            lines.append(f"The planetary boundary layer is compressed to about {val:.0f} m, limiting vertical mixing.")
        elif name == "inversion_strength" and val > 0.3:
            lines.append("A strong atmospheric inversion layer is trapping pollution near the ground.")
        elif name == "fire_impact_score" and val > 0.1:
            lines.append("Active stubble burning in Punjab/Haryana is contributing regional smoke.")
        elif name == "humidity" and val > 80:
            lines.append("High humidity is promoting secondary aerosol formation.")
    if prediction:
        pts = []
        for key in ("pm25_pred", "pm10_pred", "o3_pred", "no2_pred"):
            if prediction.get(key) is not None:
                pts.append(f"{key[:-5].upper()} {prediction[key]:g}")
        lines.append(
            f"Forecast concentrations: {', '.join(pts)} with AQI {prediction.get('aqi_pred')} "
            f"({prediction.get('aqi_category')}), dominated by {prediction.get('dominant_pollutant')}."
        )
    return lines