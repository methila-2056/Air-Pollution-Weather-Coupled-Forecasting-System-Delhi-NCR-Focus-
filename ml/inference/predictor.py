"""Real-time prediction engine for AeroCast-NCR.

Loads trained models, accepts latest feature vectors, generates 72-hour
PM2.5 forecasts with confidence estimation based on model uncertainty.
"""

import glob
import os
from typing import Optional

import joblib
import numpy as np
import pandas as pd

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")
HORIZONS = [1, 6, 12, 24, 48, 72]


class Predictor:
    """Multi-horizon PM2.5 prediction engine.

    Loads trained models for each forecast horizon and generates
    72-hour forecasts with confidence intervals.
    """

    def __init__(self, model_type: str = "xgboost", model_dir: str = MODEL_DIR):
        """Initialize predictor.

        Args:
            model_type: Model type to load (xgboost, random_forest).
            model_dir: Directory containing saved model files.
        """
        self.model_type = model_type
        self.model_dir = model_dir
        self.models = {}
        self._load_models()

    def _load_models(self) -> None:
        """Load all available models for the configured model type."""
        for horizon in HORIZONS:
            path = os.path.join(
                self.model_dir,
                f"{self.model_type}_pm25_{horizon}h.joblib",
            )
            if os.path.exists(path):
                try:
                    self.models[horizon] = joblib.load(path)
                    print(f"  Loaded {self.model_type} model for t+{horizon}h")
                except Exception as e:
                    print(f"  Failed to load model for t+{horizon}h: {e}")
            else:
                print(f"  No model found for t+{horizon}h at {path}")

    def predict_single(self, features: np.ndarray, horizon: int) -> Optional[float]:
        """Generate a single prediction for a given horizon.

        Args:
            features: Feature vector (1D array or list).
            horizon: Forecast horizon in hours.

        Returns:
            Predicted PM2.5 value, or None if model unavailable.
        """
        if horizon not in self.models:
            return None
        model = self.models[horizon]
        arr = np.array(features).reshape(1, -1) if np.ndim(features) == 1 else np.array(features)
        try:
            pred = model.predict(arr)
            return float(pred[0])
        except Exception:
            return None

    def forecast_72h(self, latest_features: np.ndarray) -> dict:
        """Generate full 72-hour PM2.5 forecast.

        Args:
            latest_features: Current feature vector.

        Returns:
            Dictionary with keys: horizons, predictions, timestamps, confidence.
        """
        predictions = {}
        for horizon in HORIZONS:
            pred = self.predict_single(latest_features, horizon)
            predictions[horizon] = pred

        now = pd.Timestamp.now(tz="UTC")
        timestamps = {h: now + pd.Timedelta(hours=h) for h in HORIZONS}

        confidence = self._estimate_confidence(predictions)

        return {
            "horizons": HORIZONS,
            "predictions": predictions,
            "timestamps": timestamps,
            "confidence": confidence,
            "model_type": self.model_type,
        }

    def _estimate_confidence(self, predictions: dict) -> dict:
        """Estimate confidence for each horizon based on model agreement.

        Uses the spread between nearby horizons as a proxy for uncertainty.
        Shorter horizons generally have higher confidence.

        Returns:
            Dictionary mapping horizon to confidence score (0-1).
        """
        confidence = {}
        horizons_sorted = sorted(predictions.keys())

        for i, h in enumerate(horizons_sorted):
            pred = predictions[h]
            if pred is None:
                confidence[h] = 0.0
                continue

            base_confidence = max(0.3, 1.0 - (h / 100.0))

            neighbors = []
            if i > 0 and predictions[horizons_sorted[i - 1]] is not None:
                neighbors.append(predictions[horizons_sorted[i - 1]])
            if i < len(horizons_sorted) - 1 and predictions[horizons_sorted[i + 1]] is not None:
                neighbors.append(predictions[horizons_sorted[i + 1]])

            if neighbors:
                spread = max(abs(pred - n) for n in neighbors)
                spread_penalty = min(0.3, spread / 500.0)
                base_confidence -= spread_penalty

            confidence[h] = round(max(0.1, min(1.0, base_confidence)), 3)

        return confidence

    def predict_from_dataframe(self, df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
        """Generate predictions for each row in a DataFrame.

        Args:
            df: DataFrame with feature columns.
            feature_cols: List of column names to use as features.

        Returns:
            DataFrame with timestamp and prediction columns for each horizon.
        """
        results = pd.DataFrame()
        if "timestamp" in df.columns:
            results["timestamp"] = df["timestamp"]

        for horizon in HORIZONS:
            if horizon not in self.models:
                results[f"pm25_t+{horizon}"] = np.nan
                results[f"confidence_t+{horizon}"] = 0.0
                continue

            model = self.models[horizon]
            available_cols = [c for c in feature_cols if c in df.columns]
            X = df[available_cols].values

            try:
                preds = model.predict(X)
                results[f"pm25_t+{horizon}"] = preds
                results[f"confidence_t+{horizon}"] = self._base_confidence(horizon)
            except Exception:
                results[f"pm25_t+{horizon}"] = np.nan
                results[f"confidence_t+{horizon}"] = 0.0

        return results

    def _base_confidence(self, horizon: int) -> float:
        """Return base confidence for a horizon (no neighbor info)."""
        return round(max(0.3, 1.0 - (horizon / 100.0)), 3)

    @property
    def available_horizons(self) -> list:
        """List of horizons with loaded models."""
        return sorted(self.models.keys())

    @property
    def is_ready(self) -> bool:
        """True if at least one model is loaded."""
        return len(self.models) > 0
