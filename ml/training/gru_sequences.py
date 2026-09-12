"""Sequence building and preprocessing utilities for the GRU model.

Provides split-safe, leakage-free sliding-window extraction over the pooled
hourly station panel and preprocessing transforms (imputation, standardization)
fitted exclusively on the training split.

Window convention
-----------------
A window that predicts `pm25[t+h]` for a row at timestamp `t` occupies
``df[p - seq_len + 1 : p + 1]`` (the row at `p` *is* the row at `t`). The
label `target_h{h}` lives at position `p`. All feature values in the window
precede or coincide with `t`, matching what an operational forecaster would
have seen at issuance time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Run-id computation (contiguous-hour detection)
# ---------------------------------------------------------------------------

def compute_run_ids(df: pd.DataFrame, gap_threshold: float = 2.0) -> np.ndarray:
    """Assign a contiguous-run id within each station.

    A new run begins whenever the gap to the previous row (within the same
    station) exceeds `gap_threshold` hours, or the row is the first for its
    station.

    Args:
        df: The training dataset sorted by (station, timestamp).
        gap_threshold: Maximum allowable gap in hours between successive rows
            within the same run.

    Returns:
        Integer array of length ``len(df)`` with a run id (globally unique).
    """
    result = np.zeros(len(df), dtype=np.int64)
    gid = 0
    prev_station = None
    prev_ts = None

    for i, (station, ts) in enumerate(
        zip(df["station"], df["timestamp"], strict=True)
    ):
        if station != prev_station or prev_ts is None:
            gid += 1
        elif (ts - prev_ts).total_seconds() / 3600.0 > gap_threshold:
            gid += 1
        result[i] = gid
        prev_station = station
        prev_ts = ts
    return result


# ---------------------------------------------------------------------------
# Preprocessing (fit on train only)
# ---------------------------------------------------------------------------

def fit_preprocess_stats(
    df: pd.DataFrame,
    features: list[str],
    splits: tuple[str, ...] = ("train",),
) -> dict:
    """Compute imputation medians and standardisation statistics on train rows.

    NaN imputation:
        1. Forward-fill per station (causal: uses only past observations).
        2. Remaining NaN filled with the train-split per-feature median.

    Standardisation:
        Per-feature z-score computed on the imputed train-split rows.

    Returns:
        dict with keys ``medians``, ``mean``, ``std``, ``features``.
    """
    mask = df["split"].isin(splits)
    train_df = df.loc[mask, features].copy()

    # 1. per-station forward-fill (done on a small subset for speed; the
    #    full dataset is filled later in apply_preprocess_stats)
    for col in train_df.columns:
        train_df[col] = pd.to_numeric(train_df[col], errors="coerce")
    train_df = train_df.ffill()

    medians = train_df.median()
    mean = train_df.mean()
    std = train_df.std(ddof=0)
    std = std.replace(0, 1)  # prevent division by zero for constant cols

    return {
        "medians": medians.to_dict(),
        "mean": mean.to_dict(),
        "std": std.to_dict(),
        "features": features,
    }


def apply_preprocess(
    df: pd.DataFrame,
    features: list[str],
    stats: dict,
) -> pd.DataFrame:
    """Impute and standardise features in-place (returns a copy).

    Applies the same steps as :func:`fit_preprocess_stats` but uses the
    already-fitted statistics rather than computing new ones.
    """
    out = df.copy()

    # Forward-fill per station using the full dataset
    for col in features:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out[features] = out.groupby("station")[features].ffill()

    # Fill residual NaN with train medians
    for col in features:
        remaining = out[col].isna()
        if remaining.any():
            out.loc[remaining, col] = stats["medians"].get(col, 0.0)

    # Standardise
    mean = pd.Series(stats["mean"])
    std = pd.Series(stats["std"])
    out[features] = (out[features] - mean) / std

    return out


# ---------------------------------------------------------------------------
# Window building
# ---------------------------------------------------------------------------

def build_windows(
    df: pd.DataFrame,
    features: list[str],
    horizon: int,
    seq_len: int,
    split: str,
    run_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build sliding windows of shape (n, seq_len, n_features) for one horizon.

    Only windows whose *last* row is in the requested split, has a valid
    target, and has the full preceding ``seq_len - 1`` contiguous history are
    returned. The caller evaluates all competing models on exactly these rows.

    Args:
        df: Preprocessed DataFrame (imputed + standardised).
        features: Ordered list of feature columns to use.
        horizon: Forecast horizon ``h`` (the row at position ``p`` has target
            ``pm25[t+h]``).
        seq_len: Length of the look-back window in hours.
        split: One of ``"train"``, ``"validation"``, ``"test"``.
        run_ids: Precomputed contiguous-run ids of length ``len(df)``.

    Returns:
        X_windows: np.ndarray of shape (n, seq_len, n_features).
        positions: np.ndarray of int – df-row indices corresponding to each
            window's last row (the label row at time ``t``).
        labels: np.ndarray – values of ``target_h{h}`` at those rows.
    """
    target_col = f"target_h{horizon}"

    n_features = len(features)
    positions: list[int] = []
    X_list: list[np.ndarray] = []

    for i in range(len(df)):
        # Fast filters (skip candidate quickly)
        if df["split"].iloc[i] != split:
            continue
        if pd.isna(df[target_col].iloc[i]) or pd.isna(df["pm25_lag1"].iloc[i]):
            continue
        # Window must fit within the contiguous run
        if i < seq_len - 1:
            continue
        if run_ids[i - seq_len + 1] != run_ids[i]:
            continue

        window_rows = df.iloc[i - seq_len + 1 : i + 1][features].values
        # All values should now be finite (preprocess applied earlier)
        if not np.all(np.isfinite(window_rows)):
            continue

        X_list.append(window_rows)
        positions.append(i)

    if not positions:
        return (
            np.empty((0, seq_len, n_features), dtype=np.float32),
            np.array([], dtype=np.int64),
            np.array([], dtype=np.float32),
        )

    X = np.stack(X_list).astype(np.float32)
    positions = np.array(positions, dtype=np.int64)
    labels = df[target_col].iloc[positions].values.astype(np.float32)
    return X, positions, labels
