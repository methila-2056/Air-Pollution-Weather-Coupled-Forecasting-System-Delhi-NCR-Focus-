"""Model evaluation for the PM2.5 forecasting system.

Evaluates the deployed direct-per-horizon XGBoost models from models/pm25/
against baselines on the SAME chronological test rows:

  1. Persistence  - pm25_lag1 (naive reference)
  2. Random Forest - trained on the same train split with the same features
  3. XGBoost       - the actual deployed model (loaded from model_dir/h-{h})
  4. GRU           - optional trained sequential model (loaded from
                     model_dir/gru/h-{h}) with its train-only preprocessor

When the GRU artifacts exist, every model is scored on the identical subset of
test rows where a full sequential window is available (the GRU-valid rows),
so MAE/RMSE/R2 are directly comparable across all four models. No metric is
inferred; every number is computed directly from held-out predictions.

Outputs:
    models/pm25/evaluation.json  - structured model-performance dataset
    models/pm25/evaluation.csv   - flat table (model, horizon, mae, rmse, r2, n)
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import time

import joblib
import numpy as np
import pandas as pd

from ..models.gru_model import GRUModel
from ..models.random_forest_model import RandomForestModel
from .gru_sequences import apply_preprocess, build_windows, compute_run_ids
from .train_pm25 import _compute_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("evaluate_pm25")

TARGET = "pm25"
EVAL_HORIZONS = [1, 6, 12, 24, 48, 72]
RF_PARAMS = {"n_estimators": 150, "max_depth": 12, "n_jobs": -1}
DEFAULT_SEQ_LEN = 48
DEFAULT_GAP_THRESHOLD = 2.0


def _split_ranges(df: pd.DataFrame) -> dict[str, dict]:
    """Dataset-wide chronological time range for each split."""
    out = {}
    for split in ("train", "validation", "test"):
        sub = df[df["split"] == split]
        if sub.empty:
            out[split] = {"start": None, "end": None, "n_rows": 0}
            continue
        out[split] = {
            "start": str(sub["timestamp"].min()),
            "end": str(sub["timestamp"].max()),
            "n_rows": int(len(sub)),
        }
    return out


def evaluate_horizon(
    df: pd.DataFrame,
    features: list[str],
    horizon: int,
    xgb_model,
    rf_params: dict | None = None,
) -> dict:
    """Evaluate persistence, RF, and XGBoost for one horizon (no GRU).

    Uses the exact same valid rows in the test split for all three models.
    """
    rf_params = rf_params or RF_PARAMS
    target_col = f"target_h{horizon}"

    valid_mask = df[target_col].notna() & df["pm25_lag1"].notna()
    df_valid = df.loc[valid_mask].copy()

    train = df_valid[df_valid["split"] == "train"]
    test = df_valid[df_valid["split"] == "test"]

    if len(train) == 0:
        raise ValueError(f"horizon {horizon}: no train rows")
    if len(test) == 0:
        raise ValueError(f"horizon {horizon}: no test rows")

    X_train = train[features].values
    y_train = train[target_col].values
    X_test = test[features].values
    y_test = test[target_col].values

    persist = test["pm25_lag1"].values

    rf = RandomForestModel(**rf_params)
    rf.fit(X_train, y_train.ravel())
    rf_pred = np.asarray(rf.predict(X_test), dtype=float).ravel()

    xgb_pred = np.asarray(xgb_model.predict(X_test), dtype=float).ravel()

    return {
        "horizon_hours": horizon,
        "n_train": int(len(train)),
        "n_val": int(df_valid[df_valid["split"] == "validation"].shape[0]),
        "n_test": int(len(test)),
        "test_period_start": str(test["timestamp"].min()),
        "test_period_end": str(test["timestamp"].max()),
        "metrics": {
            "persistence": _compute_metrics(y_test, persist),
            "random_forest": _compute_metrics(y_test, rf_pred),
            "xgboost": _compute_metrics(y_test, xgb_pred),
        },
    }


def evaluate_horizon_with_gru(
    df: pd.DataFrame,
    df_gru: pd.DataFrame,
    features: list[str],
    horizon: int,
    seq_len: int,
    run_ids: np.ndarray,
    xgb_model,
    gru_model: GRUModel,
    rf_params: dict | None = None,
) -> dict:
    """Evaluate persistence, RF, XGBoost, and GRU on identical test rows.

    The evaluation row set is the set of test rows for which a full GRU
    window exists; XGBoost/RF/persistence are scored on exactly those same
    rows so the four models are directly comparable.
    """
    rf_params = rf_params or RF_PARAMS
    target_col = f"target_h{horizon}"

    # GRU-valid test positions (also used for the other three models)
    X_gru, positions, y_test = build_windows(
        df_gru, features, horizon, seq_len, "test", run_ids
    )
    if len(positions) == 0:
        raise ValueError(f"horizon {horizon}: no GRU-valid test windows")

    # Train split for RF (same chronological train rows as XGBoost)
    valid_mask = df[target_col].notna() & df["pm25_lag1"].notna()
    train = df.loc[valid_mask & (df["split"] == "train")].copy()
    if len(train) == 0:
        raise ValueError(f"horizon {horizon}: no train rows")

    X_train = train[features].values
    y_train = train[target_col].values

    rf = RandomForestModel(**rf_params)
    rf.fit(X_train, y_train.ravel())

    X_test = df[features].iloc[positions].values
    persist = df["pm25_lag1"].iloc[positions].values.astype(float)

    rf_pred = np.asarray(rf.predict(X_test), dtype=float).ravel()
    xgb_pred = np.asarray(xgb_model.predict(X_test), dtype=float).ravel()
    gru_pred = np.asarray(gru_model.predict(X_gru), dtype=float).ravel()

    test_period_start = str(df["timestamp"].iloc[positions].min())
    test_period_end = str(df["timestamp"].iloc[positions].max())

    return {
        "horizon_hours": horizon,
        "n_train": int(len(train)),
        "n_val": int(df.loc[valid_mask & (df["split"] == "validation")].shape[0]),
        "n_test": int(len(positions)),
        "test_period_start": test_period_start,
        "test_period_end": test_period_end,
        "metrics": {
            "persistence": _compute_metrics(y_test, persist),
            "random_forest": _compute_metrics(y_test, rf_pred),
            "xgboost": _compute_metrics(y_test, xgb_pred),
            "gru": _compute_metrics(y_test, gru_pred),
        },
    }


def run_evaluation(
    csv_path: str | pathlib.Path,
    model_dir: str | pathlib.Path,
    horizons: list[int] | None = None,
    output_path: str | pathlib.Path | None = None,
    csv_output_path: str | pathlib.Path | None = None,
    rf_params: dict | None = None,
    seq_len: int = DEFAULT_SEQ_LEN,
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
    include_gru: bool = True,
) -> dict:
    """End-to-end model evaluation; writes evaluation.json and evaluation.csv."""
    t0 = time.time()
    csv_path = pathlib.Path(csv_path)
    model_dir = pathlib.Path(model_dir)
    horizons = horizons or EVAL_HORIZONS

    logger.info("Loading dataset: %s", csv_path)
    df = pd.read_csv(csv_path, parse_dates=["timestamp", "hour"])
    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))

    config_path = model_dir / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"config.json not found in {model_dir}")
    with open(config_path, encoding="utf-8") as fh:
        config = json.load(fh)
    features = list(config["features"])
    logger.info("Features from config: %d", len(features))

    for h in horizons:
        target_col = f"target_h{h}"
        if target_col not in df.columns:
            df[target_col] = df.groupby("station")[TARGET].shift(-h)

    df = df.sort_values(["station", "timestamp"]).reset_index(drop=True)

    # Optional GRU evaluation: load preprocessor + run ids
    gru_dir = model_dir / "gru"
    gru_available = include_gru and (gru_dir / "config.json").exists()
    df_gru: pd.DataFrame | None = None
    run_ids: np.ndarray | None = None
    seq_len_from_artifacts = seq_len
    if gru_available:
        try:
            with open(gru_dir / "preprocessing.json", encoding="utf-8") as fh:
                stats = json.load(fh)
            with open(gru_dir / "config.json", encoding="utf-8") as fh:
                gru_config = json.load(fh)
            seq_len_from_artifacts = int(gru_config.get("seq_len", seq_len))
            gap_threshold = float(gru_config.get("gap_threshold_hours", gap_threshold))
            df_gru = apply_preprocess(df, features, stats)
            run_ids = compute_run_ids(df, gap_threshold=gap_threshold)
            logger.info("GRU eval enabled (seq_len=%d, gap=%.1fh)", seq_len_from_artifacts, gap_threshold)
        except FileNotFoundError:
            logger.warning("GRU artifacts incomplete; skipping GRU evaluation")
            gru_available = False

    split_ranges = _split_ranges(df)

    results = []
    for h in horizons:
        model_path = model_dir / f"h-{h}" / "model.joblib"
        if not model_path.exists():
            logger.warning("h-%d model.joblib missing (%s); skipping", h, model_path)
            continue
        logger.info("--- Evaluating horizon %dh ---", h)
        xgb_model = joblib.load(model_path)

        gru_model = None
        if gru_available:
            gru_model_path = gru_dir / f"h-{h}" / "model.joblib"
            if not gru_model_path.exists():
                logger.warning("h-%d gru model missing; skipping GRU for this horizon", h)
                gru_model = None
            else:
                gru_model = GRUModel.load(gru_model_path)

        if gru_model is not None and df_gru is not None and run_ids is not None:
            res = evaluate_horizon_with_gru(
                df, df_gru, features, h, seq_len_from_artifacts, run_ids,
                xgb_model, gru_model, rf_params=rf_params,
            )
        else:
            res = evaluate_horizon(df, features, h, xgb_model, rf_params=rf_params)

        results.append(res)
        for model_name, m in res["metrics"].items():
            logger.info(
                "  h=%2dh %-13s MAE=%.3f RMSE=%.3f R2=%.4f (n=%d)",
                h, model_name, m["mae"], m["rmse"], m["r2"], m["n"],
            )

    evaluated_models = sorted(results[0]["metrics"].keys()) if results else []
    payload = {
        "schema_version": 1,
        "target": TARGET,
        "model_dir": str(model_dir),
        "data_source": str(csv_path),
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "feature_count": len(features),
        "features": features,
        "horizons": horizons,
        "evaluated_models": evaluated_models,
        "split_type": "chronological",
        "split_ratios": config.get("split_ratios"),
        "split_ranges": split_ranges,
        "results": results,
    }

    output_path = output_path or (model_dir / "evaluation.json")
    csv_output_path = csv_output_path or (model_dir / "evaluation.csv")
    output_path = pathlib.Path(output_path)
    csv_output_path = pathlib.Path(csv_output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    rows = [
        {
            "model": model,
            "horizon_hours": int(res["horizon_hours"]),
            "mae": m["mae"],
            "rmse": m["rmse"],
            "r2": m["r2"],
            "mape": m.get("mape"),
            "n_samples": int(res["n_test"]),
            "test_period_start": res["test_period_start"],
            "test_period_end": res["test_period_end"],
        }
        for res in results
        for model, m in res["metrics"].items()
    ]
    pd.DataFrame(rows).to_csv(csv_output_path, index=False)

    logger.info("Wrote %s and %s in %.1fs", output_path, csv_output_path, time.time() - t0)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PM2.5 forecasting models.")
    parser.add_argument("--data", default=pathlib.Path("data", "ml", "training_dataset.csv"))
    parser.add_argument("--model-dir", default=pathlib.Path("models", "pm25"))
    parser.add_argument("--horizons", default="1 6 12 24 48 72", help="Space-separated horizons")
    parser.add_argument("--no-gru", action="store_true", help="Skip GRU evaluation")
    args = parser.parse_args()
    horizons = [int(x.strip()) for x in args.horizons.split()]

    run_evaluation(
        csv_path=args.data,
        model_dir=args.model_dir,
        horizons=horizons,
        include_gru=not args.no_gru,
    )


if __name__ == "__main__":
    main()
