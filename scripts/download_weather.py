"""Download historical weather data from Open-Meteo for Delhi NCR stations."""

import argparse
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests


STATIONS = {
    "Anand_Vihar": {"lat": 28.6492, "lon": 77.2918},
    "RK_Puram": {"lat": 28.5601, "lon": 77.1835},
    "ITO": {"lat": 28.6290, "lon": 77.2410},
    "Dwarka": {"lat": 28.5921, "lon": 77.0460},
    "Punjabi_Bagh": {"lat": 28.6692, "lon": 77.1285},
}

HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,pressure_msl,surface_pressure,"
    "wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,"
    "boundary_layer_height"
)

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
CHUNK_DAYS = 90
DELAY_BETWEEN_REQUESTS = 0.5


def date_range_chunks(start_date: str, end_date: str, chunk_days: int = CHUNK_DAYS):
    """Yield (start, end) date string pairs, each at most *chunk_days* apart."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while start <= end:
        chunk_end = min(start + timedelta(days=chunk_days - 1), end)
        yield start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        start = chunk_end + timedelta(days=1)


def download_station(
    station_name: str,
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    output_dir: str,
) -> pd.DataFrame:
    """Download hourly weather data for a single station with chunked requests."""
    all_chunks: list[pd.DataFrame] = []

    chunks = list(date_range_chunks(start_date, end_date))
    total_chunks = len(chunks)

    for idx, (chunk_start, chunk_end) in enumerate(chunks, 1):
        print(
            f"  [{station_name}] Chunk {idx}/{total_chunks}: "
            f"{chunk_start} to {chunk_end} ..."
        )

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": chunk_start,
            "end_date": chunk_end,
            "hourly": HOURLY_VARS,
            "timezone": "Asia/Kolkata",
        }

        data = None
        last_err = None
        for attempt in range(5):
            try:
                resp = requests.get(BASE_URL, params=params, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as err:
                last_err = err
                wait = 5 * (attempt + 1)
                print(f"    RETRY {attempt + 1}/5 after error: {err} (waiting {wait}s)")
                time.sleep(wait)
        if data is None:
            print(f"    FAILED: {last_err}")
            continue

        hourly = data.get("hourly", {})
        if not hourly or "time" not in hourly:
            print(f"    WARNING: no hourly data returned for chunk {idx}")
            continue

        df = pd.DataFrame(hourly)
        df["time"] = pd.to_datetime(df["time"])
        df["station"] = station_name
        df["latitude"] = lat
        df["longitude"] = lon
        all_chunks.append(df)

        print(f"    Got {len(df)} rows")
        time.sleep(DELAY_BETWEEN_REQUESTS)

    if not all_chunks:
        print(f"  WARNING: no data retrieved for {station_name}")
        return pd.DataFrame()

    result = pd.concat(all_chunks, ignore_index=True)
    result.drop_duplicates(subset=["time"], keep="last", inplace=True)
    result.sort_values("time", inplace=True)
    result.reset_index(drop=True, inplace=True)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{station_name}_weather.csv")
    result.to_csv(out_path, index=False)
    print(f"  Saved {len(result)} rows -> {out_path}")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Download historical weather from Open-Meteo for Delhi NCR."
    )
    parser.add_argument(
        "--start-date",
        default="2023-01-01",
        help="Start date (YYYY-MM-DD). Default: 2023-01-01",
    )
    parser.add_argument(
        "--end-date",
        default="2024-12-31",
        help="End date (YYYY-MM-DD). Default: 2024-12-31",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "weather"),
        help="Output directory for CSV files.",
    )
    parser.add_argument(
        "--stations",
        nargs="*",
        default=None,
        help="Subset of station names to download (space-separated). "
        "Defaults to all stations.",
    )
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    stations = {
        k: v for k, v in STATIONS.items() if args.stations is None or k in args.stations
    }

    if not stations:
        print("No matching stations found. Available:", list(STATIONS.keys()))
        return

    print(f"Open-Meteo Weather Download")
    print(f"  Date range : {args.start_date} -> {args.end_date}")
    print(f"  Stations   : {list(stations.keys())}")
    print(f"  Output dir : {output_dir}")
    print()

    for name, coords in stations.items():
        print(f"Downloading {name} ({coords['lat']}, {coords['lon']}) ...")
        download_station(
            name, coords["lat"], coords["lon"],
            args.start_date, args.end_date, output_dir,
        )
        print()

    print("All weather downloads complete.")


if __name__ == "__main__":
    main()
