"""Download ERA5 atmospheric data via the Copernicus CDS API (WS-2).

Fetches genuine ERA5 single-level reanalysis (``2m_temperature``,
``surface_pressure``, ``boundary_layer_height``) for Delhi NCR from
`Copernicus CDS <https://cds.climate.copernicus.eu/how-to-api>`_ and extracts
per-station, per-hour rows consumed by ``scripts/build_dataset.py``:

- Requires a free CDS account with credentials in ``~/.cdsapirc`` and the
  ``cdsapi`` package installed (``pip install cdsapi``).
- Each archive year is downloaded as ``era5_atmosphere_<YYYY>.nc`` and then
  *sampled at the 17 curated NCR stations* (nearest grid cell) into
  ``era5_atmosphere.csv`` with columns
  ``time, station, era5_temperature (degC), era5_surface_pressure (hPa),
  era5_blh (m)``.
- Idempotent: existing non-empty NetCDFs are skipped unless ``--force``.

Honesty contract: no fabricated reanalysis is ever produced. If the CDS is
unreachable or unauthorised the script prints exactly why and writes an
*empty* placeholder CSV so ``build_dataset.py`` can detect that the source is
absent and keep using Open-Meteo weather.

Usage:
    python -m scripts.download_atmosphere --start-date 2023-01-01 --end-date 2024-12-31
    python -m scripts.download_atmosphere --no-download --years 2023
"""

import argparse
import os
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Delhi NCR bounding box (slightly larger for context).
LAT_MIN, LAT_MAX = 28.3, 28.9
LON_MIN, LON_MAX = 76.8, 77.5

DEFAULT_DATA_DIR = ROOT / "data" / "atmosphere"


def years_between(start_date: str, end_date: str) -> list[int]:
    y0, y1 = int(start_date[:4]), int(end_date[:4])
    return list(range(y0, y1 + 1))


def build_request(year: int) -> dict:
    return {
        "product_type": "reanalysis",
        "variable": ["boundary_layer_height", "2m_temperature", "surface_pressure"],
        "year": str(year),
        "month": [f"{m:02d}" for m in range(1, 13)],
        "day": [f"{d:02d}" for d in range(1, 32)],
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": [LAT_MAX, LON_MIN, LAT_MIN, LON_MAX],
        "format": "netcdf",
    }


def try_cds_download(start_date: str, end_date: str, output_dir: pathlib.Path,
                     force: bool = False) -> tuple[bool, list[pathlib.Path]]:
    """Attempt ERA5 downloads via cdsapi; returns (success, downloaded files)."""
    try:
        import cdsapi
    except ImportError:
        print("  cdsapi package not installed. Install with: pip install cdsapi")
        return False, []

    cdsapirc = os.path.expanduser("~/.cdsapirc")
    if not os.path.isfile(cdsapirc):
        print(f"  CDS credentials not found at {cdsapirc}")
        print("  Register at https://cds.climate.copernicus.eu/how-to-api "
              "and create ~/.cdsapirc with your UID and API key.")
        return False, []

    output_dir.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    downloaded: list[pathlib.Path] = []
    for year in years_between(start_date, end_date):
        out_path = output_dir / f"era5_atmosphere_{year}.nc"
        if out_path.exists() and out_path.stat().st_size > 0 and not force:
            print(f"  {out_path.name} already present — skipping.")
            downloaded.append(out_path)
            continue
        print(f"  Submitting ERA5 request for {year} ...")
        try:
            client.retrieve("reanalysis-era5-single-levels",
                            build_request(year), str(out_path))
        except Exception as exc:
            print(f"  CDS download failed for {year}: {exc}")
            return False, downloaded
        print(f"  Saved -> {out_path}")
        downloaded.append(out_path)
    return bool(downloaded), downloaded


def extract_station_csv(files: list[pathlib.Path], output_dir: pathlib.Path) -> pathlib.Path | None:
    """Sample ERA5 grids at the NCR stations into era5_atmosphere.csv."""
    from ml.features.era5_surface import FEATURE_COLUMNS, load_era5_surface

    frames = []
    for nc in files:
        print(f"  Sampling {nc.name} at the 17 NCR stations ...")
        df = load_era5_surface(nc)
        if not df.empty:
            frames.append(df)
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)  # type: ignore[arg-type]
    out = out[FEATURE_COLUMNS].sort_values(["time", "station"]).reset_index(drop=True)
    out_path = output_dir / "era5_atmosphere.csv"
    out.to_csv(out_path, index=False)
    return out_path


def fallback_placeholder(output_dir: pathlib.Path) -> pathlib.Path:
    """Write a clearly-empty placeholder so build_dataset detects absent ERA5."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "era5_atmosphere.csv"
    pd.DataFrame(columns=["time", "station",
                          "era5_temperature", "era5_surface_pressure", "era5_blh"]
                 ).to_csv(out_path, index=False)
    print(f"  Saved empty placeholder -> {out_path}")
    print("  No real ERA5 data was produced — the pipeline keeps using "
          "Open-Meteo weather (see docs/era5.md).")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download ERA5 atmospheric data via Copernicus CDS (WS-2).")
    parser.add_argument("--start-date", default="2023-01-01",
                        help="Start date YYYY-MM-DD (default 2023-01-01).")
    parser.add_argument("--end-date", default="2024-12-31",
                        help="End date YYYY-MM-DD (default 2024-12-31).")
    parser.add_argument("--output-dir", default=str(DEFAULT_DATA_DIR),
                        help="Output directory (default data/atmosphere).")
    parser.add_argument("--no-download", action="store_true",
                        help="Only print the request that would be submitted.")
    parser.add_argument("--force", action="store_true",
                        help="Re-download archive years even if present.")
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output_dir).expanduser().resolve()
    print("ERA5 Atmosphere Download")
    print(f"  Date range : {args.start_date} -> {args.end_date}")
    print(f"  Area       : {LAT_MIN}-{LAT_MAX} lat, {LON_MIN}-{LON_MAX} lon")
    print(f"  Output dir : {output_dir}")
    print()

    if args.no_download:
        for year in years_between(args.start_date, args.end_date):
            print(f"  planned: reanalysis-era5-single-levels {build_request(year)}")
        return 0

    ok, files = try_cds_download(args.start_date, args.end_date, output_dir,
                                 force=args.force)
    if not ok:
        fallback_placeholder(output_dir)
        return 0

    out = extract_station_csv(files, output_dir)
    if out is None:
        print("  Sampling produced no rows; writing empty placeholder.", file=sys.stderr)
        fallback_placeholder(output_dir)
        return 1

    print(f"  Extracted per-station rows -> {out}")
    print("\nAtmosphere download complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
