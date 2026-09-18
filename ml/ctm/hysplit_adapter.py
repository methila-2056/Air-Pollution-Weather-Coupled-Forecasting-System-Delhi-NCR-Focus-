"""NOAA HYSPLIT (hycs_std) dispersion-engine adapter (SIH26082 R6).

A first-party driver for a *real, installed* HYSPLIT concentration model:

- ``hysplit_home`` (config setting / HYSPLIT_HOME) must point at an HYSPLIT
  installation whose ``exec/hycs_std(.exe)`` executable exists.
- ``hysplit_met_dir`` (config setting / HYSPLIT_MET_DIR) must contain genuine
  ARL meteorological files, e.g. the GDAS archives fetched by
  ``scripts/download_hysplit_gdas.py`` (ready.noaa.gov file scheme).

The adapter writes a standard CONTROL file (line layout mirrors NOAA ARL's own
``utilhysplit`` reader), launches ``hycs_std``, reads the binary concentration
dump (``cdump``) using ARL's own record layout (verified byte-for-byte against
the real ``cdump.bin`` archived in ``noaa-oar-arl/utilhysplit``), and regrids
the plume onto the caller's lat/lon grid.

Honesty rules:

- ``is_available()`` is True only when the real executable and real met data
  are present; ``run()`` otherwise raises ``CtmUnavailable`` listing exactly
  what is missing.
- No synthetic "sample" output is ever produced: the plume surface always comes
  from a live ``hycs_std`` process.
- The concentration level is relative to the emission rate chosen because a
  nominal single source is used; ``units`` and ``metadata`` state this plainly.
"""

from __future__ import annotations

import datetime as _dt
import os
import pathlib
import subprocess
import tempfile
from dataclasses import dataclass, field

import numpy as np

from .ctm_interface import CtmResult, CtmUnavailable, register
from .regrid import idw_regrid

# Vertical motion method 1 = terrain-following isosigma; model top 10 km.
_VERTICAL_MOTION = 1
_MODEL_TOP_M = 10000
_SOURCE_DEFAULT = (28.6492, 77.2918, 50.0)  # representative Anand Vihar point
_SPECIES_NAME = "PM25"  # 4 chars, fits the cdump a4 pollutant field
_NOMINAL_RATE_KG_H = 1000.0
_EXE_CANDIDATES = ("hycs_std", "hycs_std.exe", "hycs_std.EXE")
_MET_PATTERNS = ("gdas*.arl", "gdas*.ARL", "gdas*.blb", "gdas*.BLB",
                 "edas*.arl", "edas*.ARL", "edas*.blb")


