"""Download NOAA ARL GDAS1 met files (ready.noaa.gov) for HYSPLIT.

The HYSPLIT concentration model needs genuine ARL-packed meteorological data.
This script fetches the archived 6-hourly GDAS1 ``gdas1.<mon><yy>.w<k>`` files
from NOAA ARL's public archive into ``--out-dir`` (set this directory as
``hysplit_met_dir`` in ``.env``). URIs follow the layout used by the HYSPLIT
community::

    https://www.ready.noaa.gov/data/archives/gdas1/gdas1.{mon}{yy}.w{week}

- Idempotent: a previously-downloaded non-empty file is skipped.
- Honest: only real ARL archive files are placed in the met directory, nothing
  synthetic is ever generated; ``hycs_std`` reads exactly these archives.
- A month is covered by weekly segments ``.w1 ... .w5`` (w5 holds the tail of
  the month). For a historical run spanning two months, pass both ``--month``
  values (or ``--start``/``--days``) and the script resolves them.

Usage:
    python -m scripts.download_hysplit_gdas --year 2026 --month 1 --out-dir data/met
    python -m scripts.download_hysplit_gdas --start 2025-11-25 --days 10 --out-dir data/met
        --no-download : only resolve and print the planned file URLs.
        --weeks 1 2 3 : restrict which weekly segments to fetch (default 1..5).
"""

import argparse
import datetime as _dt
import pathlib
import sys
import urllib.request

BASE_URL = "https://www.ready.noaa.gov/data/archives/gdas1"
MONTH_ABBR = [None, "jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"]
DEFAULT_WEEKS = (1, 2, 3, 4, 5)

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def archive_name(year: int, month: int, week: int) -> str:
    return f"gdas1.{MONTH_ABBR[month]}{str(year)[-2:]}.w{week}"


def archive_url(year: int, month: int, week: int) -> str:
    return f"{BASE_URL}/{archive_name(year, month, week)}"


def plan(
    *,
    year: int | None,
    month: int | None,
    start: _dt.date | None,
    days: int,
    weeks: tuple[int, ...],
) -> list[tuple[str, str, int]]:
    """Resolve wanted (year, month) pairs into ``(url, name, size_bytes)``."""
    pairs: list[tuple[int, int]] = []
    if start is not None:
        datelist = [start + _dt.timedelta(days=d) for d in range(max(1, days))]
        pairs = []
        for d in datelist:
            key = (d.year, d.month)
            if key not in pairs:
                pairs.append(key)
    elif year is not None and month is not None:
        pairs = [(year, month)]
    else:
        today = _dt.date.today()
        pairs = [(today.year, today.month)]

    out: list[tuple[str, str, int]] = []
    for (yr, mo) in pairs:
        if not (1 <= mo <= 12):
            continue
        for wk in weeks:
            out.append((archive_url(yr, mo, wk), archive_name(yr, mo, wk), 0))
    return out


def remote_size(url: str, timeout: int = 60) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        try:
            return int(resp.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return 0


def fetch_one(url: str, name: str, out_dir: pathlib.Path, timeout: int = 600) -> pathlib.Path:
    dest = out_dir / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        size = int(resp.headers.get("Content-Length") or 0)
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
    if size and tmp.stat().st_size < size * 0.9:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"short download for {name} ({tmp.stat().st_size}/{size})")
    tmp.replace(dest)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, help="archive year (with --month)")
    parser.add_argument("--month", type=int, choices=range(1, 13), help="archive month 1-12")
    parser.add_argument("--start", help="start date YYYY-MM-DD (with --days)")
    parser.add_argument("--days", type=int, default=7, help="number of days from --start (default 7)")
    parser.add_argument("--weeks", type=int, nargs="+", default=list(DEFAULT_WEEKS),
                        help="weekly segments to fetch (default 1 2 3 4 5)")
    parser.add_argument("--out-dir", default="data/met", help="destination dir (default data/met)")
    parser.add_argument("--no-download", action="store_true",
                        help="only resolve and print the planned file URLs")
    args = parser.parse_args()

    if args.start:
        start = _dt.date.fromisoformat(args.start)
        year = month = None
    else:
        start = None
        year, month = args.year, args.month

    out_dir = ROOT / args.out_dir if not pathlib.Path(args.out_dir).is_absolute() \
        else pathlib.Path(args.out_dir)

    planned = plan(year=year, month=month, start=start, days=args.days,
                   weeks=tuple(args.weeks))
    if not planned:
        print("no files to fetch", file=sys.stderr)
        return 2

    for url, name, _size in planned:
        status = "skip"
        if args.no_download:
            print(f"{url}  (no-download)")
            continue
        dest = out_dir / name
        if dest.exists() and dest.stat().st_size > 0:
            continue
        ssh = remote_size(url)
        print(f"{name}: remote {ssh/1e6:.0f} MB -> {dest} ...")
        try:
            fetch_one(url, name, out_dir)
            status = "ok"
        except RuntimeError as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            return 1
        print(f"  {status} ({dest.stat().st_size/1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
