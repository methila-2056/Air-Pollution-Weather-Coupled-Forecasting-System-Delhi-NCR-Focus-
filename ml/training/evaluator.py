"""Model evaluation utilities for AeroCast-NCR.

Loads trained models and test data, computes metrics, generates
predicted vs actual data, computes per-category AQI accuracy, and
returns structured results.
"""

import os
from typing import Optional

import joblib
import numpy as np
import pandas as pd

from ..evaluation.metrics import compute_metrics, compute_aqi_category_accuracy, aqi_to_category


def evaluate_model(model, X_test: np.ndarray, y_test: np.ndarray) -> dict:
    """Evaluate a trained model on test data.

    Args:
        model: Trained model with predict() method.
        X_test: Feature matrix for test set.
        y_test: Actual target values.

    Returns:
        Dictionary of regression metrics.
    """
    y_pred = model.predict(X_test)
    return compute_metrics(y_test, y_pred)


def print_metrics(metrics: dict, label: str = "") -> None:
    """Pretty-print evaluation metrics."""
    prefix = f"[{label}] " if label else ""
    print(f"{prefix}MAE  : {metrics['mae']:.3f}")
    print(f"{prefix}RMSE : {metrics['rmse']:.3f}")
    print(f"{prefix}R2   : {metrics['r2']:.3f}")
    print(f"{prefix}MAPE : {metrics['mape']:.2f}%")
    if "nmae" in metrics:
        print(f"{prefix}nMAE : {metrics['nmae']:.4f}")


def generate_predicted_vs_actual(
    y_true: np.ndarray, y_pred: np.ndarray, timestamps: Optional[np.ndarray] = None
) -> pd.DataFrame:
    """Create a DataFrame of predicted vs actual values for frontend plotting.

    Args:
        y_true: Actual target values.
        y_pred: Predicted target values.
        timestamps: Optional timestamp array aligned with y_true/y_pred.

    Returns:
        DataFrame with columns: actual, predicted, timestamp (optional).
    """
    result = pd.DataFrame({"actual": y_true, "predicted": y_pred})
    result["residual"] = result["actual"] - result["predicted"]
    if timestamps is not None:
        result["timestamp"] = timestamps
    result.reset_index(drop=True, inplace=True)
    return result


def evaluate_aqi_categories(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute AQI category classification metrics.

    Args:
        y_true: Actual AQI values.
        y_pred: Predicted AQI values.

    Returns:
        Per-category precision, recall, F1, and overall accuracy.
    """
    return compute_aqi_category_accuracy(y_true, y_pred)


def save_predicted_vs_actual(df: pd.DataFrame, output_path: str) -> None:
    """Save predicted vs actual DataFrame to CSV."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved predicted vs actual data to {output_path}")


def full_evaluation(
    model,
    X_test: np.ndarray,
    y_test: np.ndarray,
    model_name: str = "unknown",
    target: str = "pm25",
    horizon: int = 1,
    timestamps: Optional[np.ndarray] = None,
    output_dir: Optional[str] = None,
) -> dict:
    """Run complete evaluation: metrics, category accuracy, save results.

    Args:
        model: Trained model.
        X_test: Test features.
        y_test: Test targets.
        model_name: Model identifier.
        target: Target variable.
        horizon: Forecast horizon in hours.
        timestamps: Optional timestamps for the test set.
        output_dir: Directory to save evaluation outputs.

    Returns:
        Structured evaluation result dictionary.
    """
    y_pred = model.predict(X_test)
    metrics = compute_metrics(y_test, y_pred)
    category_metrics = evaluate_aqi_categories(y_test, y_pred)

    print(f"\n--- Evaluation: {model_name} | {target} | t+{horizon}h ---")
    print_metrics(metrics, label=f"{target}_{horizon}h")

    result = {
        "model_name": model_name,
        "target": target,
        "horizon_hours": horizon,
        "n_samples": len(y_test),
        "metrics": metrics,
        "category_metrics": category_metrics,
    }

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        pva_df = generate_predicted_vs_actual(y_test, y_pred, timestamps)
        pva_path = os.path.join(output_dir, f"predicted_vs_actual_{target}_{horizon}h.csv")
        save_predicted_vs_actual(pva_df, pva_path)

    return result
