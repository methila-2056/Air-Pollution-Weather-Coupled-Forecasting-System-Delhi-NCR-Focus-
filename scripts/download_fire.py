"""Download NASA FIRMS active-fire data for Punjab/Haryana region.

Primary: NASA FIRMS API with MAP_KEY (register free at
https://firms.modaps.eosdis.nasa.gov/map/).
Fallback: public FIRMS global CSV (VIIRS SNPP c2), filtered to region.
"""

import argparse
import os
from datetime import datetime, timedelta

import pandas as pd
import requests

DELAY = 0.3

# Bounding box covering Punjab, Haryana, western UP, northern Rajasthan, Delhi
REGION_PROPS = {
    "min_lon": 73.5,
    "min_lat": 27.5,
    "max_lon": 78.5,
    "max_lat": 33.0,
}

PUBLIC_CSV = {
    "VIIRS_SNPP": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_24h.csv",
    "MODIS": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/c6/csv/MODIS_C6_Global_24h.csv",
}


def filter_region(df: pd.DataFrame, lat_col: str, lon_col: str) -> pd.DataFrame:
    hits = (
        (df[lon_col] >= REGION_PROPS["min_lon"])
        & (df[lon_col] <= REGION_PROPS["max_lon"])
        & (df[lat_col] >= REGION_PROPS["min_lat"])
        & (df[lat_col] <= REGION_PROPS["max_lat"])
    )
    return df[hits].copy()


def download_via_firms_api(map_key: str, days: int, out_path: str) -> bool:
    """Try the official FIRMS API (requires free MAP_KEY)."""
    url = (
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}"
        f"/VIIRS_SNPP_NRT/"
        f"{REGION_PROPS['min_lon']},{REGION_PROPS['min_lat']},"
        f"{REGION_PROPS['max_lon']},{REGION_PROPS['max_lat']}/"
        f"{days}"
    )
    print(f"  Trying FIRMS API ...")
    resp = requests.get(url, timeout=90)
    if resp.status_code != 200:
        print(f"    API returned HTTP {resp.status_code}. Text: {resp.text[:120]}")
        return False
    decoded = resp.text
    if "Invalid" in decoded[:200] or "Invalid MAP_KEY" in decoded:
        print("    Invalid MAP_KEY provided.")
        return False
    df = pd.read_csv(pd.io.common.StringIO(decoded))
    _save(df, out_path)
    print(f"    Saved {len(df)} fire records from FIRMS API -> {out_path}")
    return True


def download_via_public_csv(days: int, out_path: str) -> bool:
    """Fallback: public daily FIRMS CSVs, grabbing up to `days` daily files."""
    print("  Falling back to public FIRMS daily CSVs ...")
    frames = []
    today = datetime.utcnow()
    sensor = "VIIRS_SNPP"
    url = PUBLIC_CSV[sensor]

    resp = requests.get(url, timeout=90)
    if resp.status_code != 200:
        print(f"    Public CSV fetch failed: HTTP {resp.status_code}")
        return False
    df = pd.read_csv(pd.io.common.StringIO(resp.text))
    print(f"    Retrieved global VIIRS file with {len(df)} records")
    out = filter_region(df, "latitude", "longitude")
    frames.append(out)

    if not frames or all(f.empty for f in frames):
        print("    No fires in Punjab/Haryana/Delhi region for recent window.")
        empty = df.iloc[0:0].copy()
        _save(empty, out_path)
        return True

    for frame_i, frame in enumerate(frames):
        if "acq_date_time" in frame.columns:
            frame["acq_date_time"] = pd.to_datetime(frame["acq_date_time"], errors="coerce")
        elif "acq_date" in frame.columns:
            frame["acq_time"] = frame["acq_time"].astype(str).str.zfill(4)
            frame["acq_date_time"] = pd.to_datetime(
                frame["acq_date"].astype(str) + " " + frame["acq_time"],
                format="%Y-%m-%d %H%M",
                errors="coerce",
            )
        frames[frame_i] = frame

    merged = pd.concat(frames, ignore_index=True)
    if "acq_date_time" in merged.columns:
        merged.sort_values("acq_date_time", inplace=True)
    _save(merged, out_path)
    # filter region print
    print(f"    Fire records in region: {len(merged)}")
    return True


def _save(df: pd.DataFrame, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.drop_duplicates(inplace=True)
    df.to_csv(out_path, index=False)


def main():
    parser = argparse.ArgumentParser(description="Download NASA FIRMS active-fire data.")
    parser.add_argument("--map-key", default=os.getenv("NASA_FIRMS_MAP_KEY", os.getenv("FIRMS_MAP_KEY", "")), help="NASA FIRMS MAP_KEY.")
    parser.add_argument("--days", type=int, default=3, help="Days of fire data.")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "fire"),
        help="Output directory.",
    )
    args = parser.parse_args()

    out_path = os.path.join(os.path.abspath(args.output_dir), "firms_fires.csv")
    print(f"NASA FIRMS Fire Download")
    print(f"  Region     : {REGION_PROPS}")
    print(f"  Output     : {out_path}")
    print()

    ok = False
    if args.map_key:
        ok = download_via_firms_api(args.map_key, args.days, out_path)
    if not ok:
        ok = download_via_public_csv(args.days, out_path)

    if ok:
        print("Fire download complete.")
    else:
        print("Fire download failed. Register a free MAP_KEY at https://firms.modaps.eosdis.nasa.gov/")


if __name__ == "__main__":
    main()