"""Compute REAL SHAP feature importances on the held-out test set.

For every evaluation horizon the script loads the deployed production XGBoost
model (``models/pm25/h-{h}/model.joblib``), takes the exact chronological test
rows used by ``evaluate_pm25`` (same valid mask), and computes mean |SHAP|
per feature across a deterministic sample of test rows. No importances are
inferred, borrowed, or hardcoded -- every number is ``shap.TreeExplainer`` on
the actual deployed model.

Outputs:
    models/pm25/shap_importance.json  - per-horizon SHAP tables + summary
    stdout tables                       - human-readable report
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("report_shap")

TARGET = "pm25"
HORIZONS = [1, 6, 12, 24, 48, 72]
DEFAULT_SAMPLE = 3000
RANDOM_SEED = 42


def run_report(
    csv_path: str | pathlib.Path,
    model_dir: str | pathlib.Path,
    horizons: list[int] | None = None,
    sample_size: int = DEFAULT_SAMPLE,
) -> dict:
    import shap

    t0 = time.time()
    csv_path = pathlib.Path(csv_path)
    model_dir = pathlib.Path(model_dir)
    horizons = horizons or HORIZONS

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

    per_horizon = {}
    for h in horizons:
        target_col = f"target_h{h}"
        valid_mask = df[target_col].notna() & df["pm25_lag1"].notna()
        test = df.loc[valid_mask & (df["split"] == "test")].copy()

        if len(test) <= sample_size:
            sample = test
        else:
            sample = test.sample(n=sample_size, random_state=RANDOM_SEED)
        sample = sample.sort_values(["station", "timestamp"])

        model_path = model_dir / f"h-{h}" / "model.joblib"
        if not model_path.exists():
            logger.warning("h-%d model missing; skipping", h)
            continue
        xgb = joblib.load(model_path)
        underlying = getattr(xgb, "model", xgb)

        X_test = sample[features].values.astype(float)
        y_true = sample[target_col].values.astype(float)
        y_pred = np.asarray(xgb.predict(X_test), dtype=float).ravel()

        explainer = shap.TreeExplainer(underlying)
        shap_values = np.asarray(explainer.shap_values(X_test))

        # Direction-aware per-feature stats (real SHAP values on real test rows)
        rows = []
        for i, name in enumerate(features):
            col = shap_values[:, i]
            rows.append({
                "feature": name,
                "mean_shap": round(float(np.mean(col)), 3),
                "mean_abs_shap": round(float(np.mean(np.abs(col))), 3),
                "mean_abs_share_pct": round(float(np.mean(np.abs(col)) / np.sum(np.mean(np.abs(shap_values), axis=0)) * 100.0), 2),
                "pct_rows_positive": round(float(np.mean(col > 0) * 100.0), 2),
                "pct_rows_negative": round(float(np.mean(col < 0) * 100.0), 2),
            })
        rows.sort(key=lambda r: r["mean_abs_shap"], reverse=True)

        mae = float(np.mean(np.abs(y_true - y_pred)))
        rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
        per_horizon[h] = {
            "horizon_hours": h,
            "model_path": str(model_path),
            "test_rows_sampled": int(len(sample)),
            "sampling": f"deterministic sample of up to {sample_size} chronological test rows (seed {RANDOM_SEED})"
            if len(sample) < len(test) else "full chronological test set",
            "test_period_start": str(sample["timestamp"].min()),
            "test_period_end": str(sample["timestamp"].max()),
            "deployed_metrics_on_sample": {"mae": round(mae, 2), "rmse": round(rmse, 2), "n": int(len(sample))},
            "feature_importance_by_mean_abs_shap": rows,
        }
        logger.info("h=%2dh explained on %d test rows (%.1fs)", h, len(sample), time.time() - t0)

    payload = {
        "schema_version": 1,
        "target": TARGET,
        "model_dir": str(model_dir),
        "data_source": str(csv_path),
        "method": "shap.TreeExplainer on the deployed XGBoost models; mean |SHAP| over deterministic test-sample rows",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "n_features": len(features),
        "features": features,
        "sample_size": sample_size,
        "random_seed": RANDOM_SEED,
        "horizons": per_horizon,
    }

    out_path = model_dir / "shap_importance.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    for h, info in per_horizon.items():
        print(f"\n=== Horizon {h}h (mean |SHAP| on {info['test_rows_sampled']} test rows) ===")
        for r in info["feature_importance_by_mean_abs_shap"][:12]:
            print(
                f"  {r['feature']:<28} mean|shap|={r['mean_abs_shap']:>8.2f} "
                f"share={r['mean_abs_share_pct']:>6.2f}%  mean_shap={r['mean_shap']:>8.2f}"
            )

    elapsed = time.time() - t0
    logger.info("Wrote %s in %.1fs", out_path, elapsed)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute real SHAP importance on the test set.")
    parser.add_argument("--data", default=pathlib.Path("data", "ml", "training_dataset.csv"))
    parser.add_argument("--model-dir", default=pathlib.Path("models", "pm25"))
    parser.add_argument("--horizons", default="1 6 12 24 48 72", help="Space-separated horizons")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE)
    args = parser.parse_args()
    horizons = [int(x.strip()) for x in args.horizons.split()]

    run_report(
        csv_path=args.data,
        model_dir=args.model_dir,
        horizons=horizons,
        sample_size=args.sample_size,
    )


if __name__ == "__main__":
    main()
