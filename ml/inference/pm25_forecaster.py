"""Inference engine for the trained PM2.5 direct multi-horizon models.

Loads the artifacts written by ``ml.training.train_pm25`` and produces a 1..72h
forecast from a single feature row (features available at issuance time t).

Key conventions (must match training):
    - One XGBoost model per horizon (direct, no recursive chaining).
    - Feature columns and their ORDER come from ``config.json`` (saved at
      training time). Missing features are passed as NaN (XGBoost handles NaN
      with learned splits — same behaviour as training).
    - Baseline persistence = ``pm25_lag1`` (last observed value), identical for
      every horizon.
    - Uncertainty = split-conformal interval: per-horizon calibration quantile
      ``q`` from the validation residuals is applied as
      ``[pred - q, pred + q]``, clipped to the plausible [0, 1000] range.
      The coverage target/empirical coverage recorded at calibration time are
      exposed so the caller can report them honestly (no invented percentages).
"""

from __future__ import annotations

import json
import logging
import pathlib
from datetime import datetime, timedelta
from typing import Any

import joblib
import numpy as np

logger = logging.getLogger("pm25_forecaster")

PLAUSIBLE_RANGE = (0.0, 1000.0)

DEFAULT_CONFORMAL_FALLBACK = 60.0  # used ONLY if a model has no calibration file


