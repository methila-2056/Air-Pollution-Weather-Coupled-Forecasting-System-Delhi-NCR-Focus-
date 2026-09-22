"""Clean regenerable data/build artifacts down to committed source-of-truth.

Removes only paths that ``.gitignore`` marks as fully regenerable (caches,
logs, local databases, build output, engineered datasets and ML byproducts).
Source CSVs, model weights and committed datasets are never touched.

Usage (from the repository root):

    python -m scripts.clean_generated            # dry-run: show what would be removed
    python -m scripts.clean_generated --exec     # actually remove
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

REGENERABLE = [
    # Python / tooling caches
    "**/__pycache__",
    "**/*.pyc",
    ".pytest_cache",
    ".ml-cache",
    "**/*.egg-info",
    # runtime logs & local dev databases
    "**/*.log",
    "**/*.db",
    # frontend build output
    "frontend/dist",
    "frontend/*.tsbuildinfo",
    # engineered dataset + ML byproducts (rebuilt by build_dataset.py / trainers)
    "data/processed/featured_dataset.csv",
    "data/ml",
    "models/pm25/training_predictions.csv",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove regenerable build/data artifacts.")
    parser.add_argument("--exec", action="store_true",
                        help="Actually delete; default is a dry-run listing.")
    args = parser.parse_args()

    removed: list[Path] = []
    for pattern in REGENERABLE:
        for match in PROJECT_ROOT.glob(pattern):
            if ".venv" in match.parts:
                continue
            removed.append(match)

    removed = sorted(set(removed))
    for path in removed:
        kind = "dir " if path.is_dir() else "file"
        print(f"[{'remove' if args.exec else 'dry-run'}] {kind} {path.relative_to(PROJECT_ROOT)}")
        if args.exec:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    print(f"\n{len(removed)} regenerable artifact(s) "
          f"{'removed' if args.exec else 'would be removed (re-run with --exec to apply)'}.")


if __name__ == "__main__":
    main()
