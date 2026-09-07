#!/usr/bin/env bash
# Fetch all data sources and rebuild the featured dataset (Unix).
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"

for step in \
  scripts/download_weather.py \
  scripts/download_pollution.py \
  scripts/download_fire.py \
  scripts/download_atmosphere.py \
  scripts/build_dataset.py; do
  echo "==> $step"
  "$PYTHON" "$step"
done

echo "All data pipeline steps completed."