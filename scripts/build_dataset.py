"""Merge weather, pollution, fire, and atmosphere data into a coupled dataset."""

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default data directories
WEATHER_DIR = PROJECT_ROOT / "data" / "weather"
POLLUTION_DIR = PROJECT_ROOT / "data" / "pollution"
FIRE_DIR = PROJECT_ROOT / "data" / "fire"
ATMOSPHERE_DIR = PROJECT_ROOT / "data" / "atmosphere"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

STATIONS = ["Anand_Vihar", "RK_Puram", "ITO", "Dwarka", "Punjabi_Bagh"]

MAX_FFILL_HOURS = 3


def load_weather(weather_dir: Path) -> pd.DataFrame:
    """Load and concatenate all per-station weather CSVs."""
    frames = []
    for csv in sorted(weather_dir.glob("*_weather.csv")):
        df = pd.read_csv(csv, parse_dates=["time"])
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_pollution(pollution_dir: Path) -> pd.DataFrame:
    """Load all per-station pollution CSVs."""
    frames = []
    for csv in sorted(pollution_dir.glob("*_pollution.csv")):
        # Skip placeholder files with comment-only headers
        try:
            df = pd.read_csv(csv, comment="#")
        except Exception:
            continue
        if df.empty or "station" not in df.columns:
            continue
        time_col = "timestamp" if "timestamp" in df.columns else "From Date"
        ren = {time_col: "time"}
        keep = [time_col, "station", "pm25", "pm10", "no2", "so2", "co", "o3",
                "PM2.5", "PM10", "NO2", "O3", "SO2", "CO", "AQI"]
        df = df.rename(columns=ren)
        keep = [("time" if c == time_col else c) for c in keep]
        keep = [c for c in keep if c in df.columns]
        df = df[keep]
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # Normalize pollutant column names to lowercase short forms
    colmap = {"PM2.5": "pm25", "PM10": "pm10", "NO2": "no2", "O3": "o3",
              "SO2": "so2", "CO": "co"}
    out = out.rename(columns=colmap)
    if "time" in out.columns:
        ts = pd.to_datetime(out["time"], utc=True, errors="coerce")
        out["time"] = ts.dt.tz_localize(None)
    # Drop duplicate pollutant column versions (keep last if both exist)
    for col in set(colmap.values()):
        if sum(1 for c in out.columns if c == col) > 1:
            keep = [c for c in out.columns if c != col] + [col]
            out = out[keep]
    return out


def load_fire(fire_dir: Path) -> pd.DataFrame:
    """Load FIRMS fire data and bin to hourly + nearest-station."""
    csv_path = fire_dir / "firms_fires.csv"
    if not csv_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(csv_path, low_memory=False)
    if df.empty or "latitude" not in df.columns:
        return pd.DataFrame()

    # Parse acquisition datetime
    if "acq_date" in df.columns and "acq_time" in df.columns:
        # acq_time is HHMM integer
        df["acq_time_str"] = df["acq_time"].astype(str).str.zfill(4)
        df["acq_datetime"] = pd.to_datetime(
            df["acq_date"] + " " + df["acq_time_str"].str[:2] + ":" + df["acq_time_str"].str[2:],
            errors="coerce",
        )
    elif "acq_date" in df.columns:
        df["acq_datetime"] = pd.to_datetime(df["acq_date"], errors="coerce")
    else:
        return pd.DataFrame()

    df.dropna(subset=["acq_datetime", "latitude", "longitude"], inplace=True)
    df["time"] = df["acq_datetime"].dt.floor("h")

    # Station coordinates
    station_coords = {
        "Anand_Vihar": (28.6492, 77.2918),
        "RK_Puram": (28.5601, 77.1835),
        "ITO": (28.6290, 77.2410),
        "Dwarka": (28.5921, 77.0460),
        "Punjabi_Bagh": (28.6692, 77.1285),
    }

    def nearest_station(lat, lon):
        best, best_dist = None, float("inf")
        for stn, (slat, slon) in station_coords.items():
            d = (lat - slat) ** 2 + (lon - slon) ** 2
            if d < best_dist:
                best, best_dist = stn, d
        return best

    df["station"] = df.apply(lambda r: nearest_station(r["latitude"], r["longitude"]), axis=1)

    # Aggregate fires per hour per station
    agg = (
        df.groupby(["time", "station"])
        .agg(
            fire_count=("latitude", "size"),
            mean_frp=("frp", "mean") if "frp" in df.columns else ("latitude", "size"),
            max_bright=("bright_ti4", "max") if "bright_ti4" in df.columns else ("latitude", "size"),
        )
        .reset_index()
    )
    return agg


