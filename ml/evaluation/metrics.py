"""Comprehensive evaluation metrics for AeroCast-NCR.

Implements MAE, RMSE, R-squared, MAPE, nMAE, AQI category accuracy,
precision, recall, and F1. Provides functions to generate a full
evaluation report.
"""

import json
from typing import Optional

import numpy as np
import pandas as pd


AQI_BREAKPOINTS = [
    (0, 50, "Good"),
    (51, 100, "Satisfactory"),
    (101, 200, "Moderate"),
    (201, 300, "Poor"),
    (301, 400, "Very Poor"),
    (401, 500, "Severe"),
]


def compute_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def compute_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Coefficient of determination (R-squared)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 0.0
    return float(1 - (ss_res / ss_tot))


def compute_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Percentage Error (only where actual > 0)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = y_true > 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def compute_nmae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Normalized Mean Absolute Error (MAE / mean of actual)."""
    y_true = np.asarray(y_true, dtype=float)
    mean_true = np.mean(y_true)
    if mean_true == 0:
        return 0.0
    return float(compute_mae(y_true, y_pred) / mean_true)


def aqi_to_category(aqi: float) -> str:
    """Convert AQI value to category label."""
    if pd.isna(aqi):
        return "Unknown"
    aqi = max(0, aqi)
    for lo, hi, label in AQI_BREAKPOINTS:
        if lo <= aqi <= hi:
            return label
    return "Severe"


def compute_aqi_category_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute per-category accuracy, precision, recall, F1 for AQI classification.

    Args:
        y_true: Actual AQI values.
        y_pred: Predicted AQI values.

    Returns:
        Dictionary with per-category metrics and overall accuracy.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    true_cats = [aqi_to_category(v) for v in y_true]
    pred_cats = [aqi_to_category(v) for v in y_pred]

    all_categories = [label for _, _, label in AQI_BREAKPOINTS] + ["Unknown"]
    results = {}

    tp = {c: 0 for c in all_categories}
    fp = {c: 0 for c in all_categories}
    fn = {c: 0 for c in all_categories}

    correct = sum(1 for t, p in zip(true_cats, pred_cats) if t == p)
    total = len(true_cats)
    results["overall_accuracy"] = correct / total if total > 0 else 0.0

    for tc, pc in zip(true_cats, pred_cats):
        tp[tc] += 1
        if pc != tc:
            fp[pc] += 1
            fn[tc] += 1

    for cat in all_categories:
        precision = tp[cat] / (tp[cat] + fp[cat]) if (tp[cat] + fp[cat]) > 0 else 0.0
        recall = tp[cat] / (tp[cat] + fn[cat]) if (tp[cat] + fn[cat]) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        results[cat] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp[cat],
        }

    return results


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute all regression metrics at once.

    Returns:
        Dictionary with mae, rmse, r2, mape, nmae.
    """
    return {
        "mae": compute_mae(y_true, y_pred),
        "rmse": compute_rmse(y_true, y_pred),
        "r2": compute_r2(y_true, y_pred),
        "mape": compute_mape(y_true, y_pred),
        "nmae": compute_nmae(y_true, y_pred),
    }


def generate_evaluation_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str = "unknown",
    target: str = "pm25",
    horizon: int = 1,
    include_categories: bool = True,
) -> dict:
    """Generate a comprehensive evaluation report.

    Args:
        y_true: Actual values.
        y_pred: Predicted values.
        model_name: Name of the model.
        target: Target variable name.
        horizon: Forecast horizon in hours.
        include_categories: Whether to compute AQI category metrics.

    Returns:
        Structured report dictionary.
    """
    regression_metrics = compute_metrics(y_true, y_pred)

    report = {
        "model_name": model_name,
        "target": target,
        "horizon_hours": horizon,
        "n_samples": len(y_true),
        "regression_metrics": regression_metrics,
    }

    if include_categories:
        category_metrics = compute_aqi_category_accuracy(y_true, y_pred)
        report["category_metrics"] = category_metrics

    return report


def save_report(report: dict, output_path: str) -> None:
    """Save evaluation report as JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Saved evaluation report to {output_path}")
