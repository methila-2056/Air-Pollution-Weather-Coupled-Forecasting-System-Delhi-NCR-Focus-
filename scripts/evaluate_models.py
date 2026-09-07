"""Re-evaluate every trained model from its persisted predicted-vs-actual CSV.

Scans models/predicted_vs_actual_*_*h.csv, recomputes regression metrics using
ml.evaluation.metrics, and writes a single models/metrics_eval_summary.json.

Usage:
    python -m scripts.evaluate_models [--models-dir models]
"""

import argparse
import glob
import json
import os
import re
import shutil

import pandas as pd

from ml.evaluation.metrics import compute_metrics


MODEL_DIR_DEFAULT = "models"


def parse_filename(path: str) -> tuple:
    base = os.path.basename(path)  # e.g. predicted_vs_actual_pm25_24h.csv
    m = re.match(r"predicted_vs_actual_([a-z0-9_]+)_(\d+)h\.csv$", base)
    if not m:
        return ("unknown", 0)
    return (m.group(1), int(m.group(2)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", default=MODEL_DIR_DEFAULT)
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.models_dir, "predicted_vs_actual_*.csv")))
    if not files:
        print(f"No predicted_vs_actual CSV files found under {args.models_dir!r}")
        raise SystemExit(1)

    summary = {"generated_by": "scripts.evaluate_models", "n_models": len(files), "results": []}
    for path in files:
        target, horizon = parse_filename(path)
        df = pd.read_csv(path)
        if "actual" not in df or "predicted" not in df:
            print(f"Skipping {path}: missing actual/predicted columns")
            continue
        metrics = compute_metrics(df["actual"].to_numpy(), df["predicted"].to_numpy())
        entry = {
            "target": target,
            "horizon_hours": horizon,
            "n_samples": int(len(df)),
            "mae": round(metrics["mae"], 4),
            "rmse": round(metrics["rmse"], 4),
            "r2": round(metrics["r2"], 4),
            "mape": round(metrics["mape"], 2),
            "nmae": round(metrics["nmae"], 4),
        }
        summary["results"].append(entry)
        print(
            f"{target:>5} {horizon:>3}h | MAE {entry['mae']:7.3f} | RMSE {entry['rmse']:7.3f} "
            f"| R2 {entry['r2']:6.3f} | MAPE {entry['mape']:5.1f}% | n={entry['n_samples']}"
        )

    out_path = os.path.join(args.models_dir, "metrics_eval_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()