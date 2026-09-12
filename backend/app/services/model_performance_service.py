"""Model performance service: loads the measured performance dataset.

Reads models/pm25/evaluation.json (written by ml/training/evaluate_pm25.py)
and returns it as a validated ModelPerformanceResponse. Every metric in the
file is computed from held-out (unseen) chronological test predictions - the
service performs no calculation, so nothing can be fabricated at request time.
"""

from __future__ import annotations

import json
import os
import pathlib

from ..schemas.schemas import ModelPerformanceResponse

_SERVICE_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _SERVICE_DIR.parents[2]
DEFAULT_MODEL_DIR = _REPO_ROOT / "models" / "pm25"


def get_evaluation_path() -> pathlib.Path:
    model_dir = pathlib.Path(os.environ.get("AEROCAST_PM25_MODEL_DIR", DEFAULT_MODEL_DIR))
    return model_dir / "evaluation.json"


def load_model_performance() -> ModelPerformanceResponse:
    """Load the stored evaluation dataset and validate against the schema."""
    path = get_evaluation_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Model evaluation dataset not found at {path}. "
            "Run `python -m ml.training.evaluate_pm25` first."
        )
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return ModelPerformanceResponse(**data)
