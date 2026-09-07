# ml/ — Machine Learning, Physics & Coupling

Core science of AeroCast-NCR.

## features/

| Module | Responsibility |
|--------|----------------|
| `feature_engineering.py` | Temporal lags, rolling stats, wind decomposition, composite/ coupling features (124-column featured dataset) |
| `coupling.py` | Two-way weather–chemistry: aerosol AOD proxy, radiation attenuation, PBL suppression, stability-coupling index |
| `coupled_loop.py` | Online time-stepped coupled forecast loop (chemistry ↔ meteorology over each forecast hour) |
| `dispersion_solver.py` | Numerical advection–diffusion–deposition–emission core (WRF-Chem-style surrogate) on the NCR grid |
| `fire_impact.py` | Stubble-fire impact score, upwind/downwind geometry to stations |
| `inversion.py` | Inversion detection + diurnal trapping factors |

## training/

- `trainer.py` — trains persistence/RF/XGB for 6 pollutants × 6 horizons,
  writes `models/{type}_{pollutant}_{h}h.joblib` + `metrics.json`.

## Design note

The two-way interlink is deliberately layered:

1. **Statistical forecasters** learn coupled dynamics through coupling features
   (`feedback_multiplier`, `stability_coupling_index`, …).
2. **Online loop** re-forces each hour's predictions with the up-to-date
   met state.
3. **Numerical core** explicitly integrates transport and lets the resolved
   aerosol field suppress PBL / deepen stability — then feeds those back into
   deposition/mixing.