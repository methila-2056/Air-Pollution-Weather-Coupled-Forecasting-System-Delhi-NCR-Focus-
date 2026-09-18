# NOAA HYSPLIT adapter (R6 / WS-4)

AeroCast-NCR integrates a **real**, locally-installed NOAA HYSPLIT concentration
model (`hycs_std`) as the highest-priority chemical-transport engine. This page
documents exactly what runs, what is gated, and what is never done.

## Scope and honesty contract

The project **never simulates HYSPLIT**. The analysis-to-dispersion path is:

1. `ml/ctm/hysplit_adapter.py` renders a standard CONTROL file (line layout
   mirrors NOAA ARL's own `utilhysplit` `hcontrol.py`).
2. It launches the genuine `exec/hycs_std(.exe)` from `HYSPLIT_HOME` with that
   CONTROL in a working directory.
3. It reads the binary concentration dump with ARL's own record layout via a
   parser that was validated **byte-for-byte against the real `cdump.bin`**
   shipped in the `noaa-oar-arl/utilhysplit` test suite
   (`testing/test_isoch/cdump.bin`, 63,000 bytes; `model_id=GFSG`,
   grid 301×601, nlev 1 × 500 m, 12 sampling blocks).
4. The genuine plume is regridded (inverse-distance weighting) onto the NCR
   grid and composed with the coupled forecast as documented in
   `backend/app/services/dispersion_service.py`.

If any ingredient is missing, `is_available()` is `False`, `run()` raises
`CtmUnavailable` with the exact missing item, and the documented analytic
surrogate stays active. **No sample output is ever generated.**

## Requirements

- **HYSPLIT binary**: point `HYSPLIT_HOME` (or `.env` `hysplit_home=`) at a real
  HYSPLIT *PC/Mac/Linux* installation whose `exec/hycs_std(.exe)` exists. Get it
  from https://www.ready.noaa.gov/HYSPLIT.php.
- **Meteorological data**: genuine ARL met files under `HYSPLIT_MET_DIR`
  (`.env` `hysplit_met_dir=`). Fetch the GDAS1 archives with:

  ```powershell
  python -m scripts.download_hysplit_gdas --year 2026 --month 1 --out-dir data/met
  ```

  The downloader targets NOAA ARL's verified archive scheme
  `https://www.ready.noaa.gov/data/archives/gdas1/gdas1.<mon><yy>.w<week>`
  (HEAD 200 confirmed this session; ~600 MB/week), is idempotent, and fetches
  nothing synthetic.

## cdump format (what the reader consumes)

Fortran-unformatted records are symmetric `[len i4][payload][len i4]`. Physical
records, in order:

| Record | Content |
|--------|---------|
| header | model id (a4) + met clock (7×i4) |
| ×nstartloc | release clock (4×i4) + lat/lon/ht (3×f4) + minutes (i4) |
| grid | nlat,nlon (i4); dlat,dlon,llcrnr_lat,llcrnr_lon (f4) |
| levels | nlev (i4) + level heights (nlev×i4) — one record |
| species | pollutant count (i4) + names (npoll×a4) — one record |
| per sampling period | start clock (6×i4), stop clock (6×i4) |
| per (level×pollutant) | poll name (a4), level (i4), element count ne (i4) + ne×`(indx i2, jndx i2, conc f4)` — one record |

A malformed or asymmetric record raises `CtmUnavailable` so the caller falls
back rather than trusting garbage.

## Wiring

`backend/app/services/dispersion_service.py` calls `available_engines(...)`/
`run_best_engine(...)`; on success the engine's plume **pattern** (min–max
normalized per frame) is composited 50/50 with the coupled data-driven forecast
surface, and the response sets `mode`, `composite`, and `ctm` fields explaining
the blend and the genuine source. Units are stated as relative model
concentration (*per nominal 1000 kg/h single source at Anand Vihar*), never
silently converted to absolute µg/m³.

## Tests

`backend/tests/unit/test_ctm_engines.py` covers CONTROL line layout, synthetic
cdump round-trip (spec-exact big-endian fixture), NCR surface regrid, malformed/
asymmetric record rejection, availability gating, registry ordering, and the
genuine-engine composite logic.