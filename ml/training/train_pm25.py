"""Train PM2.5 forecasting models: persistence baseline + direct multi-horizon XGBoost.

Conventions:
    - Strategy: *direct per-horizon* — one independent XGBoost model per forecast
      horizon h. No recursive chaining; each model uses only features available at
      the issuance hour t (the latest known observations).
    - Split: *chronological* — rows are assigned to train/validation/test by
      production timestamp, never shuffled. The `split` column in the dataset
      identifies the split; validation is used for early stopping and conformal
      calibration.
    - Targets: pm25[t+h] where h is the horizon; samples where the target falls
      outside the available rows are dropped (NaN target). Label overlap between
      train/validation at period boundaries is acceptable since it does NOT
      introduce information leakage (input features are the same regardless of
      where the label lands).
    - Features: *no random permutation*; all NaN/constant columns across the
      training frame are dropped and recorded in config. Feature ordering is
      stored in the saved config so inference reproduces the same column order.
    - Baseline: Persistence — pm25_lag1 (last observed value at t-1). Compared
      against every horizon to establish the naive reference.
    - Uncertainty: Split-conformal prediction intervals on validation residuals.
      Coverage target configurable (default 85%). The quantile of |y - yhat|
      residuals on the validation set is stored; the same fixed-width interval
      is applied to all forecasts for a given horizon. Honest calibration is
      guaranteed on the validation set; we make NO claim about online coverage.
    - All metrics reported here are *test-set* metrics (the held-out period).
      Training/validation metrics are never printed as results.
    - `models/pm25/` directory layout per horizon:
        h-{h}/model.joblib       — fitted XGBoost model
        h-{h}/metrics.json       — MAE, RMSE, R², MAPE, nMAE, persistence metrics
        h-{h}/conformal.json     — calibration quantile, coverage target, n_cal
      Root:
        config.json              — feature list, horizons, params, meta
        persistence_metrics.json — average persistence metrics across horizons
        training_predictions.csv — per-horizon test predictions for audit
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("train_pm25")

# ─────────────────────────────────────────────────────────────────────────────
# Canonical feature pool — matches columns produced by the training dataset
# pipeline exactly.  Columns not present in a given dataset snapshot are skipped;
# columns that are all-NaN or constant across the training split are dropped
# and recorded in config.json.
# ─────────────────────────────────────────────────────────────────────────────

EXOGENOUS_FEATURES: list[str] = [
    # Meteorology
    "temperature", "humidity", "pressure_msl", "surface_pressure",
    "wind_speed", "wind_direction", "wind_dir_sin", "wind_dir_cos",
    "pbl_height", "ventilation_coefficient",
    # Inversion / atmospheric stability
    "inversion_detected", "inversion_strength", "strongest_layer_gradient",
    # Fire
    "fire_count", "fire_impact_score", "nearest_fire_distance",
    "wind_aligned_fire_count", "wind_alignment_pct", "transport_time_hours",
    "transport_risk", "stubble_impact_score",
]

TEMPORAL_FEATURES: list[str] = [
    "hour_of_day", "day_of_week", "month", "day_of_year", "is_weekend",
    "hour_sin", "hour_cos", "dayofweek_sin", "dayofweek_cos",
    "month_sin", "month_cos",
]

PM25_HISTORY_FEATURES: list[str] = [
    "pm25_lag1", "pm25_lag3", "pm25_lag6", "pm25_lag12", "pm25_lag24",
    "pm25_roll_mean_3h", "pm25_roll_std_3h",
    "pm25_roll_mean_6h", "pm25_roll_std_6h",
    "pm25_roll_mean_12h", "pm25_roll_std_12h",
    "pm25_roll_mean_24h", "pm25_roll_std_24h",
]

CANDIDATE_FEATURES = EXOGENOUS_FEATURES + TEMPORAL_FEATURES + PM25_HISTORY_FEATURES

# Strings / metadata — never fed to the model
_DROP_COLUMNS: set[str] = {
    "station_id", "timestamp", "pm25", "station", "hour",
    "latitude", "longitude", "split",
    "inversion_category", "inversion_source",
    "temperature_1000hPa", "temperature_925hPa",
    "temperature_850hPa", "temperature_700hPa",
    "ventilation_norm", "inversion_profile_available",
    "transport_risk_level",
    # Outlier flags — diagnostic only, not predictive
    "outlier_temperature", "outlier_humidity", "outlier_pressure_msl",
    "outlier_surface_pressure", "outlier_wind_speed",
    "outlier_wind_direction", "outlier_pbl_height",
    "outlier_ventilation_coefficient", "outlier_inversion_strength",
    "outlier_strongest_layer_gradient", "outlier_fire_count",
    "outlier_fire_impact_score", "outlier_nearest_fire_distance",
    "outlier_wind_aligned_fire_count", "outlier_wind_alignment_pct",
    "outlier_transport_time_hours", "outlier_transport_risk",
    "outlier_stubble_impact_score", "outlier_pm25",
}

# ─────────────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_HORIZONS: list[int] = [1, 3, 6, 12, 24]
FULL_HORIZONS: list[int] = list(range(1, 73))  # 1..72 for task-2
DEFAULT_COVERAGE: float = 0.85

TARGET = "pm25"

DEFAULT_XGB_PARAMS: dict[str, Any] = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.06,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 2,
    "reg_lambda": 1.0,
    "reg_alpha": 0.0,
    "tree_method": "hist",
    "verbosity": 0,
    "n_jobs": -1,
}

DEFAULT_TEST_MAX_ROWS: int | None = None  # None = use all


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_outlier_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("outlier_")]


def _resolve_candidate_features(df: pd.DataFrame) -> list[str]:
    """Return the intersection of candidate features present in df."""
    return [f for f in CANDIDATE_FEATURES if f in df.columns]


def _select_features(
    df: pd.DataFrame,
    candidates: list[str] | None = None,
    drop: set[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Determine usable feature columns from the training frame.

    Returns (features, dropped_reasons) where dropped_reasons maps column name
    to the reason it was excluded.
    """
    if candidates is None:
        candidates = _resolve_candidate_features(df)
    if drop is None:
        drop = _DROP_COLUMNS

    features: list[str] = []
    reasons: dict[str, str] = {}

    for col in candidates:
        if col in drop:
            reasons[col] = "in drop set"
            continue
        if col not in df.columns:
            reasons[col] = "not in dataset"
            continue
        vals = df[col]
        if vals.isna().all():
            reasons[col] = "all NaN"
            continue
        nunique = vals.nunique(dropna=True)
        if nunique <= 1:
            reasons[col] = f"constant (nunique={nunique})"
            continue
        features.append(col)

    return features, reasons


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Honest test-set metrics (MAE, RMSE, R², MAPE, nMAE)."""
    y_true = np.ravel(y_true)
    y_pred = np.ravel(y_pred)
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    yt = y_true[valid]
    yp = y_pred[valid]
    if len(yt) == 0:
        return {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "mape": np.nan, "nmae": np.nan, "n": 0}
    mae = float(mean_absolute_error(yt, yp))
    mse = float(mean_squared_error(yt, yp))
    rmse = float(np.sqrt(mse))
    r2 = float(r2_score(yt, yp))
    nonzero = yt != 0
    mape = float(np.mean(np.abs((yt[nonzero] - yp[nonzero]) / yt[nonzero])) * 100) if nonzero.any() else np.nan
    mean_obs = float(np.mean(yt))
    nmae = mae / mean_obs if mean_obs > 0 else np.nan
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2": round(r2, 4),
        "mape": round(mape, 4) if not np.isnan(mape) else None,
        "nmae": round(nmae, 4) if not np.isnan(nmae) else None,
        "n": int(len(yt)),
    }


def _conformal_quantile(
    residuals: np.ndarray,
    coverage: float = 0.85,
) -> dict[str, Any]:
    """Split-conformal calibration: conservative quantile of absolute residuals.

    Uses the formula: q = quantile at level ceil((n+1)*C) / n to guarantee
    at least nominal coverage on the calibration (validation) set.
    """
    valid = residuals[np.isfinite(residuals)]
    n = len(valid)
    if n == 0:
        return {"quantile": np.nan, "coverage_target": coverage, "n_calibration": 0, "method": "split-conformal"}
    level = min(1.0, (n + 1) * coverage / n)
    q = float(np.quantile(valid, level, method="higher"))
    empirical_coverage = float(np.mean(valid <= q))
    return {
        "quantile": round(q, 4),
        "coverage_target": coverage,
        "empirical_coverage": round(empirical_coverage, 4),
        "n_calibration": n,
        "method": "split-conformal",
    }


def _parse_horizon_arg(arg: str) -> list[int]:
    """Parse horizon argument: '1 3 6 12 24' or '1..72'."""
    arg = arg.strip()
    if ".." in arg:
        parts = arg.split("..", 1)
        lo, hi = int(parts[0]), int(parts[1])
        return list(range(lo, hi + 1))
    return [int(x.strip()) for x in arg.split()]


# ─────────────────────────────────────────────────────────────────────────────
# Core training
# ─────────────────────────────────────────────────────────────────────────────


def train_horizon(
    df: pd.DataFrame,
    features: list[str],
    horizon: int,
    xgb_params: dict[str, Any],
    early_stopping_rounds: int = 25,
    conformal_coverage: float = DEFAULT_COVERAGE,
) -> dict[str, Any]:
    """Train one XGBoost model for a single horizon; return model + metrics dict.

    Returns dict with keys:
        model         — fitted XGBRegressor
        test_pred     — np.ndarray of test predictions
        test_metrics  — dict (MAE, RMSE, R², ...)
        val_pred      — np.ndarray of validation predictions (for conformal)
        persistence_test_metrics
        persistence_val_metrics
        target_col    — str, e.g. "target_h1"
        n_train / n_val / n_test  — int
    """
    target_col = f"target_h{horizon}"
    if target_col not in df.columns:
        raise ValueError(f"Target column {target_col} not found in dataset")

    # Rows where the target AND the last-known observation (pm25_lag1, used for
    # the persistence baseline) are available. Feature columns may contain NaN
    # (e.g. PBL height was missing historically); XGBoost learns NaN-aware
    # splits natively, so we do NOT drop rows for missing features. This keeps
    # the XGBoost and persistence baselines on the exact same test rows.
    valid_mask = df[target_col].notna() & df["pm25_lag1"].notna()
    df_valid = df.loc[valid_mask].copy()

    train = df_valid[df_valid["split"] == "train"]
    val   = df_valid[df_valid["split"] == "validation"]
    test  = df_valid[df_valid["split"] == "test"]

    X_train = train[features].values
    y_train = train[target_col].values
    X_val   = val[features].values
    y_val   = val[target_col].values
    X_test  = test[features].values
    y_test  = test[target_col].values

    # Persistence baseline: predict pm25_lag1 for every sample
    persist_test = test["pm25_lag1"].values
    persist_val  = val["pm25_lag1"].values

    persistence_test_metrics = _compute_metrics(y_test, persist_test)
    persistence_val_metrics  = _compute_metrics(y_val, persist_val)

    if len(val) == 0:
        raise ValueError(
            f"Horizon {horizon}: no validation rows. Cannot use early stopping "
            "or conformal calibration. Check that the validation split exists."
        )

    if len(X_train) == 0:
        raise ValueError(f"Horizon {horizon}: no training samples (all features/targets NaN)")

    # XGBoost
    params = {**xgb_params}
    model = xgb.XGBRegressor(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    # Early stopping info
    best_iter = getattr(model, "best_iteration", None)

    # Predictions. NOTE: XGBoost returns a (0,0) array for empty input, so we
    # handle empty test/val before predicting to keep arrays 1-D.
    test_pred = model.predict(X_test)
    val_pred  = model.predict(X_val)
    if test_pred.ndim > 1:
        test_pred = test_pred.ravel()
    if val_pred.ndim > 1:
        val_pred = val_pred.ravel()

    test_metrics = _compute_metrics(y_test, test_pred)
    val_metrics  = _compute_metrics(y_val, val_pred)

    # Conformal calibration on validation residuals
    val_residuals = np.abs(y_val - val_pred)
    conformal = _conformal_quantile(val_residuals, coverage=conformal_coverage)

    return {
        "model": model,
        "test_pred": test_pred,
        "test_metrics": test_metrics,
        "val_pred": val_pred,
        "val_metrics": val_metrics,
        "persistence_test_metrics": persistence_test_metrics,
        "persistence_val_metrics": persistence_val_metrics,
        "target_col": target_col,
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "n_test": int(len(test)),
        "best_iteration": best_iter,
        "conformal": conformal,
        "test_idx": test.index.tolist(),
    }


def run_training(
    csv_path: str | pathlib.Path,
    horizons: list[int],
    model_dir: str | pathlib.Path,
    coverage: float = DEFAULT_COVERAGE,
    max_test_rows: int | None = DEFAULT_TEST_MAX_ROWS,
    xgb_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """End-to-end training pipeline.

    Reads the built dataset CSV, trains persistence + XGBoost per horizon,
    saves artifacts, prints honest test-set metrics.

    Returns a summary dict with all horizon results.
    """
    if xgb_params is None:
        xgb_params = DEFAULT_XGB_PARAMS
    csv_path = pathlib.Path(csv_path)
    model_dir = pathlib.Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    logger.info("Loading dataset: %s", csv_path)
    df = pd.read_csv(csv_path, parse_dates=["timestamp", "hour"])
    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))

    if max_test_rows is not None and max_test_rows < len(df):
        # Quick diagnostic mode: keep a strided sample across the FULL timeline
        # so train/validation/test splits all remain populated (head() would
        # truncate to the train period only). Features were already computed at
        # build time, so striding preserves their semantics.
        stride = max(1, len(df) // max_test_rows)
        df = df.iloc[::stride].reset_index(drop=True)
        logger.info("Diagnostic mode: kept every %d-th row (%d rows)", stride, len(df))

    # Feature selection
    features, dropped = _select_features(df)
    logger.info("Usable features: %d | Dropped: %d", len(features), len(dropped))
    for col, reason in dropped.items():
        logger.info("  DROP %s -> %s", col, reason)

    # Split stats
    split_counts = df["split"].value_counts().to_dict()
    logger.info("Split distribution: %s", split_counts)

    # Station stats
    station_counts = df["station"].value_counts().to_dict()
    logger.info("Stations: %d | Per-station rows: %s", len(station_counts), station_counts)

    # Time range
    time_range = {
        "start": str(df["timestamp"].min()),
        "end": str(df["timestamp"].max()),
    }
    logger.info("Time range: %s to %s", time_range["start"], time_range["end"])

    # ── Generate multi-horizon targets (per-station forward shift) ──────────

    df = df.sort_values(["station", "timestamp"]).reset_index(drop=True)
    for h in horizons:
        target_col = f"target_h{h}"
        if target_col not in df.columns:
            df[target_col] = df.groupby("station")[TARGET].shift(-h)
    logger.info("Target columns created for horizons: %s", horizons)

    # ── Train per horizon ────────────────────────────────────────────────────

    results: dict[str, Any] = {}
    all_test_preds: list[pd.DataFrame] = []

    for h in horizons:
        target_col = f"target_h{h}"
        if target_col not in df.columns:
            logger.warning("Target %s not in dataset (horizon %dh skipped)", target_col, h)
            continue

        logger.info("--- Training horizon %dh ---", h)
        t_h0 = time.time()
        res = train_horizon(df, features, h, xgb_params, conformal_coverage=coverage)

        # Save model
        h_dir = model_dir / f"h-{h}"
        h_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(res["model"], h_dir / "model.joblib")

        # Save metrics
        metrics_payload = {
            "horizon_hours": h,
            "features": features,
            "n_features": len(features),
            "n_train": res["n_train"],
            "n_val": res["n_val"],
            "n_test": res["n_test"],
            "test_metrics": res["test_metrics"],
            "val_metrics": res["val_metrics"],
            "persistence_test": res["persistence_test_metrics"],
            "persistence_val": res["persistence_val_metrics"],
            "conformal": res["conformal"],
            "best_iteration": res["best_iteration"],
            "xgb_params": xgb_params,
        }
        with open(h_dir / "metrics.json", "w", encoding="utf-8") as fp:
            json.dump(metrics_payload, fp, indent=2)

        # Save conformal data
        with open(h_dir / "conformal.json", "w", encoding="utf-8") as fp:
            json.dump(res["conformal"], fp, indent=2)

        t_h = time.time() - t_h0
        logger.info(
            "h=%2dh  test_MAE=%.3f  RMSE=%.3f  R2=%.4f  persist_MAE=%.3f  "
            "conformal_q=%.3f  time=%.1fs",
            h,
            res["test_metrics"]["mae"],
            res["test_metrics"]["rmse"],
            res["test_metrics"]["r2"],
            res["persistence_test_metrics"]["mae"],
            res["conformal"]["quantile"],
            t_h,
        )

        results[h] = {
            "test_metrics": res["test_metrics"],
            "persistence_test": res["persistence_test_metrics"],
            "conformal": res["conformal"],
        }

        # Collect test predictions for audit CSV
        test_idx = res["test_idx"]
        preds_df = pd.DataFrame({
            "station": df.loc[test_idx, "station"].values,
            "timestamp": df.loc[test_idx, "timestamp"].values,
            "horizon_hours": h,
            "actual_pm25": df.loc[test_idx, target_col].values,
            "predicted_pm25_xgb": res["test_pred"],
            "predicted_pm25_persist": df.loc[test_idx, "pm25_lag1"].values,
        })
        all_test_preds.append(preds_df)

    # ── Save config ──────────────────────────────────────────────────────────

    config = {
        "target": "pm25",
        "horizons": horizons,
        "features": features,
        "n_features": len(features),
        "dropped_features": dropped,
        "coverage": coverage,
        "split_ratios": [0.60, 0.20, 0.20],
        "split_names": ["train", "validation", "test"],
        "chronological_split": True,
        "shuffle": False,
        "sample_convention": (
            "Row at time t contains features (exogenous + pm25 history lags/rolling) "
            "available at t; target = pm25[t+h]. No pm25[t] used as a feature."
        ),
        "strategy": "direct per-horizon — one independent XGB model per horizon, no recursive chaining",
        "uncertainty_method": (
            "Split-conformal: fixed-width interval [|y-hat| quantile on validation residuals] "
            "applied per-horizon. Coverage is calibrated on the validation set only."
        ),
        "xgb_params": xgb_params,
        "data_source": str(csv_path),
        "n_rows": len(df),
        "time_range": time_range,
        "stations": list(station_counts.keys()),
        "split_counts": split_counts,
        "persistence_baseline": (
            "pm25_lag1: last observed PM2.5 at t-1, constant across all horizons. "
            "Used as the naive reference for every forecast horizon."
        ),
        "model_dir": str(model_dir),
        "trained_at": pd.Timestamp.now("UTC").isoformat(),
    }
    with open(model_dir / "config.json", "w", encoding="utf-8") as fp:
        json.dump(config, fp, indent=2)

    # ── Save test predictions audit CSV ──────────────────────────────────────

    if all_test_preds:
        all_preds_df = pd.concat(all_test_preds, ignore_index=True)
        all_preds_df.to_csv(model_dir / "training_predictions.csv", index=False)
        logger.info("Saved training_predictions.csv (%d rows)", len(all_preds_df))

    # ── Summary ──────────────────────────────────────────────────────────────

    elapsed = time.time() - t0
    logger.info("Training complete in %.1fs -> %s", elapsed, model_dir)

    # Print summary table
    logger.info("=" * 78)
    logger.info("TEST-SET METRICS (honest - test split, never used during training)")
    logger.info("=" * 78)
    logger.info(
        "%4s | %8s %8s %7s | %8s | %9s",
        "h", "MAE", "RMSE", "R2", "pMAE", "conformal_q",
    )
    logger.info("-" * 78)
    for h, r in results.items():
        t = r["test_metrics"]
        p = r["persistence_test"]
        c = r["conformal"]
        logger.info(
            "%4dh | %8.3f %8.3f %7.4f | %8.3f | %9.4f",
            h, t["mae"], t["rmse"], t["r2"], p["mae"], c["quantile"],
        )
    logger.info("=" * 78)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train PM2.5 forecasting models (persistence + XGBoost).",
    )
    parser.add_argument(
        "--data",
        default=os.path.join("data", "ml", "training_dataset.csv"),
        help="Path to the training dataset CSV (default: data/ml/training_dataset.csv)",
    )
    parser.add_argument(
        "--model-dir",
        default=os.path.join("models", "pm25"),
        help="Directory to save trained models (default: models/pm25)",
    )
    parser.add_argument(
        "--horizons",
        default=" ".join(map(str, DEFAULT_HORIZONS)),
        help="Space-separated horizons or range like '1..72' (default: '1 3 6 12 24')",
    )
    parser.add_argument(
        "--max-test-rows",
        type=int,
        default=None,
        help="Cap total rows for quick diagnostics (default: None = full dataset)",
    )
    parser.add_argument(
        "--coverage",
        type=float,
        default=DEFAULT_COVERAGE,
        help=f"Conformal coverage target (default: {DEFAULT_COVERAGE})",
    )
    args = parser.parse_args()
    horizons = _parse_horizon_arg(args.horizons)
    logger.info("Horizons: %s (%d models)", horizons, len(horizons))

    run_training(
        csv_path=args.data,
        horizons=horizons,
        model_dir=args.model_dir,
        coverage=args.coverage,
        max_test_rows=args.max_test_rows,
    )


if __name__ == "__main__":
    main()
