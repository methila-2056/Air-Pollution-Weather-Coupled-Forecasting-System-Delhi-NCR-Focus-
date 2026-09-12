# AeroCast-NCR Pollution Event Detection

> Rule-based detection of current / upcoming **pollution events** for a station,
> driven entirely by the trained PM2.5 forecast series and by observations
> already stored in the database. **No ML in the rule layer and no invented
> numbers**: every trigger value comes from the deployed XGBoost models and from
> stored CPCB / Open-Meteo / FIRMS-derived fields (see `docs/api.md` and
> `backend/app/services/pollution_event_service.py`).

---

## 1. Event types

| Event | Meaning | Primary trigger |
|-------|---------|-----------------|
| `pollution_surge` | Forecast PM2.5 rises sharply above the observed baseline | Peak ≥ 30 % above the 24h-observed baseline **and** ≥ 60 µg/m³ (24h NAAQS) |
| `pollution_relief` | Forecast PM2.5 drops sharply below the observed baseline | Minimum ≥ 25 % below baseline **with a dispersion-supporting atmosphere** (or a ≥ 45 % washout) |
| `high_risk_episode` | Forecast PM2.5 stays in the CPCB "Very Poor" tier for a full day | ≥ 121 µg/m³ sustained for ≥ 24 consecutive forecast hours **and** ≥ 1 active atmospheric risk contributor |

Each event carries a `severity` tier, the exact stored values that triggered it
(`contributing_factors`), and a `confidence` object derived from the model's own
split-conformal prediction interval at the trigger point.

---

## 2. Threshold provenance

### 2.1 National standards (government figures, cited)

| Threshold | Value | Source |
|-----------|-------|--------|
| PM2.5 24h NAAQS limit | 60 µg/m³ | India National Ambient Air Quality Standards (CPCB notification under the Environment (Protection) Act) |
| CPCB AQI "Very Poor" lower bound | 121 µg/m³ | CPCB AQI sub-index breakpoints (Very Poor band 121–250 µg/m³) |
| CPCB AQI "Severe" lower bound | 250 µg/m³ | CPCB AQI sub-index breakpoints (Severe band > 250 µg/m³) |

### 2.2 Operational conventions (documented, NOT government limits)

| Conventions | Value | Purpose |
|-------------|-------|---------|
| Surge relative increase | 30 % | Filters ordinary diurnal variability; flags meaningful forecast rises |
| Relief relative decrease | 25 % | Flags meaningful forecast falls |
| Relief washout drop | 45 % | Any drop this large counts as relief regardless of atmosphere |
| Episode sustained hours | 24 h | A full day in the "Very Poor" tier |

### 2.3 Atmospheric risk bands (reuse documented `atmosphere_service` / `transport_risk_service` bands)

| Factor | Active when | Band source |
|--------|-------------|-------------|
| `low_ventilation` | ventilation < 3000 m²/s | `atmosphere_service` (poor band) |
| `shallow_pbl` | PBL height < 300 m | documented PBL classification |
| `inversion` | inversion `detected` (lapse-rate or PBL proxy) | `ml/features/atmospheric_profile.py` |
| `stagnant_wind` | wind < 2 m/s | `atmosphere_service` (light wind) |
| `regional_transport` | transport risk level ≥ HIGH | `transport_risk_service` bands |

---

## 3. Detection rules (exact)

Given an observed 24h baseline `B` (mean of stored PM2.5 in the 24h before the
forecast release) and an hourly forecast series `{t_i, f_i}`:

### 3.1 `pollution_surge`

A contiguous run where `f_i >= max(B × 1.30, 60 µg/m³)`. The selected run is the
one with the highest peak. Report the peak, its timestamp, and:

- severity: `severe` if peak ≥ 250, `moderate` if peak ≥ 121, else `mild`.

### 3.2 `pollution_relief`

A contiguous run where `f_i <= B × 0.75`, but only if dispersion is supported
(`atmosphere_service` ventilation ≥ 6000 m²/s, or deep PBL ≥ 300 m with wind ≥
2 m/s, or drop ≤ B × 0.55 — i.e. a ≥ 45 % washout). Report the trough and its
timestamp.

- severity: `significant` if trough < 60 µg/m³, else `minor`.

### 3.3 `high_risk_episode`

Any contiguous run of ≥ 24 forecast hours where `f_i >= 121 µg/m³`, with at
least one active atmospheric risk contributor (Table 2.3). Report the peak and
the active contributors.

- severity: `emergency` if peak ≥ 250 or ≥ 2 active contributors, else `high`.

### 3.4 Timing / status

`contiguous` means consecutive hourly forecast points — gaps larger than one
hour break a run (the forecast serves sparse horizons, e.g. 1/6/12/24/48/72 h,
so honest contiguous-window semantics matter).

- `status`: `active` while "now" lies between the event's start and effective
  end; otherwise `forecast`. An event whose activated run reaches the end of the
  served forecast has no end (`end_time = None`) and is treated as ongoing, so
  it reports `active` while `now ≥ start`.

---

## 4. Confidence (uncertainty-aware)

Every event computes `margin` = predicted value at the trigger point minus the
trigger threshold, compared against the split-conformal half-width `w` at that
same forecast horizon:

| Condition | Label |
|-----------|-------|
| margin ≥ `w` | `high` — event is robust within the model interval |
| `w`/2 ≤ margin < `w` | `medium` — plausible but not interval-robust |
| margin < `w`/2 | `low` — sits inside the prediction interval |
| no interval for the horizon | `medium` (unquantified, disclosed) |

`lower_bound_ugm3`, `upper_bound_ugm3`, horizon test R², coverage target and the
uncertainty method are attached to every event so the confidence label is never
free-floating.

---

## 5. What this is NOT

- **Not a chemical transport simulation.** Surge/relief rules use only the
  forecast series + stored atmosphere; `ml/features/dispersion_solver.py` is the
  numerical 2D PDE transport module (`docs/api.md` → `/api/dispersion/forecast`).
- **Not government event validation.** Relative-change figures are operational
  conventions (Table 2.2), clearly labelled as such in the API response.

---

## 6. API

```
GET /api/events/current?station_name=<name>&hours=<1..72>
```

Returns `PollutionEventsCurrentResponse` (see `backend/app/schemas/schemas.py`):
the model card context (`model`, `forecast_strategy`, `uncertainty_method`,
`coverage_target`), the observed baseline and forecast peak, the event list, an
atmosphere summary, the threshold `methodology`, and `notes` for any detection
that was skipped (short horizon, missing baseline). Missing stations → 404; an
unavailable PM2.5 model pipeline → 503.

---

## 7. Implementation map

| Piece | File |
|-------|------|
| Rule engine (pure, deterministic) | `backend/app/services/pollution_event_service.py` (`detect_events_from_series`) |
| Orchestrator (forecast + baseline + atmosphere + transport risk) | `backend/app/services/pollution_event_service.py` (`detect_current_events`) |
| API router | `backend/app/api/events.py` |
| Response schemas | `backend/app/schemas/schemas.py` (`PollutionEvent*`) |
| Tests | `backend/tests/unit/test_pollution_events.py` |