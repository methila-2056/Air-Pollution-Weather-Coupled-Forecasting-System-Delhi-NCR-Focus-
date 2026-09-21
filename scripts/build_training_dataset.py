"""Build the AeroCast-NCR historical training dataset from the database.

Usage:
    python -m scripts.build_training_dataset [--output data/ml] [--target pm25] [--json]

Reads CPCB pollution, Open-Meteo weather (incl. PBL + vertical profile),
inversion indicators, ventilation and FIRMS fire/transport-risk features from
the configured backend database, produces a time-aligned, chronologically-ordered,
leak-free panel with the target pollutant's lag/rolling features, splits it
train/val/test, and writes:

    data/ml/training_dataset_{target}.csv   full panel (with `split` column)
    data/ml/training_dataset_{target}.parquet     same, columnar
    data/ml/dataset_summary_{target}.json   the required dataset summary

No model is trained by this script.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the historical training dataset.")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "data" / "ml"),
                        help="Output directory (default data/ml).")
    parser.add_argument("--stations", nargs="*",
                        help="Restrict to these station names (default: all).")
    parser.add_argument("--target", default="pm25",
                        help="Pollutant target: pm25 pm10 o3 no2 so2 co (default: pm25).")
    parser.add_argument("--json", action="store_true",
                        help="Print the summary as JSON instead of text.")
    args = parser.parse_args()

    from ml.preprocessing.training_dataset import build_training_dataset_from_db

    df, summary = build_training_dataset_from_db(station_names=args.stations, target=args.target)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.target}"
    df.to_csv(out_dir / f"training_dataset{suffix}.csv", index=False)
    parquet_path = out_dir / f"training_dataset{suffix}.parquet"
    try:
        df.to_parquet(parquet_path, index=False)
    except ImportError:
        print("NOTE: parquet engine (pyarrow/fastparquet) not installed — "
              "skipping training_dataset.parquet (CSV written).")
    with open(out_dir / f"dataset_summary{suffix}.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return

    print(f"Saved panel           -> {out_dir / f'training_dataset{suffix}.csv'}  ({len(df):,} rows)")
    print(f"Saved summary         -> {out_dir / f'dataset_summary{suffix}.json'}")
    print(f"Target                : {summary['target']}  ({summary['rows']:,} rows)")
    print(f"Time range            : {summary['time_range']['min']} -> {summary['time_range']['max']}")
    print(f"Stations              : {', '.join(summary['stations'])}")
    print("Splits (chronological, no shuffle):")
    for name, sp in summary["splits"].items():
        print(f"  {name:10s}: {sp['rows']:>5,d} rows  {sp['time_range']['min']} -> {sp['time_range']['max']}")
    print(f"Missing values        : {sum(v['count'] for v in summary.get('missing_values', {}).values())} cells")
    print(f"Target stats          : {summary['target_statistics']}")


if __name__ == "__main__":
    main()