def load_atmosphere(atmo_dir: Path) -> pd.DataFrame:
    """Load ERA5 atmosphere data if available."""
    nc_path = atmo_dir / "era5_atmosphere.nc"
    csv_path = atmo_dir / "era5_atmosphere.csv"

    if nc_path.exists():
        try:
            ds = pd.read_xarray(nc_path)  # type: ignore
            # Convert to DataFrame — specifics depend on variable names
            return ds.to_dataframe().reset_index()
        except Exception:
            pass

    if csv_path.exists():
        df = pd.read_csv(csv_path, parse_dates=["time"], comment="#")
        if not df.empty:
            return df

    return pd.DataFrame()


def normalize_timestamps(df: pd.DataFrame, time_col: str = "time") -> pd.DataFrame:
    """Ensure time column is datetime, tz-naive UTC."""
    if time_col not in df.columns:
        return df
    df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df[time_col] = df[time_col].dt.tz_localize(None)
    return df


def forward_fill_missing(df: pd.DataFrame, group_col: str, max_hours: int = MAX_FFILL_HOURS) -> pd.DataFrame:
    """Forward-fill numeric columns within each group, up to *max_hours* steps."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols or group_col not in df.columns:
        return df

    df.sort_values([group_col, "time"], inplace=True)

    def _ffill_group(g):
        g = g.set_index("time").sort_index()
        # Resample to hourly to ensure consistent index
        g = g.resample("h").first()
        g[group_col] = g[group_col].ffill(limit=max_hours)
        for col in numeric_cols:
            if col in g.columns:
                g[col] = g[col].ffill(limit=max_hours)
        g = g.reset_index()
        return g

    result = df.groupby(group_col, group_keys=False).apply(_ffill_group)
    return result


def merge_datasets(
    weather: pd.DataFrame,
    pollution: pd.DataFrame,
    fire: pd.DataFrame,
    atmosphere: pd.DataFrame,
) -> pd.DataFrame:
    """Merge all data sources on (time, station)."""
    # Start with weather as the base
    if weather.empty:
        print("WARNING: weather data is empty — cannot build coupled dataset.")
        return pd.DataFrame()

    base = weather.copy()

    # Merge pollution
    if not pollution.empty and "time" in pollution.columns:
        pol = pollution.copy()
        merge_cols = ["time", "station"]
        pol_keep = [c for c in ["time", "station", "pm25", "pm10", "no2", "o3", "so2", "co", "AQI"]
                     if c in pol.columns]
        pol = pol[pol_keep]
        base = base.merge(pol, on=merge_cols, how="left")

    # Merge fire
    if not fire.empty:
        fire_keep = [c for c in ["time", "station", "fire_count", "mean_frp", "max_bright"]
                     if c in fire.columns]
        fire = fire[fire_keep]
        base = base.merge(fire, on=["time", "station"], how="left")

    # Merge atmosphere
    if not atmosphere.empty and "time" in atmosphere.columns and "station" in atmosphere.columns:
        atm_keep = [c for c in atmosphere.columns if c in ["time", "station"] or c.startswith("era5_")]
        atmosphere = atmosphere[atm_keep]
        base = base.merge(atmosphere, on=["time", "station"], how="left")

    return base


def validate(df: pd.DataFrame) -> list[str]:
    """Run quality checks and return a list of issues found."""
    issues = []

    if df.empty:
        issues.append("Dataset is empty.")
        return issues

    # Duplicate timestamps per station
    dupes = df.duplicated(subset=["timestamp", "station"], keep=False).sum()
    if dupes > 0:
        issues.append(f"Duplicate (timestamp, station) rows: {dupes}")

    # Missing stations
    present = set(df["station"].unique()) if "station" in df.columns else set()
    missing_stations = set(STATIONS) - present
    if missing_stations:
        issues.append(f"Missing stations: {missing_stations}")

    # Date range
    if "timestamp" in df.columns:
        tmin, tmax = df["timestamp"].min(), df["timestamp"].max()
        issues.append(f"Date range: {tmin} to {tmax}")

    return issues


def quality_report(df: pd.DataFrame) -> str:
    """Build a human-readable data quality report."""
    lines = ["=" * 60, "  AeroCast-NCR  —  Coupled Dataset Quality Report", "=" * 60, ""]

    if df.empty:
        lines.append("Dataset is EMPTY.")
        return "\n".join(lines)

    lines.append(f"Total rows          : {len(df):,}")
    lines.append(f"Columns             : {list(df.columns)}")
    lines.append("")

    if "station" in df.columns:
        lines.append("--- Rows per station ---")
        for stn, count in df["station"].value_counts().sort_index().items():
            lines.append(f"  {stn:20s}: {count:>8,}")
        lines.append("")

    if "timestamp" in df.columns:
        lines.append(f"Date range          : {df['timestamp'].min()} to {df['timestamp'].max()}")
        lines.append(f"Unique timestamps   : {df['timestamp'].nunique():,}")
        lines.append("")

    lines.append("--- Missing values (%) ---")
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    for col in numeric_cols:
        pct = df[col].isna().mean() * 100
        if pct > 0:
            lines.append(f"  {col:30s}: {pct:5.1f}%")
    if not any(df[c].isna().mean() * 100 > 0 for c in numeric_cols if c in df.columns):
        lines.append("  (none)")
    lines.append("")

    issues = validate(df)
    lines.append("--- Validation ---")
    for issue in issues:
        lines.append(f"  {issue}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Merge all data sources into coupled_dataset.csv"
    )
    parser.add_argument("--weather-dir", default=str(WEATHER_DIR))
    parser.add_argument("--pollution-dir", default=str(POLLUTION_DIR))
    parser.add_argument("--fire-dir", default=str(FIRE_DIR))
    parser.add_argument("--atmosphere-dir", default=str(ATMOSPHERE_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument(
        "--max-ffill",
        type=int,
        default=MAX_FFILL_HOURS,
        help=f"Max forward-fill hours (default {MAX_FFILL_HOURS}).",
    )
    args = parser.parse_args()

    weather_dir = Path(args.weather_dir)
    pollution_dir = Path(args.pollution_dir)
    fire_dir = Path(args.fire_dir)
    atmo_dir = Path(args.atmosphere_dir)
    output_dir = Path(args.output_dir)

    print("Building coupled dataset ...")
    print(f"  Weather dir     : {weather_dir}")
    print(f"  Pollution dir   : {pollution_dir}")
    print(f"  Fire dir        : {fire_dir}")
    print(f"  Atmosphere dir  : {atmo_dir}")
    print(f"  Output dir      : {output_dir}")
    print()

    # --- Load ---
    print("Loading weather data ...")
    weather = load_weather(weather_dir)
    print(f"  {len(weather):,} rows")

    print("Loading pollution data ...")
    pollution = load_pollution(pollution_dir)
    print(f"  {len(pollution):,} rows")

    print("Loading fire data ...")
    fire = load_fire(fire_dir)
    print(f"  {len(fire):,} rows")

    print("Loading atmosphere data ...")
    atmosphere = load_atmosphere(atmo_dir)
    print(f"  {len(atmosphere):,} rows")
    print()

    # --- Normalize ---
    for df_name, df in [("weather", weather), ("pollution", pollution),
                        ("fire", fire), ("atmosphere", atmosphere)]:
        if not df.empty:
            if "timestamp" in df.columns:
                normalize_timestamps(df, "time")
            elif "From Date" in df.columns:
                normalize_timestamps(df, "From Date")
            print(f"  {df_name}: timestamps normalized to UTC")

    # --- Merge ---
    print("\nMerging datasets ...")
    coupled = merge_datasets(weather, pollution, fire, atmosphere)

    if coupled.empty:
        print("Coupled dataset is empty — nothing to save.")
        return

    # --- Forward fill ---
    if "station" in coupled.columns:
        print(f"Forward-filling missing values (max {args.max_ffill}h) ...")
        coupled = forward_fill_missing(coupled, "station", max_hours=args.max_ffill)

# --- Remove final duplicated timestamps per station ---
    before = len(coupled)
    coupled.drop_duplicates(subset=["time", "station"], keep="last", inplace=True)
    coupled.sort_values(["station", "time"], inplace=True)
    coupled.reset_index(drop=True, inplace=True)
    after = len(coupled)
    if before != after:
        print(f"  Removed {before - after} duplicate rows")

    # --- Standardize time column name to `timestamp` (used by ML pipeline) ---
    if "time" in coupled.columns:
        coupled.rename(columns={"time": "timestamp"}, inplace=True)

    # --- Save ---
    os.makedirs(output_dir, exist_ok=True)
    out_csv = output_dir / "coupled_dataset.csv"
    coupled.to_csv(out_csv, index=False)
    print(f"\nSaved coupled dataset -> {out_csv}  ({len(coupled):,} rows)")

    # --- Quality report ---
    report = quality_report(coupled)
    report_path = output_dir / "quality_report.txt"
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"Quality report -> {report_path}")
    print()
    print(report)


if __name__ == "__main__":
    main()