# ---------------------------------------------------------------------------
# CONTROL file writer - line layout mirrors NOAA ARL's utilhysplit
# ---------------------------------------------------------------------------
def build_control_text(
    *,
    start: _dt.datetime,
    duration_hours: int,
    sources: list[tuple[float, float, float]],
    met_files: list[tuple[str, str]],
    center_lat: float,
    center_lon: float,
    grid_spacing: float,
    lat_span: float,
    lon_span: float,
    output_dir: str,
    output_file: str = "cdump",
    species_name: str = _SPECIES_NAME,
    emission_rate: float = _NOMINAL_RATE_KG_H,
    vertical_motion: int = _VERTICAL_MOTION,
    model_top_m: int = _MODEL_TOP_M,
    levels: list[int] | None = None,
) -> str:
    """Render a standard HYSPLIT concentration CONTROL file."""
    levels = levels or [0]

    def _trailing(p: str) -> str:
        return p if p.endswith(("/", "\\")) else p + "/"

    lines: list[str] = [
        start.strftime("%y %m %d %H %M"),
        str(len(sources)),
    ]
    for lat, lon, alt in sources:
        lines.append(f"{lat:.4f} {lon:.4f} {alt:.1f}")
    lines += [
        str(int(duration_hours)),
        str(int(vertical_motion)),
        str(int(model_top_m)),
        str(len(met_files)),
    ]
    for met_dir, met_name in met_files:
        lines.append(_trailing(met_dir))
        lines.append(met_name)
    lines += [
        "1",  # number of pollutant species
        species_name,
        f"{emission_rate:.1f}",
        f"{float(duration_hours):.2f}",
        "00 00 00 00 00",  # release begins at simulation start
        "1",  # number of concentration grids
        f"{center_lat:.4f} {center_lon:.4f}",
        f"{grid_spacing:.6f} {grid_spacing:.6f}",
        f"{lat_span:.4f} {lon_span:.4f}",
        _trailing(output_dir),
        output_file,
        str(len(levels)),
        " ".join(str(int(lev)) for lev in levels),
        "00 00 00 00 00",  # sampling start == simulation start
        "00 00 00 00 00",  # sampling stop (bounded by run end)
        "0 01 00",  # 1-hour average concentration sampling
        "1",  # deposition definitions for the single species
        "0.0 0.0 0.0",  # particle diameter / density / shape (gas)
        "0.0 0.0 0.0 0.0 0.0",  # dry-deposition / resistance terms
        "0.0 0.0 0.0",  # wet-removal terms
        "0.0",  # radioactive decay half-life
        "0.0",  # resuspension factor
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# cdump binary reader - ARL utilhysplit/monetio record layout. Records are
# Fortran-unformatted [len][payload][len]. Physical record layout (verified
# against the real `cdump.bin` archived in noaa-oar-arl/utilhysplit):
#   rec0   model id (a4) + met clock (7 x i4)
#   rec1.. per start location: release clock (4 x i4) + lat/lon/ht (3 x f4)
#   rec_+3 grid: nlat,nlon (i4); dlat,dlon,llcrnr_lat,llcrnr_lon (f4)
#   rec   nlev (i4) + level heights (nlev x i4), one record
#   rec   pollutant count (i4) + pollutant names (npoll x a4), one record
#   then per sampling period:
#   rec   start time (oyear,omonth,oday,ohr,omin,oforecast = 6 x i4)
#   rec   stop time (same layout)
#   per (level x pollutant): one record:
#         poll name (a4), level (i4), element count ne (i4), then ne x
#         (indx i2, jndx i2, conc f4) triples.
# A malformed record boundary raises CtmUnavailable so the caller falls back
# to the analytic surrogate rather than trusting garbage.
# ---------------------------------------------------------------------------
_I4 = np.dtype(">i4")
_REC_3 = np.dtype([("nlat", ">i4"), ("nlon", ">i4"), ("dlat", ">f4"),
                   ("dlon", ">f4"), ("llcrnr_lat", ">f4"),
                   ("llcrnr_lon", ">f4")])
_REC_6 = np.dtype([("oyear", ">i4"), ("omonth", ">i4"), ("oday", ">i4"),
                   ("ohr", ">i4"), ("omin", ">i4"), ("oforecast", ">i4")])
_REC_8B = np.dtype([("indx", ">i2"), ("jndx", ">i2"), ("conc", ">f4")])


def _record(buf: bytes, off: int) -> tuple[bytes, int]:
    """Read one [len][payload][len] record; return (payload, next_offset)."""
    if off + 8 > len(buf):
        raise CtmUnavailable(f"cdump truncated at byte {off}")
    len1 = int(np.frombuffer(buf, dtype=_I4, count=1, offset=off)[0])
    if len1 < 0 or off + 8 + len1 > len(buf):
        raise CtmUnavailable(f"cdump record at byte {off} falls off the file")
    len2 = int(np.frombuffer(buf, dtype=_I4, count=1, offset=off + 4 + len1)[0])
    if len1 != len2:
        raise CtmUnavailable(
            f"cdump record at byte {off} asymmetric (len1={len1} len2={len2})"
        )
    return buf[off + 4 : off + 4 + len1], off + 8 + len1


def _i4s(payload: bytes) -> np.ndarray:
    return np.frombuffer(payload, dtype=_I4)


@dataclass
class CdumpRecord:
    """One (time, level, pollutant) block extracted from a cdump file."""

    time: _dt.datetime
    level: int
    pollutant: str
    indx: np.ndarray
    jndx: np.ndarray
    conc: np.ndarray


@dataclass
class CdumpFile:
    """Metadata + per-sampling-period records from one cdump file."""

    model_id: str
    nlat: int
    nlon: int
    dlat: float
    dlon: float
    llcrnr_lat: float
    llcrnr_lon: float
    levels: list[int]
    species: list[str]
    sample_time_hours: float
    records: list[CdumpRecord] = field(default_factory=list)


def _clock_to_dt(clock: np.ndarray) -> _dt.datetime:
    yy = int(clock[0])
    return _dt.datetime((2000 if yy < 50 else 1900) + yy, int(clock[1]),
                        int(clock[2]), int(clock[3]), int(clock[4]))


def read_cdump(path: str | os.PathLike) -> CdumpFile:
    """Parse a HYSPLIT concentration dump into a ``CdumpFile``."""
    buf = pathlib.Path(path).read_bytes()

    payload, off = _record(buf, 0)
    meta = _i4s(payload)
    # meta[0] are the model-id bytes read as one big-endian int32.
    model_id = payload[:4].decode("ascii", errors="replace").strip()
    nstartloc = int(meta[6]) if meta.size >= 8 else 1
    if not (1 <= nstartloc <= 50):
        raise CtmUnavailable(f"cdump implausible start-location count {nstartloc}")

    for _ in range(nstartloc):
        _, off = _record(buf, off)

    payload, off = _record(buf, off)
    grid = np.frombuffer(payload, dtype=_REC_3)[0]

    payload, off = _record(buf, off)
    levels_i = _i4s(payload)
    nlev = int(levels_i[0])
    if not (1 <= nlev <= 100) or len(levels_i) != nlev + 1:
        raise CtmUnavailable(f"cdump implausible level record (nlev={nlev} n={len(levels_i)})")
    levels = [int(x) for x in levels_i[1:]]

    payload, off = _record(buf, off)
    npoll = int(_i4s(payload)[0])
    if not (1 <= npoll <= 20) or len(payload) != 4 * (npoll + 1):
        raise CtmUnavailable(f"cdump implausible poll record (npoll={npoll} n={len(payload)})")
    species = [payload[4 + 4 * i : 8 + 4 * i].decode("ascii", errors="replace").strip()
               for i in range(npoll)]

    records: list[CdumpRecord] = []
    sample_time_hours = 1.0
    while off < len(buf):
        try:
            t_start = _clock_to_dt(_i4s(_record(buf, off)[0]))
            off = _record(buf, off)[1]
            t_stop = _clock_to_dt(_i4s(_record(buf, off)[0]))
            off = _record(buf, off)[1]
        except CtmUnavailable:
            break
        delta = (t_stop - t_start).total_seconds()
        if delta > 0:
            sample_time_hours = delta / 3600.0
        for _ in range(nlev):
            for _ in range(npoll):
                payload, off = _record(buf, off)
                if len(payload) < 12:
                    raise CtmUnavailable(f"cdump truncated concentration record at byte {off - 8 - len(payload)}")
                poll_name = payload[:4].decode("ascii", errors="replace").strip()
                lev = int(_i4s(payload[4:8])[0])
                ne = int(_i4s(payload[8:12])[0])
                if ne < 0 or len(payload) != 12 + 8 * ne:
                    raise CtmUnavailable(
                        f"cdump concentration record size mismatch (ne={ne} n={len(payload)})"
                    )
                if ne:
                    pts = np.frombuffer(payload[12:], dtype=_REC_8B)
                    records.append(CdumpRecord(
                        time=t_start, level=lev, pollutant=poll_name,
                        indx=pts["indx"], jndx=pts["jndx"], conc=pts["conc"],
                    ))

    return CdumpFile(
        model_id=model_id,
        nlat=int(grid["nlat"]), nlon=int(grid["nlon"]),
        dlat=float(grid["dlat"]), dlon=float(grid["dlon"]),
        llcrnr_lat=float(grid["llcrnr_lat"]), llcrnr_lon=float(grid["llcrnr_lon"]),
        levels=levels, species=species,
        sample_time_hours=sample_time_hours, records=records,
    )


def cdump_to_surface(
    cdump: CdumpFile,
    *,
    lat_axis: np.ndarray,
    lon_axis: np.ndarray,
) -> tuple[list[_dt.datetime], np.ndarray]:
    """Regrid cdump points (summed over pollutants) onto a regular grid.

    Returns ``(times, surface)`` with ``surface`` of shape (T, nlat, nlon).
    Cells within the NCR footprint but without any HYSPLIT data are 0 — the
    sparse plume is never over-spread beyond its own footprint.
    """
    groups: dict[_dt.datetime, list[np.ndarray]] = {}
    for rec in cdump.records:
        glat = cdump.llcrnr_lat + (rec.jndx.astype(float) - 1.0) * cdump.dlat
        glon = cdump.llcrnr_lon + (rec.indx.astype(float) - 1.0) * cdump.dlon
        groups.setdefault(rec.time, []).append(np.column_stack([glat, glon, rec.conc]))

    dst_lat, dst_lon = np.meshgrid(lat_axis, lon_axis, indexing="ij")
    dst_lat = dst_lat.ravel()
    dst_lon = dst_lon.ravel()

    times: list[_dt.datetime] = []
    surface: list[np.ndarray] = []

    def interpolate(time: _dt.datetime) -> np.ndarray:
        stack = groups[time]
        if not stack:
            return np.zeros_like(dst_lat)
        src_lat = np.concatenate([s[:, 0] for s in stack])
        src_lon = np.concatenate([s[:, 1] for s in stack])
        src_val = np.concatenate([s[:, 2] for s in stack])
        return idw_regrid(src_lat, src_lon, src_val, dst_lat, dst_lon)

    for t in sorted(groups):
        flat = interpolate(t)
        times.append(t)
        surface.append(np.asarray(flat).reshape(len(lat_axis), len(lon_axis)))
    return times, np.asarray(surface)


@register
class HysplitAdapter:
    """Run the real NOAA HYSPLIT concentration model on this host."""

    name = "HYSPLIT (NOAA)"

    def __init__(
        self,
        hysplit_home: str | pathlib.Path | None = None,
        met_dir: str | pathlib.Path | None = None,
        working_dir: str | pathlib.Path | None = None,
    ):
        if hysplit_home is None:
            try:
                from backend.app.config import get_settings
                hysplit_home = get_settings().hysplit_home
            except Exception:
                hysplit_home = os.environ.get("HYSPLIT_HOME", "")
        if met_dir is None:
            try:
                from backend.app.config import get_settings
                met_dir = get_settings().hysplit_met_dir
            except Exception:
                met_dir = os.environ.get("HYSPLIT_MET_DIR", "")
        self.hysplit_home = pathlib.Path(hysplit_home) if hysplit_home else None
        self.met_dir = pathlib.Path(met_dir) if met_dir else None
        self.working_dir = pathlib.Path(working_dir) if working_dir else None

    # -- availability -------------------------------------------------------
    @property
    def executable(self) -> pathlib.Path | None:
        if self.hysplit_home is None:
            return None
        for cand in _EXE_CANDIDATES:
            candidate = self.hysplit_home / "exec" / cand
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _met_files(self) -> list[tuple[str, str]]:
        if self.met_dir is None or not self.met_dir.is_dir():
            return []
        found: list[tuple[str, str]] = []
        for pattern in _MET_PATTERNS:
            for match in sorted(self.met_dir.glob(pattern)):
                found.append((str(self.met_dir), match.name))
        return found

    def unavailable_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.hysplit_home is None:
            reasons.append("HYSPLIT_HOME is not configured (hysplit_home setting)")
        elif self.executable is None:
            reasons.append(f"no hycs_std executable under {self.hysplit_home / 'exec'}")
        if self.met_dir is None:
            reasons.append("HYSPLIT_MET_DIR is not configured (hysplit_met_dir setting)")
        elif not self._met_files():
            reasons.append(
                f"no ARL met files (gdas*/edas*/*.arl|*.blb) found in {self.met_dir}; "
                "run scripts/download_hysplit_gdas.py"
            )
        return reasons

    def is_available(self) -> bool:
        return not self.unavailable_reasons()

    # -- execution ----------------------------------------------------------
    def run(
        self,
        start_utc: _dt.datetime,
        hours: int,
        domain: dict[str, float],
        grid_step: float,
        sources: list[dict[str, float]] | None = None,
    ) -> CtmResult:
        reasons = self.unavailable_reasons()
        if reasons:
            raise CtmUnavailable("HYSPLIT unavailable:\n  - " + "\n  - ".join(reasons))
        exe = self.executable
        assert exe is not None and self.met_dir is not None

        met = self._met_files()
        if not met:
            raise CtmUnavailable("HYSPLIT: no ARL meteorological files available")

        start = start_utc.replace(tzinfo=None)
        lat_axis = np.arange(domain["lat_min"], domain["lat_max"] + 1e-9, grid_step)
        lon_axis = np.arange(domain["lon_min"], domain["lon_max"] + 1e-9, grid_step)

        if sources:
            src = [(float(s["lat"]), float(s["lon"]), float(s.get("alt", 50.0)))
                   for s in sources]
        else:
            src = [_SOURCE_DEFAULT]

        center_lat = (float(domain["lat_min"]) + float(domain["lat_max"])) / 2.0
        center_lon = (float(domain["lon_min"]) + float(domain["lon_max"])) / 2.0
        lat_span = float(domain["lat_max"]) - float(domain["lat_min"])
        lon_span = float(domain["lon_max"]) - float(domain["lon_min"])

        working = self.working_dir or pathlib.Path(
            tempfile.mkdtemp(prefix="hysplit_run_")
        )
        working.mkdir(parents=True, exist_ok=True)

        control = build_control_text(
            start=start,
            duration_hours=int(hours),
            sources=src,
            met_files=met,
            center_lat=center_lat,
            center_lon=center_lon,
            grid_spacing=float(grid_step),
            lat_span=lat_span,
            lon_span=lon_span,
            output_dir=str(working),
            output_file="cdump",
        )
        (working / "CONTROL").write_text(control, encoding="ascii")

        timeout = min(3600, max(120, 12 * int(hours)))
        proc = subprocess.run(
            [str(exe)],
            cwd=working,
            timeout=timeout,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or b"").decode("utf-8", errors="replace")
            raise CtmUnavailable(
                f"HYSPLIT: hycs_std failed (rc={proc.returncode}): {detail[:400]}"
            )

        cdump_files = sorted(working.glob("cdump*"))
        if not cdump_files:
            raise CtmUnavailable("HYSPLIT: hycs_std produced no cdump output")
        try:
            cdump = read_cdump(cdump_files[0])
        except CtmUnavailable as exc:
            raise CtmUnavailable(f"HYSPLIT: could not parse cdump output: {exc}") from exc

        times, surface = cdump_to_surface(cdump, lat_axis=lat_axis, lon_axis=lon_axis)
        if surface.shape[0] == 0:
            raise CtmUnavailable("HYSPLIT: no concentration grid points in output")

        return CtmResult(
            engine=self.name,
            pollutant="PM2.5",
            units="relative model concentration (kg emitted per grid cell)",
            start_utc=start,
            times_utc=times,
            data=surface,
            lat=lat_axis,
            lon=lon_axis,
            metadata={
                "provenance": "genuine NOAA HYSPLIT hycs_std run",
                "model_id": cdump.model_id,
                "met_dir": str(self.met_dir),
                "species": cdump.species,
                "levels": cdump.levels,
                "sample_time_hours": cdump.sample_time_hours,
                "nominal_emission_kg_h": _NOMINAL_RATE_KG_H,
                "units": "relative model concentration",
            },
        )
