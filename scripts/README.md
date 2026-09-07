# scripts/ — Developer & Data-Pipeline Utilities

| Script | Purpose |
|--------|---------|
| `download_weather.py` | Open-Meteo weather for the 5 NCR stations |
| `download_pollution.py` | CPCB pollution readings |
| `download_fire.py` | NASA FIRMS hotspots |
| `download_atmosphere.py` | ERA5/atmospheric ancillary data |
| `generate_fire_data.py` | Deterministic demo fire readings (no API key) |
| `build_dataset.py` | Assemble + engineer `data/processed/featured_dataset.csv` |
| `run_dev.py` | One-command local stack: seed DB → backend → (optional) frontend |
| `environment_check.py` | Dependency/DB/model sanity check |
| `evaluate_models.py` | Recompute held-out metrics from `models/` |

Run any script from the repository root:

```bash
python -m scripts.build_dataset
python -m scripts.environment_check
```