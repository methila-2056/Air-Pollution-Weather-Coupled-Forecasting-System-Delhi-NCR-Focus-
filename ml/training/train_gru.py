"""Train direct-per-horizon GRU models for the PM2.5 forecasting system.

Each horizon ``h`` in ``{1, 6, 12, 24, 48, 72}`` gets its own GRU network
trained on the same chronological train split used by XGBoost. Windows ending
at or before the train/validation boundary are emitted; validation windows
drive early stopping. Test metrics are intentionally NOT computed here: the
evaluation pipeline (:mod:`ml.training.evaluate_pm25`) scores every model on
the identical held-out rows, so nothing can be fabricated at train time.

Artifacts written under ``model_dir/gru/``:

    preprocessing.json  - imputation medians + standardisation stats (train fit)
    config.json         - features, seq_len, horizons, hyperparameters
    h-{h}/model.joblib  - fitted GRUModel (wrapper contract: save/load/predict)
    h-{h}/metrics.json  - train/validation loss history + best epoch
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from ..models.gru_model import GRUModel
from .gru_sequences import apply_preprocess, build_windows, compute_run_ids, fit_preprocess_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("train_gru")

TARGET = "pm25"
GRU_HORIZONS = [1, 6, 12, 24, 48, 72]
DEFAULT_SEQ_LEN = 48
DEFAULT_GAP_THRESHOLD = 2.0
DEFAULT_GRU_PARAMS = {
    "hidden_size": 128,
    "num_layers": 2,
    "dropout": 0.1,
    "lr": 1e-3,
    "batch_size": 512,
    "max_epochs": 60,
    "patience": 12,
    "seed": 42,
}


def build_train_val_windows(
    df: pd.DataFrame,
    features: list[str],
    horizon: int,
    seq_len: int,
    run_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build train and validation window sets for one horizon.

    Returns:
        (X_train, y_train, X_val, y_val)
    """
    X_train, pos_train, y_train = build_windows(
        df, features, horizon, seq_len, "train", run_ids
    )
    X_val, pos_val, y_val = build_windows(
        df, features, horizon, seq_len, "validation", run_ids
    )
    logger.info(
        "h=%2dh windows: train=%d val=%d",
        horizon, len(X_train), len(X_val),
    )
    return X_train, y_train, X_val, y_val


def train_horizon_gru(
    df: pd.DataFrame,
    features: list[str],
    horizon: int,
    seq_len: int,
    run_ids: np.ndarray,
    gru_params: dict | None = None,
) -> GRUModel:
    """Train (and early-stop) a single GRU for the given horizon."""
    X_train, y_train, X_val, y_val = build_train_val_windows(
        df, features, horizon, seq_len, run_ids
    )
    if len(X_train) == 0:
        raise ValueError(f"horizon {horizon}: no training windows available")
    if len(X_val) == 0:
        raise ValueError(f"horizon {horizon}: no validation windows available")

    model = GRUModel(**(gru_params or DEFAULT_GRU_PARAMS))
    model.fit(X_train, y_train, X_val=X_val, y_val=y_val)
    logger.info(
        "h%dh trained: best_epoch=%s, val_mse=%.2f",
        horizon, model.best_epoch_,
        model.val_history_[model.best_epoch_ - 1] if model.best_epoch_ else float("nan"),
    )
    return model


def run_training(
    csv_path: str | pathlib.Path,
    model_dir: str | pathlib.Path,
    horizons: list[int] | None = None,
    seq_len: int = DEFAULT_SEQ_LEN,
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
    gru_params: dict | None = None,
) -> dict:
    """Train GRU models for all horizons and write artifacts under model_dir."""
    t0 = time.time()
    csv_path = pathlib.Path(csv_path)
    model_dir = pathlib.Path(model_dir).resolve()
    horizons = horizons or GRU_HORIZONS

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

    logger.info("Fitting preprocessing stats on train split only")
    stats = fit_preprocess_stats(df, features, splits=("train",))
    df = apply_preprocess(df, features, stats)

    run_ids = compute_run_ids(df, gap_threshold=gap_threshold)
    logger.info("Contiguous runs: %d", run_ids.max())

    gru_dir = model_dir / "gru"
    (gru_dir / "h-1").parent.mkdir(parents=True, exist_ok=True)

    trained = {}
    for h in horizons:
        logger.info("--- Training GRU for horizon %dh ---", h)
        model = train_horizon_gru(df, features, h, seq_len, run_ids, gru_params)

        h_dir = gru_dir / f"h-{h}"
        h_dir.mkdir(parents=True, exist_ok=True)
        model.save(h_dir / "model.joblib")
        model_meta = {
            "horizon_hours": h,
            "seq_len": seq_len,
            "best_epoch": model.best_epoch_,
            "train_history_mse": model.train_history_,
            "val_history_mse": model.val_history_,
            "params": gru_params or DEFAULT_GRU_PARAMS,
            "n_features": len(features),
        }
        with open(h_dir / "metrics.json", "w", encoding="utf-8") as fh:
            json.dump(model_meta, fh, indent=2)
        trained[h] = model
        logger.info("Saved h-%d artifacts", h)

    with open(gru_dir / "preprocessing.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2)
    with open(gru_dir / "config.json", "w", encoding="utf-8") as fh:
        json.dump(
            {
                "target": TARGET,
                "model_type": "gru",
                "horizons": horizons,
                "seq_len": seq_len,
                "gap_threshold_hours": gap_threshold,
                "features": features,
                "gru_params": gru_params or DEFAULT_GRU_PARAMS,
                "model_dir": str(gru_dir),
                "trained_at": pd.Timestamp.now("UTC").isoformat(),
            },
            fh,
            indent=2,
        )

    logger.info("GRU training complete in %.1fs", time.time() - t0)
    return {"horizons": horizons, "gru_dir": str(gru_dir), "trained": trained}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train GRU models for PM2.5 forecasting.")
    parser.add_argument("--data", default=pathlib.Path("data", "ml", "training_dataset.csv"))
    parser.add_argument("--model-dir", default=pathlib.Path("models", "pm25"))
    parser.add_argument("--horizons", default="1 6 12 24 48 72", help="Space-separated horizons")
    parser.add_argument("--seq-len", type=int, default=DEFAULT_SEQ_LEN)
    parser.add_argument("--hidden", type=int, default=DEFAULT_GRU_PARAMS["hidden_size"])
    parser.add_argument("--layers", type=int, default=DEFAULT_GRU_PARAMS["num_layers"])
    parser.add_argument("--epochs", type=int, default=DEFAULT_GRU_PARAMS["max_epochs"])
    parser.add_argument("--batch-size", type=int, default=DEFAULT_GRU_PARAMS["batch_size"])
    parser.add_argument("--lr", type=float, default=DEFAULT_GRU_PARAMS["lr"])
    args = parser.parse_args()

    horizons = [int(x) for x in args.horizons.split()]
    params = {
        **DEFAULT_GRU_PARAMS,
        "hidden_size": args.hidden,
        "num_layers": args.layers,
        "max_epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
    }
    run_training(
        csv_path=args.data,
        model_dir=args.model_dir,
        horizons=horizons,
        seq_len=args.seq_len,
        gru_params=params,
    )


if __name__ == "__main__":
    main()
