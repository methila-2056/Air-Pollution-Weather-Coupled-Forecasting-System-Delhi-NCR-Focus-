"""Model performance service: loads the measured performance dataset.

Reads models/{target}/evaluation.json (written by ml/training/evaluate_pm25.py)
and returns it as a validated ModelPerformanceResponse. Every metric in the
file is computed from held-out (unseen) chronological test predictions - the
service performs no calculation, so nothing can be fabricated at request time.
"""

from __future__ import annotations

import json
import os
import pathlib

from ..schemas.schemas import ModelPerformanceResponse
from ..utils.helpers import repo_root

DEFAULT_MODEL_DIR = repo_root() / "models"
ALL_POLLUTANTS = ("pm25", "pm10", "o3", "no2", "so2", "co")


def get_evaluation_path(target: str = "pm25") -> pathlib.Path:
    model_dir = pathlib.Path(
        os.environ.get("AEROCAST_PM25_MODEL_DIR", DEFAULT_MODEL_DIR / target)
    )
    return model_dir / "evaluation.json"


def load_model_performance(target: str = "pm25") -> ModelPerformanceResponse:
    """Load the stored evaluation dataset and validate against the schema."""
    if target not in ALL_POLLUTANTS:
        raise FileNotFoundError(
            f"Unknown pollutant target '{target}'. Expected one of {', '.join(ALL_POLLUTANTS)}."
        )
    path = get_evaluation_path(target)
    if not path.exists():
        raise FileNotFoundError(
            f"Model evaluation dataset not found at {path}. "
            "Run `python -m ml.training.evaluate_pm25 --target "
            f"{target}` first."
        )
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return ModelPerformanceResponse(**data)