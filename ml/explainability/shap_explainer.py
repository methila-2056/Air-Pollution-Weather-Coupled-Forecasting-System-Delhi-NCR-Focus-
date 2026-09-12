"""SHAP-based explainability for the production PM2.5 XGBoost forecast models.

Every contribution returned here is computed with ``shap.TreeExplainer`` on the
*actual deployed* XGBoost model (``models/pm25/h-{h}/model.joblib``). Nothing is
hardcoded: a "positive driver" is a feature whose real SHAP value pushes the
prediction above the model's expected value (``base_value``); a "negative
driver" pushes it below. Percentages are ``|shap_i| / sum(|shap|)`` — real
SHAP maths, not fabricated weights.

For a single forecast row the feature vector is built in the exact order of
``config.json`` (identical to the training/evaluation pipeline), and the same
NaN convention as forecasting applies (missing values stay NaN — XGBoost has
learned split direction for them).
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import joblib
import numpy as np

logger = logging.getLogger("pm25_shap_explainer")

#: Neutral, factual meaning of each feature (no invented causality).
FEATURE_MEANING = {
    "temperature": "Surface air temperature (degC)",
    "humidity": "Relative humidity (%)",
    "pressure_msl": "Mean-sea-level pressure (hPa)",
    "surface_pressure": "Surface pressure (hPa)",
    "wind_speed": "Wind speed (m/s)",
    "wind_direction": "Wind direction (deg)",
    "wind_dir_sin": "Wind direction (sine component)",
    "wind_dir_cos": "Wind direction (cosine component)",
    "pbl_height": "Planetary boundary layer height (m)",
    "ventilation_coefficient": "Ventilation coefficient (wind x PBL)",
    "inversion_detected": "Atmospheric inversion flag (0/1)",
    "inversion_strength": "Inversion strength (degC / distance)",
    "fire_count": "Detected fires in trailing window",
    "fire_impact_score": "Fire impact score (plume weighting)",
    "nearest_fire_distance": "Distance to nearest detected fire (km)",
    "wind_aligned_fire_count": "Fires aligned with transport wind",
    "wind_alignment_pct": "Share of fires aligned with wind (%)",
    "transport_time_hours": "Advection time from fire region (h)",
    "transport_risk": "Transport risk from fires (0-1)",
    "stubble_impact_score": "Stubble-burning impact score",
    "hour_of_day": "Hour of day (0-23)",
    "day_of_week": "Day of week (0-6)",
    "month": "Month of year (1-12)",
    "day_of_year": "Day of year (1-366)",
    "is_weekend": "Weekend flag (0/1)",
    "hour_sin": "Hour of day (sin encoding)",
    "hour_cos": "Hour of day (cos encoding)",
    "dayofweek_sin": "Day of week (sin encoding)",
    "dayofweek_cos": "Day of week (cos encoding)",
    "month_sin": "Month (sin encoding)",
    "month_cos": "Month (cos encoding)",
    "pm25_lag1": "PM2.5 one hour ago (persistence value)",
    "pm25_lag3": "PM2.5 three hours ago",
    "pm25_lag6": "PM2.5 six hours ago",
    "pm25_lag12": "PM2.5 twelve hours ago",
    "pm25_lag24": "PM2.5 twenty-four hours ago",
    "pm25_roll_mean_3h": "PM2.5 rolling mean (3h)",
    "pm25_roll_std_3h": "PM2.5 rolling std (3h)",
    "pm25_roll_mean_6h": "PM2.5 rolling mean (6h)",
    "pm25_roll_std_6h": "PM2.5 rolling std (6h)",
    "pm25_roll_mean_12h": "PM2.5 rolling mean (12h)",
    "pm25_roll_std_12h": "PM2.5 rolling std (12h)",
    "pm25_roll_mean_24h": "PM2.5 rolling mean (24h)",
    "pm25_roll_std_24h": "PM2.5 rolling std (24h)",
}


def _clean_value(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return f


class Pm25ShapExplainer:
    """Loads the production XGBoost model for a horizon and explains rows."""

    def __init__(self, model_dir: str | pathlib.Path):
        self.model_dir = pathlib.Path(model_dir)
        config_path = self.model_dir / "config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"No config.json in {self.model_dir}")
        with open(config_path, encoding="utf-8") as fp:
            self.config = json.load(fp)
        self.features: list[str] = list(self.config.get("features", []))
        self._models: dict[int, Any] = {}
        self._explainers: dict[int, Any] = {}

    # ── Loading ──────────────────────────────────────────────────────────────

    def _model(self, horizon: int):
        """Return the loaded production XGBoostModel wrapper for a horizon."""
        if horizon in self._models:
            return self._models[horizon]
        path = self.model_dir / f"h-{horizon}" / "model.joblib"
        if not path.exists():
            raise FileNotFoundError(f"No trained XGBoost model for horizon {horizon}h at {path}")
        model = joblib.load(path)
        underlying = getattr(model, "model", model)
        if not hasattr(underlying, "predict"):
            raise TypeError(f"model at {path} does not look like the XGBoost wrapper")
        self._models[horizon] = model
        return model

    def _explainer(self, horizon: int):
        """Memoised TreeExplainer over the underlying XGBRegressor."""
        if horizon not in self._explainers:
            import shap
            model = self._model(horizon)
            underlying = getattr(model, "model", model)
            self._explainers[horizon] = shap.TreeExplainer(underlying)
        return self._explainers[horizon]

    def is_trained(self, horizon: int) -> bool:
        return (self.model_dir / f"h-{horizon}" / "model.joblib").exists()

    # ── Vectorisation ────────────────────────────────────────────────────────

    def build_vector(self, feature_row: dict[str, Any]) -> np.ndarray:
        """Order features exactly as trained; missing keys become NaN."""
        return np.asarray(
            [feature_row.get(f, np.nan) if feature_row.get(f) is not None else np.nan
             for f in self.features],
            dtype=float,
        ).reshape(1, -1)

    # ── Explanation ──────────────────────────────────────────────────────────

    def explain_row(
        self,
        feature_row: dict[str, Any],
        horizon: int,
        prediction: float | None = None,
    ) -> dict[str, Any]:
        """Compute per-feature SHAP contributions for one forecast row.

        Returns a flat, JSON-ready dict with ``top_positive_drivers`` and
        ``top_negative_drivers`` (model-derived, never hardcoded).
        """
        model = self._model(horizon)
        explainer = self._explainer(horizon)
        x = self.build_vector(feature_row)

        if prediction is None:
            prediction = float(np.ravel(model.predict(x))[0])

        shap_values = np.asarray(explainer.shap_values(x)).reshape(-1)
        if shap_values.shape[0] != len(self.features):
            raise RuntimeError(
                f"SHAP returned {shap_values.shape[0]} values for {len(self.features)} features "
                f"(horizon {horizon}h)"
            )

        base_value = float(explainer.expected_value)
        total_abs = float(np.sum(np.abs(shap_values))) or 1.0

        contributions = []
        for i, name in enumerate(self.features):
            sv = float(shap_values[i])
            value = _clean_value(feature_row.get(name))
            contributions.append({
                "feature": name,
                "value": value,
                "shap_value": round(sv, 2),
                "share_of_abs_contributions_pct": round(abs(sv) / total_abs * 100.0, 2),
                "direction": "positive" if sv > 0 else ("negative" if sv < 0 else "zero"),
                "description": FEATURE_MEANING.get(name, name),
            })

        positive = sorted(
            (c for c in contributions if c["direction"] == "positive"),
            key=lambda c: c["shap_value"], reverse=True,
        )
        negative = sorted(
            (c for c in contributions if c["direction"] == "negative"),
            key=lambda c: c["shap_value"],  # ascending: most negative first
        )
        by_magnitude = sorted(contributions, key=lambda c: abs(c["shap_value"]), reverse=True)

        delta = prediction - base_value
        if delta > 1e-6:
            summary = (
                f"PM2.5 is expected to INCREASE from the model base of {base_value:.1f} "
                f"to {prediction:.1f} across the {horizon}h horizon (net +{delta:.1f}); "
                "positive drivers outweigh negative drivers."
            )
        elif delta < -1e-6:
            summary = (
                f"PM2.5 is expected to DECREASE from the model base of {base_value:.1f} "
                f"to {prediction:.1f} across the {horizon}h horizon (net {delta:.1f}); "
                "negative drivers outweigh positive drivers."
            )
        else:
            summary = (
                f"PM2.5 is expected to stay near the model base of {base_value:.1f} "
                f"(predicted {prediction:.1f}) across the {horizon}h horizon."
            )

        return {
            "model": "xgboost",
            "explanation_method": "shap.TreeExplainer (exact tree SHAP on the deployed model)",
            "horizon_hours": horizon,
            "base_value": round(base_value, 2),
            "forecast_pm25": round(float(prediction), 2),
            "n_features": len(self.features),
            "summary": summary,
            "top_positive_drivers": positive,
            "top_negative_drivers": negative,
            "contributions_by_magnitude": by_magnitude,
        }
