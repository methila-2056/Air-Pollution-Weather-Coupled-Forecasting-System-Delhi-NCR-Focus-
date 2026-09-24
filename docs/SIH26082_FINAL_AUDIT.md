# SIH26082 — FINAL AUDIT

**AeroCast-NCR · Air Pollution–Weather Coupled Forecasting System (Delhi NCR Focus)**
Smart India Hackathon 2026 · Ministry of Earth Sciences / NCMRWF

> The rule for this audit: **a capability is `FULLY IMPLEMENTED` only when it is
> genuinely executed and measured — never merely simulated or visually
> represented.** Surrogates, proxies, adapters and gated engines are classified
> `PARTIALLY IMPLEMENTED` and named as such, with the exact boundary written down.

---

## A. Requirement coverage

Full requirement-level table: [`docs/SIH26082_IMPLEMENTATION_AUDIT.md`](SIH26082_IMPLEMENTATION_AUDIT.md)
(24 rows) and traceability in [`docs/SIH26082_TRACEABILITY.md`](SIH26082_TRACEABILITY.md).

Summary of the 24 capability rows:

- **IMPLEMENTED (23/24)** — two-way surrogate coupling, 9 coupling features, forward path,
  backward path, coupled loop, coupling-state persistence, 72h multi-pollutant forecasting,
  direct PM2.5 + conformal intervals, vertical pressure data (4 levels), lapse-rate inversion,
  PBL classification, fire features + transport pathway, 500 km ring + modelling domain,
  dispersion surrogate, GRU evaluation, CPCB/Open-Meteo/FIRMS ingestion, Indian AQI,
  SHAP explainability, alert engine (30 unit tests), chronological validation, dashboard/maps.
- **PARTIALLY IMPLEMENTED (1/24)** — real-engine WRF-Chem/HYSPLIT *run* (adapter contract and
  binaries/gating implemented; a live run requires operator-provided engine output by design).

## B. Scientific methodology

`FULLY IMPLEMENTED` — `docs/SCIENTIFIC_METHODOLOGY.md` documents problem definition, data
sources, preprocessing, atmospheric variables, PBLH, inversion, dispersion, fire influence,
coupling, ML architecture, feature engineering, AQI, validation, uncertainty methodology,
limitations and the WRF-Chem integration path — with exact formulas, constants and units.

## C. Data sources

`PARTIALLY IMPLEMENTED` — Live: CPCB (AQI/pollutants), Open-Meteo (surface + 1000/925/850/700 hPa,
PBLH), NASA FIRMS VIIRS (fires + FRP). Offline: ERA5 single-level reanalysis (`era5_surface.py`).
Gated by credentials: ERA5 (CDS) full pipeline and IMD (both report `reason` strings honestly).
Vertical full-profile reanalysis (multi-pressure ERA5 in live pipeline, IMD radar) remains the
documented production upgrade. Real data only; missing values render "Data unavailable".

## D. Model performance

`FULLY IMPLEMENTED` — MAE / RMSE / R² by model (persistence, Random Forest, XGBoost, GRU) ×
pollutant (PM2.5/PM10/O3/NO2) × horizon (1/6/12/24/48/72 h) on chronological held-out splits;
actual-vs-predicted, residual, error-distribution and split (train/validation/test) tables;
split-conformal coverage measured on the test set and reported as-is. `GET /api/model/performance`
+ Model Performance page. **Metrics are not "accuracy" — R² is goodness-of-fit on held-out data.**

## E. Coupling implementation

`PARTIALLY IMPLEMENTED` — Both directions exist and are measured:
- **met → chem:** wind/PBL/inversion/humidity/fire features feed all forecasters (forward path).
- **chem → met:** AOD proxy → radiation transmittance → PBL suppression → stability-coupling
  index → feedback multiplier, applied per time-step in the online coupled loop
  (`POST /api/forecast/coupled` returns both coupled and uncoupled series).

This is a **data-driven two-way coupling surrogate** (linear/sub-linear analytic closure), not a
physical radiation-transfer or chemistry scheme. Any claim of "physical WRF-Chem coupling" would
be false; the UI and docs use "surrogate/potential" wording. Because the PS asks for the stronger
*physical* interaction, classification is `PARTIALLY IMPLEMENTED` (functional surrogate fully
implemented).

## F. Inversion implementation

`PARTIALLY IMPLEMENTED` — Vertical temperature gradient (dT/dp × 100 K/100 hPa) over stored
1000/925/850/700 hPa layers; category NO/WEAK/MODERATE/STRONG with documented thresholds;
strength 0..1 ramp; documented PBL-height proxy fallback labelled `pbl_proxy` with a UMD-quality
"vertical profile unavailable — estimate limited" note. Not implemented: inversion *base/top
height, thickness, duration and persistence hours* over continuous time (requires a multi-day
vertical archive the dataset does not currently store), and multi-level live ERA5 ingestion.

## G. PBL implementation

`FULLY IMPLEMENTED` — PBLH is a first-class variable from Open-Meteo `boundary_layer_height`
(real NWP field). Classified LOW (<150 m)/MODERATE(<300)/HIGH; anomaly vs climatological band;
trend over last 24 h; ventilation potential (speed × PBLH); dispersion condition; confidence.
PBLH participates in every forecast and in the coupling engine. Displayed in Atmosphere panel and
forecast context. Thresholds documented as heuristics.