class Pm25Forecaster:
    """Loads PM2.5 model artifacts and generates per-horizon forecasts."""

    def __init__(self, model_dir: str | pathlib.Path):
        self.model_dir = pathlib.Path(model_dir)
        self.config: dict[str, Any] = {}
        self.features: list[str] = []
        self.horizons: list[int] = []
        self.models: dict[int, Any] = {}
        self.conformal: dict[int, dict[str, Any]] = {}
        self.metrics: dict[int, dict[str, Any]] = {}
        self.load()

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self) -> None:
        cfg_path = self.model_dir / "config.json"
        if not cfg_path.exists():
            logger.warning("No config.json in %s (models not trained?)", self.model_dir)
            return
        with open(cfg_path, encoding="utf-8") as fp:
            self.config = json.load(fp)
        self.features = list(self.config.get("features", []))
        self.horizons = []

        for h in range(1, 73):
            h_dir = self.model_dir / f"h-{h}"
            model_path = h_dir / "model.joblib"
            if not model_path.exists():
                continue
            self.models[h] = joblib.load(model_path)
            self.horizons.append(h)

            conf_path = h_dir / "conformal.json"
            if conf_path.exists():
                with open(conf_path, encoding="utf-8") as fp:
                    self.conformal[h] = json.load(fp)
            else:
                self.conformal[h] = {
                    "quantile": DEFAULT_CONFORMAL_FALLBACK,
                    "method": "not-calibrated",
                    "coverage_target": None,
                    "empirical_coverage": None,
                    "n_calibration": 0,
                }

            met_path = h_dir / "metrics.json"
            if met_path.exists():
                with open(met_path, encoding="utf-8") as fp:
                    self.metrics[h] = json.load(fp)

        self.horizons.sort()
        if self.horizons:
            logger.info(
                "Pm25Forecaster loaded %d horizon models from %s "
                "(features=%d, max_horizon=%dh)",
                len(self.horizons), self.model_dir, len(self.features),
                max(self.horizons),
            )

    # ── Queries ──────────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return bool(self.config and self.models)

    @property
    def max_horizon(self) -> int:
        return max(self.horizons) if self.horizons else 0

    @property
    def uncertainty_method(self) -> str:
        return self.config.get(
            "uncertainty_method",
            "split-conformal (validation-calibrated; no invented confidence)",
        )

    @property
    def coverage_target(self) -> float | None:
        v = self.config.get("coverage")
        return v if isinstance(v, (int, float)) else None

    def conformal_quantile(self, horizon: int) -> float:
        conf = self.conformal.get(horizon)
        if not conf:
            return float(DEFAULT_CONFORMAL_FALLBACK)
        q = conf.get("quantile")
        return float(q) if isinstance(q, (int, float)) and np.isfinite(q) else float(DEFAULT_CONFORMAL_FALLBACK)

    def test_metrics(self, horizon: int) -> dict[str, Any]:
        """Honest held-out test metrics for a horizon (from metrics.json)."""
        met = self.metrics.get(horizon, {})
        return {
            "mae": met.get("test_metrics", {}).get("mae"),
            "rmse": met.get("test_metrics", {}).get("rmse"),
            "r2": met.get("test_metrics", {}).get("r2"),
            "n": met.get("test_metrics", {}).get("n"),
        }

    # ── Forecasting ──────────────────────────────────────────────────────────

    def _build_feature_vector(self, feature_row: dict[str, Any]) -> np.ndarray:
        """Order features exactly as trained; fill missing with NaN."""
        return np.asarray(
            [feature_row.get(f, np.nan) if feature_row.get(f) is not None else np.nan
             for f in self.features],
            dtype=float,
        ).reshape(1, -1)

    def forecast(
        self,
        feature_row: dict[str, Any],
        horizons: list[int] | None = None,
        base_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate a multi-horizon PM2.5 forecast from one feature row.

        ``feature_row`` must map feature names (from the model config) to values;
        missing keys become NaN. ``base_time`` defaults to now (naive UTC).

        Returns a dict with the full pipeline metadata plus a ``forecasts`` list:
        each entry has {forecast_horizon, timestamp, predicted_pm25,
        lower_bound, upper_bound, baseline_persistence}.
        """
        if not self.is_available:
            raise RuntimeError("PM2.5 models are not trained; cannot forecast")

        if horizons is None:
            horizons = self.horizons
        elif isinstance(horizons, int):
            horizons = [horizons]

        available = sorted(h for h in horizons if h in self.models)
        if not available:
            max_h = self.max_horizon
            raise ValueError(
                f"No trained model covers the requested horizons; trained up to {max_h}h"
            )

        if base_time is None:
            base_time = datetime.utcnow()
        if base_time.tzinfo is not None:  # normalise to naive UTC
            base_time = base_time.astimezone().replace(tzinfo=None)
        base_time = base_time.replace(minute=0, second=0, microsecond=0)

        x = self._build_feature_vector(feature_row)
        persist = feature_row.get("pm25_lag1", np.nan)

        forecasts = []
        for h in available:
            model = self.models[h]
            pred = float(np.ravel(model.predict(x))[0])
            if not np.isfinite(pred):
                pred = float(persist) if np.isfinite(persist) else 0.0
            q = self.conformal_quantile(h)
            lower = max(PLAUSIBLE_RANGE[0], pred - q)
            upper = min(PLAUSIBLE_RANGE[1], pred + q)
            forecasts.append({
                "forecast_horizon": h,
                "timestamp": (base_time + timedelta(hours=h)).isoformat() + "Z",
                "predicted_pm25": round(float(pred), 2),
                "pm25_lower_bound": round(float(lower), 2),
                "pm25_upper_bound": round(float(upper), 2),
                "baseline_persistence": round(float(persist), 2)
                if np.isfinite(persist) else None,
            })

        return {
            "model": "xgboost",
            "strategy": "direct multi-horizon per-hour XGBoost (one model per horizon)",
            "uncertainty_method": self.uncertainty_method,
            "coverage_target": self.coverage_target,
            "feature_version": self.config.get("trained_at"),
            "available_horizons": self.horizons,
            "forecasts": forecasts,
        }

    def summary(self) -> dict[str, Any]:
        """Human/API-facing model summary without running a forecast."""
        return {
            "model": "xgboost",
            "strategy": "direct multi-horizon per-hour XGBoost (one model per horizon)",
            "n_horizons": len(self.horizons),
            "horizons": self.horizons,
            "n_features": len(self.features),
            "uncertainty_method": self.uncertainty_method,
            "coverage_target": self.coverage_target,
            "model_dir": str(self.model_dir),
        }
