"""Training pipeline for AeroCast-NCR.

Loads the featured dataset, defines multi-horizon targets for pollutants,
performs chronological (time-based) train/val/test splitting,
trains Persistence Baseline, Random Forest, and XGBoost models per
horizon per pollutant, saves models/metrics/importances.
"""

import json
import os
from datetime import datetime
from typing import Optional

import joblib
import numpy as np
import pandas as pd

from ..evaluation.metrics import compute_metrics, generate_evaluation_report
from ..models.xgboost_model import XGBoostModel
from ..models.random_forest_model import RandomForestModel
from ..models.persistence_baseline import PersistenceBaseline

HORIZONS = [1, 6, 12, 24, 48, 72]
ALL_POLLUTANTS = ["pm25", "pm10", "o3", "no2"]

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")
DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "processed", "featured_dataset.csv"
)


def load_featured_data(path: str = DEFAULT_DATA_PATH) -> pd.DataFrame:
    """Load the featured dataset."""
    print(f"Loading featured dataset from {path} ...")
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df.dropna(subset=["timestamp"], inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    print(f"  Loaded {len(df)} rows, {len(df.columns)} columns")
    return df


def get_feature_columns(df: pd.DataFrame) -> list:
    """Determine feature columns by excluding targets (current pollutant levels),
    metadata columns, and calendar/season columns that duplicate information."""
    exclude = {
        "pm25", "pm10", "o3", "no2", "so2", "co", "aqi",
        "timestamp", "station", "outlier_flags", "weather_outlier_flags",
    }
    return [
        c for c in df.columns
        if c not in exclude
        and df[c].dtype in ("float64", "float32", "int64", "int32", "int")
    ]


def create_target_columns(df: pd.DataFrame, pollutant: str, horizons: list = HORIZONS) -> pd.DataFrame:
    """Create future-observation target columns for each forecast horizon.

    Targets are shifted *within each station's time series* so that a row
    (station S, time T) is labelled with S's own observation at T+h — never
    another station's reading at the same hour.
    """
    df = df.copy()
    if "station" in df.columns:
        grouped = df.groupby("station", group_keys=False)[pollutant]
        for h in horizons:
            df[f"target_{pollutant}_t+{h}"] = grouped.shift(-h)
    else:
        for h in horizons:
            df[f"target_{pollutant}_t+{h}"] = df[pollutant].shift(-h)
    return df


def chronological_split_by_time(
    df: pd.DataFrame,
    train_ratio: float = 0.60,
    val_ratio: float = 0.15,
) -> tuple:
    """Chronological train/val/test split by time (no leakage).

    Data must be sorted chronologically. The time axis (across all stations)
    is divided so that later observations are never used for training.
    """
    times = df["timestamp"]
    t0, t1 = times.min(), times.max()
    span = (t1 - t0).total_seconds()

    train_cut = t0 + pd.Timedelta(seconds=span * train_ratio)
    val_cut = t0 + pd.Timedelta(seconds=span * (train_ratio + val_ratio))

    train = df[times <= train_cut].copy()
    val = df[(times > train_cut) & (times <= val_cut)].copy()
    test = df[times > val_cut].copy()

    print(f"  Time range : {t0} -> {t1}")
    print(f"  Train cut  : {train_cut}  ({len(train)} rows)")
    print(f"  Val   cut  : {val_cut}  ({len(val)} rows)")
    print(f"  Test       : {len(test)} rows")

    return train, val, test


def train_single_model(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    model_type: str,
    horizon: int,
    feature_names: Optional[list] = None,
) -> tuple:
    """Train a single model and return (model_wrapper, val_metrics)."""
    if model_type == "persistence":
        model = PersistenceBaseline(horizon=horizon)
    elif model_type == "random_forest":
        model = RandomForestModel(n_estimators=150, max_depth=12)
    elif model_type == "xgboost":
        model = XGBoostModel(
            n_estimators=250, max_depth=7, learning_rate=0.08,
            subsample=0.8, colsample_bytree=0.8,
        )
    else:
        raise ValueError(f"Unknown model type: {model_type}")

    model.fit(X_train, y_train)
    if feature_names is not None:
        model.feature_names_ = list(feature_names)
    y_val_pred = model.predict(X_val)
    val_metrics = compute_metrics(y_val, y_val_pred)
    return model, val_metrics


def save_model(model, model_type: str, target: str, horizon: int, model_dir: str) -> str:
    """Save trained model wrapper to disk using joblib.

    Persists the full wrapper (has `.predict`) and, when available, the
    underlying estimator's feature names in a sidecar JSON for inference.
    """
    os.makedirs(model_dir, exist_ok=True)
    filename = f"{model_type}_{target}_{horizon}h.joblib"
    path = os.path.join(model_dir, filename)

    payload = {"type": model_type, "target": target, "horizon": horizon, "model": model}
    joblib.dump(payload, path)

    meta = {"target": target, "horizon": horizon, "trained_at": datetime.utcnow().isoformat()}
    meta_path = path.replace(".joblib", ".json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return path


def save_feature_importance(model, model_type: str, target: str, horizon: int,
                            feature_names: list, output_dir: str) -> Optional[str]:
    """Save feature importances to CSV (tree-based models only)."""
    if model_type == "persistence":
        return None
    try:
        importances = model.feature_importances()
        df_imp = pd.DataFrame([
            {"feature": f, "importance": importances.get(f, 0.0)}
            for f in feature_names
        ])
        df_imp.sort_values("importance", ascending=False, inplace=True)
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"feature_importance_{target}_{horizon}h.csv")
        df_imp.to_csv(path, index=False)
        return path
    except Exception:
        return None


def train_all(
    data_path: str = DEFAULT_DATA_PATH,
    model_dir: str = MODEL_DIR,
    model_types: Optional[list] = None,
    horizons: Optional[list] = None,
    targets: Optional[list] = None,
) -> dict:
    """Full training pipeline for all models, horizons, and pollutants.

    Args:
        data_path: Path to featured_dataset.csv.
        model_dir: Directory to save models and metrics.
        model_types: List of model types to train.
        horizons: Forecast horizons.
        targets: Pollutants to forecast (defaults to pm25 only).
    """
    model_types = model_types or ["persistence", "random_forest", "xgboost"]
    horizons = horizons or HORIZONS
    targets = targets or ["pm25"]

    os.makedirs(model_dir, exist_ok=True)

    df = load_featured_data(data_path)
    feature_cols = get_feature_columns(df)
    print(f"  Using {len(feature_cols)} feature columns")

    all_results = {}
    all_metrics_summary = []

    for target in targets:
        print(f"\n{'#'*70}")
        print(f"TARGET POLLUTANT: {target.upper()}")
        print(f"{'#'*70}")

        valid_range = df[df[target].notna()]
        if valid_range.empty:
            print(f"  No {target} observations available. Skipping.")
            continue
        print(f"  {target} observations: {len(valid_range)} rows")

        df_t = create_target_columns(df, target, horizons)
        df_t = df_t[df_t[target].notna()]
        df_t = df_t.dropna(subset=feature_cols, how="all")
        df_t = df_t.sort_values("timestamp").reset_index(drop=True)

        train_df, val_df, test_df = chronological_split_by_time(df_t)

        for model_type in model_types:
            print(f"\n  --- Model: {model_type.upper()} ---")

            for horizon in horizons:
                target_col = f"target_{target}_t+{horizon}"
                if target_col not in train_df.columns:
                    print(f"    Skipping t+{horizon}h: target column not found")
                    continue

                X_train = train_df[feature_cols].fillna(0).values
                X_val = val_df[feature_cols].fillna(0).values
                X_test = test_df[feature_cols].fillna(0).values
                y_train = train_df[target_col].values
                y_val = val_df[target_col].values
                y_test = test_df[target_col].values

                valid_train = ~(np.isnan(y_train))
                valid_val = ~(np.isnan(y_val))
                valid_test = ~(np.isnan(y_test))

                X_tr, y_tr = X_train[valid_train], y_train[valid_train]
                X_v, y_v = X_val[valid_val], y_val[valid_val]
                X_te, y_te = X_test[valid_test], y_test[valid_test]

                if len(y_tr) < 100 or len(y_te) < 10:
                    print(f"    Skipping t+{horizon}h: insufficient data "
                          f"(train={len(y_tr)}, test={len(y_te)})")
                    continue

                print(f"    t+{horizon}h: train={len(y_tr)}, val={len(y_v)}, test={len(y_te)}")

                model, val_metrics = train_single_model(
                    X_tr, y_tr, X_v, y_v, model_type, horizon, feature_names=feature_cols
                )
                print(f"      Val  MAE={val_metrics['mae']:.2f} RMSE={val_metrics['rmse']:.2f} R2={val_metrics['r2']:.3f}")

                y_test_pred = model.predict(X_te)
                test_metrics = compute_metrics(y_te, y_test_pred)
                print(f"      Test MAE={test_metrics['mae']:.2f} RMSE={test_metrics['rmse']:.2f} R2={test_metrics['r2']:.3f} MAPE={test_metrics['mape']:.1f}%")

                path = save_model(model, model_type, target, horizon, model_dir)
                save_feature_importance(model, model_type, target, horizon, feature_cols, model_dir)

                pva_df = pd.DataFrame({
                    "actual": y_te,
                    "predicted": y_test_pred,
                    "timestamp": test_df.loc[valid_test, "timestamp"].values,
                })
                pva_path = os.path.join(model_dir, f"predicted_vs_actual_{target}_{horizon}h.csv")
                pva_df.to_csv(pva_path, index=False)

                all_results[(model_type, target, horizon)] = {
                    "val_metrics": val_metrics,
                    "test_metrics": test_metrics,
                    "n_train": len(y_tr),
                    "n_val": len(y_v),
                    "n_test": len(y_te),
                }

                all_metrics_summary.append({
                    "model": model_type,
                    "target": target,
                    "horizon": horizon,
                    "test_mae": test_metrics["mae"],
                    "test_rmse": test_metrics["rmse"],
                    "test_r2": test_metrics["r2"],
                    "test_mape": test_metrics["mape"],
                    "val_mae": val_metrics["mae"],
                    "n_train": len(y_tr),
                    "n_test": len(y_te),
                })

    metrics_path = os.path.join(model_dir, "metrics.json")
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            new_keys = {(e["model"], e["target"], e["horizon"]) for e in all_metrics_summary}
            all_metrics_summary = [
                e for e in existing if (e.get("model"), e.get("target"), e.get("horizon")) not in new_keys
            ] + all_metrics_summary
        except Exception:
            pass
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(all_metrics_summary, f, indent=2, default=str)
    print(f"\nSaved metrics summary to {metrics_path}")

    print("\n" + "=" * 70)
    print("TRAINING COMPLETE - SUMMARY (Test set)")
    print("=" * 70)
    for entry in all_metrics_summary:
        print(f"  {entry['model']:14s} | {entry['target']:5s} | t+{entry['horizon']:2d}h | "
              f"MAE={entry['test_mae']:.2f} | RMSE={entry['test_rmse']:.2f} | "
              f"R2={entry['test_r2']:.3f} | MAPE={entry['test_mape']:.1f}%")

    return all_results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train AeroCast-NCR models.")
    parser.add_argument("--data-path", default=DEFAULT_DATA_PATH)
    parser.add_argument("--model-dir", default=MODEL_DIR)
    parser.add_argument("--models", nargs="*", default=None,
                        help="Model types: persistence, random_forest, xgboost")
    parser.add_argument("--targets", nargs="*", default=None,
                        help="Pollutants: pm25 pm10 o3 no2")
    parser.add_argument("--horizons", nargs="*", type=int, default=None,
                        help="Forecast horizons in hours")
    args = parser.parse_args()

    train_all(
        data_path=args.data_path,
        model_dir=args.model_dir,
        model_types=args.models,
        targets=args.targets,
        horizons=args.horizons,
    )