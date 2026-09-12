# AeroCast-NCR What-If Scenario Analysis

> **Read-only, explicitly-labelled what-if analysis.** A scenario changes ONLY
> the inputs you asked for — wind speed, wind direction, PBL height, regional
> fire activity, inversion — on an in-memory copy of the forecast feature row,
> then re-runs the **same trained XGBoost PM2.5 models** on that changed row.
> The service issues only SELECT queries; it never flushes, commits, or writes.
> The response is a what-if estimate of the model's response, **not** a
> measurement, a causal claim, or an emissions/dispersion simulation.

---

## 1. What a scenario is (and is not)

| | |
|---|---|
| Baseline forecast | Model output on the **unchanged** feature row built from stored observations. |
| Scenario forecast | Model output on the same row after ONLY the requested inputs changed. |
| Difference | `scenario − baseline` per horizon. A model-response estimate, not causality. |
| Observed | The last stored PM2.5 observation used as the model's anchor — never modified. |

Every response carries `label: "SCENARIO ANALYSIS"`, a `disclaimer`, a
`value_kinds` legend (observed / forecast / scenario / difference), and a
`data_integrity` block (`mode: "read_only"`, `database_writes: 0`).

---

## 2. Supported input changes

| Input | `mode`| Semantics |
|-------|-------|-----------|
| `wind_speed` | `absolute` / `relative` | absolute replaces the stored m/s value; relative **multiplies** it (2.0 = double, 0.5 = half) |
| `wind_direction` | `absolute` / `relative` | absolute sets degrees (0–360); relative **adds** a rotation in degrees |
| `pbl_height` | `absolute` / `relative` | absolute/relative metres; ventilation + inversion are re-derived |
| `fire_activity` | `relative` only | an FRP intensity **multiplier** (> 0) |
| `inversion` | — | `{detected: bool, strength?: 0–1}` overrides the derived indicator |

At least one change is required (empty `changes` → 422).

### 2.1 Re-derivation is consistent with training

The perturbed row is a one-row copy of the aligned observation row, and the
**training-time** feature functions are re-run on it:
`add_atmosphere_and_temporal_features` + `add_fire_features`
(`ml/preprocessing/training_dataset.py`). Because these functions are recomputed
rather than patched, no derived feature goes stale:

- `wind_speed` → `ventilation_coefficient`, `transport_time_hours`,
  wind-sensitive fire transport terms.
- `wind_direction` → `wind_dir_sin`/`wind_dir_cos`, wind-aligned fire terms
  (recomputed against REAL stored fire geometry).
- `pbl_height` → `ventilation_coefficient` and the inversion indicator (via the
  PBL lapse-rate proxy). The `input_changes` panel also lists the re-derived
  inversion values when they actually change.
- `fire_activity` → the FRP-weighted intensity terms `fire_impact_score`,
  `transport_risk`, `stubble_impact_score` only. Detected fire **counts**
  (`fire_count`, `wind_aligned_fire_count`), distance and transport-time terms
  keep their REAL observed values — a multiplier simulates more-intense fires,
  not more fires. Scores pass through the logistic `_normalize_impact`, so they
  respond monotonically but not linearly.

### 2.2 Validation

- `relative` requires a present baseline value (else 422 — use `absolute`).
- `fire_activity.multiplier` must be > 0 (clamped to ≤ 100).
- `hours` ∈ 1..72; a request beyond the trained horizon range → 503.

---

## 3. API

```
POST /api/scenario/analysis
Content-Type: application/json

{
  "station_name": "Anand Vihar",          // optional; defaults to first station
  "hours": 24,                            // optional; default 72, max 72
  "changes": {
    "wind_speed":   {"mode": "relative", "value": 2.0},
    "pbl_height":   {"mode": "absolute", "value": 500.0},
    "fire_activity":{"mode": "relative", "multiplier": 2.0},
    "inversion":    {"detected": false, "strength": 0.1}
  }
}
```

Response is `ScenarioAnalysisResponse`
(`backend/app/schemas/schemas.py`) with:

- `baseline_forecast` / `scene_forecast`: `{peak_pm25, mean_pm25,
  forecasts:[Pm25ForecastPoint…]}` (bounds + horizon test metrics attached).
- `difference`: `{peak_difference_pm25, mean_difference_pm25, points:[…]}`.
- `observed`: anchor PM2.5 (and lag-1) with its timestamp.
- `input_changes`: `[{feature, unit, baseline_value, scenario_value}]`.
- `notes`: transparent documentation of how each change was applied.
- `data_integrity`: read-only proof block.

Status codes: 200 OK · 404 unknown station · 422 no/invalid changes or
relative-without-baseline · 503 models not trained / horizon not covered ·
500 defensive pipeline failure.

---

## 4. Read-only guarantee

The engine (`run_scenario_analysis`) performs only db.query() (stations,
weather, fires) inside the existing forecast pipeline's `build_feature_row`.
There is no `add`, `flush`, or `commit` anywhere in `scenario_service.py`. The
safety is enforced by tests, not just prose:

`backend/tests/unit/test_scenario_analysis.py` →
`test_scenario_run_leaves_database_unchanged` snapshots **every row of every
table** before and after a full scenario run (with the pipeline standing in for
the models) and asserts the database is byte-for-byte identical.

---

## 5. Implementation map

| Piece | File |
|-------|------|
| Scenario engine (`run_scenario_analysis`, `_build_scenario_row`) | `backend/app/services/scenario_service.py` |
| API router | `backend/app/api/scenario.py` |
| Request/response schemas | `backend/app/schemas/schemas.py` (`Scenario*`) |
| Re-run training-time feature functions | `ml/preprocessing/training_dataset.py` |
| Fire intensity normalization | `ml/features/fire_impact.py` (`_normalize_impact`) |
| Tests (incl. DB-unchanged safety) | `backend/tests/unit/test_scenario_analysis.py` |