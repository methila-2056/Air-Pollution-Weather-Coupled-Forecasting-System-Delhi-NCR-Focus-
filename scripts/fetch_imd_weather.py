"""Fetch genuine IMD city forecasts from api.imd.gov.in into data/imd (WS-3).

Writes per-day rows (``time, station, imd_max_temp_c, imd_min_temp_c,
imd_condition, imd_source``) to ``data/imd/imd_forecast.csv`` for the offline
coupled dataset (``scripts/build_dataset.py`` merges ``imd_*`` columns).

Official IMD gateway (https://api.imd.gov.in) requires an API key and/or IP
whitelisting — without it you get an honest 401 message and an *empty* file,
and the pipeline keeps using Open-Meteo. Never fabricates IMD data.

Usage:
    python -m scripts.fetch_imd_weather --station-id 42182
    python -m scripts.fetch_imd_weather --no-download
"""

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DATA_DIR = ROOT / "data" / "imd"
COLUMNS = ["time", "station", "imd_max_temp_c", "imd_min_temp_c",
           "imd_condition", "imd_source"]


def _import_service():
    from backend.app.services.imd_weather import fetch_city_forecast, imd_forecast_dataframe
    return fetch_city_forecast, imd_forecast_dataframe


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch genuine IMD city forecasts (api.imd.gov.in) — WS-3.")
    parser.add_argument("--station-id", default=None,
                        help="IMD station id (default: settings imd_station_id = 42182).")
    parser.add_argument("--output-dir", default=str(DEFAULT_DATA_DIR),
                        help="Output directory (default data/imd).")
    parser.add_argument("--no-download", action="store_true",
                        help="Only print the request that would be made.")
    args = parser.parse_args()

    print("IMD City Weather Fetch (WS-3)")
    output_dir = pathlib.Path(args.output_dir).expanduser().resolve()

    if args.no_download:
        from backend.app.config import get_settings
        s = get_settings()
        print("  planned GET", f"{s.imd_api_base.rstrip('/')}/cityforecast",
              "params={}", "id:", args.station_id or s.imd_station_id,
              "key:", "configured" if s.imd_api_key else "NOT configured")
        return 0

    fetch_city_forecast, imd_forecast_dataframe = _import_service()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "imd_forecast.csv"

    try:
        result = fetch_city_forecast(args.station_id)
    except Exception as exc:
        print(f"  IMD unavailable: {exc}")
        import pandas as pd
        pd.DataFrame(columns=COLUMNS).to_csv(out_path, index=False)
        print(f"  Saved empty placeholder -> {out_path}")
        print("  The pipelined dataset keeps using Open-Meteo (see docs/imd.md).")
        return 1

    df, reasons = imd_forecast_dataframe(result)
    if df.empty:
        print("  IMD produced no rows (" + "; ".join(reasons) + ").")
        return 1

    df[COLUMNS].to_csv(out_path, index=False)
    print(f"  Saved {len(df)} genuine IMD rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
