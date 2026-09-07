"""Download ERA5 atmospheric data via Copernicus CDS API.

NOTE: The CDS API requires a free account and credentials stored in
~/.cdsapirc.  See https://cds.climate.copernicus.eu/how-to-api

If CDS credentials are unavailable, the script falls back to the
Open-Meteo boundary-layer-height data that is already fetched by
download_weather.py and prints a reminder.
"""

import argparse
import os
import sys
import time

import pandas as pd

# Delhi NCR bounding box (slightly larger for context)
LAT_MIN, LAT_MAX = 28.3, 28.9
LON_MIN, LON_MAX = 76.8, 77.5

VARIABLES = [
    "boundary_layer_height",
    "temperature",
    "surface_pressure",
]

DELAY_BETWEEN_REQUESTS = 0.5


def try_cds_download(start_date: str, end_date: str, output_dir: str) -> bool:
    """Attempt ERA5 download via cdsapi. Returns True on success."""
    try:
        import cdsapi
    except ImportError:
        print("  cdsapi package not installed. Install with: pip install cdsapi")
        return False

    # Check for credentials file
    cdsapirc = os.path.expanduser("~/.cdsapirc")
    if not os.path.isfile(cdsapirc):
        print(f"  CDS credentials not found at {cdsapirc}")
        print(
            "  Register at https://cds.climate.copernicus.eu/how-to-api "
            "and create ~/.cdsapirc"
        )
        return False

    print("  Attempting ERA5 download via CDS API ...")

    try:
        c = cdsapi.Client()

        area = [LAT_MAX, LON_MIN, LAT_MIN, LON_MAX]

        request_params = {
            "product_type": "reanalysis",
            "variable": VARIABLES,
            "year": sorted({start_date[:4], end_date[:4]}),
            "month": [f"{m:02d}" for m in range(1, 13)],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": area,
            "format": "netcdf",
        }

        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "era5_atmosphere.nc")

        c.retrieve("reanalysis-era5-single-levels", request_params, out_path)

        print(f"  Saved ERA5 data -> {out_path}")
        return True

    except Exception as exc:
        print(f"  CDS download failed: {exc}")
        return False


def fallback_open_meteo_pbl(output_dir: str) -> None:
    """Inform user that PBL data is already in weather CSVs."""
    msg = """
==========================================================================
  Fallback: ERA5 atmospheric data not available.
==========================================================================

  Boundary-layer height (BLH) is already included in the weather CSVs
  downloaded by download_weather.py (variable: boundary_layer_height).

  If you additionally need ERA5 temperature / surface pressure at higher
  vertical resolution, please:

  1. Register at https://cds.climate.copernicus.eu/how-to-api
  2. Create ~/.cdsapirc with your UID and API key.
  3. pip install cdsapi
  4. Re-run this script.

  Meanwhile, the downstream build_dataset.py will use the Open-Meteo
  weather data which already contains BLH.
==========================================================================
"""
    print(msg)

    # Write a lightweight CSV so build_dataset.py can detect this source
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "era5_atmosphere.csv")
    cols = [
        "time", "station",
        "era5_temperature", "era5_surface_pressure", "era5_blh",
    ]
    pd.DataFrame(columns=cols).to_csv(out_path, index=False)
    print(f"  Saved empty placeholder -> {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Download ERA5 atmospheric data via Copernicus CDS."
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
        default=os.path.join(os.path.dirname(__file__), "..", "data", "atmosphere"),
        help="Output directory.",
    )
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)

    print(f"ERA5 Atmosphere Download")
    print(f"  Date range : {args.start_date} -> {args.end_date}")
    print(f"  Area       : {LAT_MIN}-{LAT_MAX} lat, {LON_MIN}-{LON_MAX} lon")
    print(f"  Output dir : {output_dir}")
    print()

    success = try_cds_download(args.start_date, args.end_date, output_dir)
    if not success:
        fallback_open_meteo_pbl(output_dir)

    print("\nAtmosphere download complete.")


if __name__ == "__main__":
    main()