## H. Fire/stubble implementation

`FULLY IMPLEMENTED` — Real NASA FIRMS VIIRS detections stored (lat/lon/time/FRP/confidence);
500 km radius, upwind ±90° alignment, FRP-weighted impact, transport time (nearest ÷ wind),
transport-risk weighting, stubble-impact score; estimated transport pathway (top-6 corridors),
influence ring and corridor overlay on maps. Wording is "estimated fire-related transport
influence", never "guaranteed plume arrival". Crop-residue attribution is not claimed.

## I. Dispersion implementation

`PARTIALLY IMPLEMENTED` — A genuine numerical solver runs: finite-difference advection–diffusion–
deposition on the ~2.2 km NCR grid (CFL-safe, non-negativity preserving, FRP point sources under
wind/PBL/rain forcing) — this is a real lightweight transport model, clearly distinguished from
WRF-Chem-class chemistry. Because the PS names WRF-Chem or similar *full* frameworks, and the
boundary-layer chemistry is parametric, classification is `PARTIALLY IMPLEMENTED` with the
surrogate fully executed and documented.

## J. Two-way feedback implementation

`PARTIALLY IMPLEMENTED` — Pollution→meteorology feedback is implemented and measurable
(aerosol proxy → transmittance → PBL suppression → stability index → next-step feedback), fully
covered by `TestCouplingFeedback`. It is an **analytic/data-driven closure**, not physical
radiative transfer — classification is `PARTIALLY IMPLEMENTED` for the physical-coupling claim,
`FULLY` for the surrogate's own functionality. Lagged pollution values are used; no future leakage.

## K. Dashboard functionality

`FULLY IMPLEMENTED` — Operational layout: current AQI, 72h max forecast AQI, PM2.5, O3, PBLH,
inversion, dispersion, fire influence; 8 visualisations (72h AQI, pollutants, NCR map,
wind/dispersion, inversion/PBL, fire influence, explanation, alerts). Institutional styling;
SystemStatus + About + GRAP panels. Alerts phrased as risk ("expected", "risk") not certainty.

## L. Testing results

`FULLY IMPLEMENTED` — **635 tests passed**, `ruff check backend/app backend/tests` clean,
`ruff check ml` clean, `tsc --noEmit` clean, `vite build` clean. Coverage includes AQI, inversion,
PBLH handling, wind-vector (u/v), dispersion solver, fire influence, coupling engine, forecast
generation, 72h output, time-series split, data-leakage prevention and API validation. See
[§ L] rows in IMPLEMENTATION_AUDIT for the verification table.

## M. Security audit

`FULLY IMPLEMENTED` (within prototype scope) — JWT auth (`/api/auth/*`), scoped demo session,
CORS from env (`CORS_ORIGINS`), Pydantic request validation, parameterised SQLAlchemy queries
(no raw SQL injection surfaces), no key material committed (`.env` + `.env.example`), secrets
arrive via environment variables only (Render/Neon), no debug endpoints in production profile.
Prototype-appropriate notes: rate limiting is not enforced on public read endpoints (documented).

## N. Performance audit

`FULLY IMPLEMENTED` (documented) — SQLAlchemy indexes on time-series joins; GETs retry on Render
cold-start 502/503/504 with capped attempts; client-side 60 s timeout; IDW grid cached per window;
numerical solver vectorised (NumPy); charts render with `ResponsiveContainer`; maps cluster
stations; no unbounded payloads returned to the dashboard (horizon-limited APIs).

## O. Known limitations

1. Vertical archive is 4 pressure levels only (1000/925/850/700 hPa) — no multi-day vertical
   profile → inversion thickness/persistence/duration not yet computed.
2. ERA5 live (multi-level) and IMD live are credential-gated; ERA5 reanalysis offline only.
3. Coupling feedback and fire transport are **surrogates/estimates**; no physical WRF-Chem run.
4. Long-horizon NO₂/SO₂ skill is modest (≈0.21/0.15 R² @72h); uncertainty shown where computed.
5. GRU is evaluated but not the serving model (XGBoost is); documented honestly.
6. Model metrics reflect the most recent chronological evaluation run only.

## P. Future improvements

1. Multi-day vertical ERA5 archive → inversion base/top/thickness/duration/persistence + confidence.
2. Operator-deployed WRF-Chem/HYSPLIT consumption through the existing gated adapters.
3. Live IMD / ERA5-CDS ingestion with credential gate already in place.
4. Ensemble spread + quantile regression as extra uncertainty methods beside split-conformal.
5. Rate limiting and staged public-key read endpoints before any non-hackathon operation.

---

**Coverage roll-up (24 capability rows):** 23 IMPLEMENTED · 1 PARTIALLY IMPLEMENTED · 0 NOT
IMPLEMENTED. The partial item is the real-engine WRF-Chem/HYSPLIT run — implemented as a strict
adapter/gate, not as an executed HPC coupled simulation. Nothing in this system claims physical
WRF-Chem operation, guarantees plume arrival, or fabricates sensor/model values.