"""Run a one-shot live data refresh on the configured backend database.

Usage:
    python -m scripts.refresh_once [--dry-run] [--json]

`--dry-run` fetches and reports what *would* be upserted for each source
(weather, fire, pollution) without writing anything to the database.

During development, point it at the local SQLite dev DB:
    DATABASE_URL=sqlite:///./aerocast_ncr.db python -m scripts.refresh_once --dry-run
"""

import argparse
import json

from backend.app.services.refresh_service import run_refresh_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh live weather/fire/pollution data.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report pending rows without writing to the database.",
    )
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON.")
    args = parser.parse_args()

    summary = run_refresh_once(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(summary))
    else:
        mode = "DRY-RUN (nothing written)" if args.dry_run else "committed"
        print(f"Refresh mode: {mode}")
        for source, count in summary.items():
            print(f"  {source:10s}: {count:,} new rows")


if __name__ == "__main__":
    main()
