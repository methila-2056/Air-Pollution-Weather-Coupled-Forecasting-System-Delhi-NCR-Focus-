"""Download CPCB air-quality data via opencity.in CKAN (real CPCB-sourced Delhi data)."""

import argparse
import os
import time

import pandas as pd
import requests

CKAN_BASE = "https://data.opencity.in/api/3/action/datastore_search"

RESOURCES = {
    "Anand_Vihar": "5ef3f66f-2bb0-4593-91db-ba6e693a77f3",
    "RK_Puram": "d9dfd28d-038d-448f-8e33-5e6f6b32d15c",
    "ITO": "890f786d-fb9f-475e-8516-191bfa1b01ea",
    "Dwarka": "495db3d4-5683-4b1d-9b7d-34ecb887ca13",
    "Punjabi_Bagh": "82080ddc-e094-4a3a-8421-242ec6bc8a45",
}

STATION_LAT_LON = {
    "Anand_Vihar": (28.6492, 77.2918),
    "RK_Puram": (28.5601, 77.1835),
    "ITO": (28.6290, 77.2410),
    "Dwarka": (28.5921, 77.0460),
    "Punjabi_Bagh": (28.6692, 77.1285),
}

PMAP = {
    "PM2.5 (ug/m3)": "pm25",
    "PM10 (ug/m3)": "pm10",
    "NO2 (ug/m3)": "no2",
    "SO2 (ug/m3)": "so2",
    "CO (mg/m3)": "co",
    "Ozone (ug/m3)": "o3",
}

DELAY_BETWEEN_REQUESTS = 0.3


def fetch_ckan(resource_id: str, limit: int, offset: int) -> tuple[list, int]:
    resp = requests.get(
        CKAN_BASE,
        params={"resource_id": resource_id, "limit": limit, "offset": offset},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN error: {payload.get('error')}")
    result = payload["result"]
    return result.get("records", []), result.get("total", 0)


def download_station(station_name: str, output_dir: str) -> pd.DataFrame | None:
    resource_id = RESOURCES[station_name]
    print(f"  Downloading {station_name} (resource {resource_id}) ...")

    all_rows: list[dict] = []
    offset = 0
    page_size = 10000
    total = None

    while True:
        try:
            records, total = fetch_ckan(resource_id, page_size, offset)
        except Exception as exc:
            print(f"    FAILED at offset {offset}: {exc}")
            break

        if not records:
            break

        all_rows.extend(records)
        print(f"    Fetched {len(records)} rows (offset {offset}, total {total})")

        offset += page_size
        if offset >= total:
            break

        time.sleep(DELAY_BETWEEN_REQUESTS)

    if not all_rows:
        print(f"  No records retrieved for {station_name}")
        return None

    df = pd.DataFrame(all_rows)
    df = df.drop(columns=["_id"], errors="ignore")

    df.rename(columns=PMAP, inplace=True)

    for col in ["pm25", "pm10", "no2", "so2", "co", "o3"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df.drop(columns=["Timestamp"], inplace=True)

    lat, lon = STATION_LAT_LON[station_name]
    df["station"] = station_name
    df["latitude"] = lat
    df["longitude"] = lon

    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    if "timestamp" in df.columns and "pm25" in df.columns:
        hourly = df.set_index("timestamp").resample("1h").mean(numeric_only=True).reset_index()
        hourly["station"] = station_name
        hourly["latitude"] = lat
        hourly["longitude"] = lon
        df = hourly

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{station_name}_pollution.csv")
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df)} rows -> {out_path}")

    cov = (df["pm25"].notna().mean() * 100) if "pm25" in df.columns else 0
    print(f"  PM2.5 coverage: {cov:.1f}%")
    return df


def main():
    parser = argparse.ArgumentParser(
        description="Download CPCB air-quality data (opencity.in CKAN, real CPCB sources)."
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "pollution"),
        help="Output directory for CSV files.",
    )
    parser.add_argument(
        "--stations",
        nargs="*",
        default=None,
        help="Subset of station names (space-separated). Defaults to all.",
    )
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    stations = list(
        RESOURCES.keys()
        if args.stations is None
        else [s for s in args.stations if s in RESOURCES]
    )

    print(f"CPCB Pollution Download (opencity.in CKAN)")
    print(f"  Stations  : {stations}")
    print(f"  Output dir: {output_dir}")
    print()

    for name in stations:
        download_station(name, output_dir)
        print()

    print("All pollution downloads complete.")


if __name__ == "__main__":
    main()