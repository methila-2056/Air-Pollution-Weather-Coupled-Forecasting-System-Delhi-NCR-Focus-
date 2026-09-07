"""Sanity-check the AeroCast-NCR environment before running anything.

Verifies Python version, critical imports, database files/tables, trained
model artifacts, and processed data. Prints a report and exits non-zero if
any critical check fails.

Usage:
    python -m scripts.environment_check
"""

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "backend", "aerocast_ncr.db")

CRITICAL_IMPORTS = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "pydantic",
    "pandas",
    "numpy",
    "sklearn",
    "joblib",
]

OPTIONAL_IMPORTS = ["xgboost", "shap", "alembic"]

EXPECTED_TABLES = [
    "stations",
    "pollution_readings",
    "weather_readings",
    "fire_readings",
    "forecasts",
    "alerts",
    "model_metrics",
]


def check(label: str, ok: bool, detail: str = "", critical: bool = False) -> bool:
    status = "ok" if ok else ("FAIL" if critical else "WARN")
    print(f"[{status:^4}] {label}" + (f" - {detail}" if detail else ""))
    return ok or critical


def main() -> int:
    print(f"AeroCast-NCR environment check\nPython {sys.version.split()[0]} ({sys.executable})\n")
    failures = 0

    ok = sys.version_info >= (3, 11)
    if not check("Python >= 3.11", ok, critical=True):
        failures += 1

    for module in CRITICAL_IMPORTS:
        try:
            __import__(module)
            check(f"import {module}", True)
        except Exception as exc:  # pragma: no cover - env dependency
            if check(f"import {module}", False, str(exc), critical=True):
                failures += 1

    for module in OPTIONAL_IMPORTS:
        try:
            __import__(module)
            check(f"import {module} (optional)", True)
        except Exception:
            check(f"import {module} (optional)", False, "not installed; some features degrade")

    db_path = os.environ.get("DATABASE_URL", DEFAULT_DB).replace("sqlite:///", "")
    if not db_path or "sqlite" in os.environ.get("DATABASE_URL", ""):
        db_path = db_path or DEFAULT_DB
    if not os.path.isabs(db_path):
        db_path = os.path.join(ROOT, db_path)
    if check("SQLite database file exists", os.path.exists(db_path), db_path):
        try:
            con = sqlite3.connect(db_path)
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            con.close()
            missing = [t for t in EXPECTED_TABLES if t not in tables]
            check("Database tables present", not missing, f"missing={missing or 'none'}", critical=bool(missing))
            if missing:
                failures += 1
        except Exception as exc:
            check("Database readable", False, str(exc), critical=True)
            failures += 1

    models_dir = os.path.join(ROOT, "models")
    model_files = [f for f in os.listdir(models_dir) if f.endswith(".joblib")] if os.path.isdir(models_dir) else []
    n_models = len(model_files)
    check("Trained models present (108 expected)", n_models >= 100, f"{n_models} joblib files", critical=n_models < 100)
    if n_models < 100:
        failures += 1

    processed = os.path.join(ROOT, "data", "processed")
    parts = [f for f in os.listdir(processed) if f.startswith("featured_dataset_part")] if os.path.isdir(processed) else []
    check("Processed dataset parts present", bool(parts), parts and ", ".join(parts) or "missing")

    print("\n" + ("ALL CHECKS PASSED" if not failures else f"{failures} CRITICAL CHECK(S) FAILED"))
    return failures


if __name__ == "__main__":
    sys.exit(main())