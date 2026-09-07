# API Reference

Base URL (dev): `http://localhost:8000/api`
Base URL (docker): `http://localhost:8000/api` (nginx proxies `/api` → backend)

All endpoints return JSON. Errors use FastAPI's standard `{"detail": ...}` shape.

Authoritative definitions live in `backend/app/api/*.py` and
`backend/app/schemas/schemas.py`.

## System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe: status, service, version |
| GET | `/api/data-quality` | Row counts + missing-value audit per table |

## Stations
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stations` | List NCR monitoring stations (lat/lon/city) |

## Current conditions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/current/{station_name}` | Latest pollutant readings + AQI sub-indices |

## Weather & atmosphere
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/weather/{station_name}` | Latest weather (wind, PBL, precip, temp…) |
| GET | `/api/weather/{station_name}/history?hours=24` | Historical weather series |
| GET | `/api/inversion/{station_name}` | Inversion detection + trapping risk |

## Forecasting
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/forecast/generate` | `{station_name}` → 6-horizon pollutant forecasts |
| GET | `/api/forecast/{station_name}?hours=72` | Persisted forecasts for a station |
| GET | `/api/forecast/ncr` | Per-station forecasts across NCR |
| GET | `/api/forecast/comparison/{station_name}?hours=72` | Predicted vs actual series |
| POST | `/api/forecast/coupled` | `{station_name, horizons?}` → two-way coupled loop |

## Spatial & dispersion
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/grid/forecast?horizon_hours=24` | Statistical IDW AQI surface (cells) |
| GET | `/api/grid/overview` | Grid coverage summary |
| GET | `/api/dispersion/forecast?horizon_hours=72&start_hour=8` | Numerical advection–diffusion run; hourly frames + coupling diagnostics |

## Fire & plume
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/fire-activity` | Latest FIRMS fire aggregate |
| GET | `/api/fire/transport?station_name=…` | Transport direction to a station |
| GET | `/api/plume-risk` | Composite plume-risk score |
| GET | `/api/fire/{station_name}` | Fire context for a station |

## Explainability, coupling, alerts, metrics
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/explanation/{station_name}` | Top features + natural-language explanation |
| GET | `/api/coupling/{station_name}` | Two-way coupling diagnostics + narrative |
| GET | `/api/alerts` | Generated alert feed |
| GET | `/api/model/metrics` | Persisted MAE/RMSE/R² per model |
| POST | `/api/model/metrics` | Save a model metric row |

## Notes
- Horizon values: `[1, 6, 12, 24, 48, 72]` hours.
- AQI categories: `Good`, `Satisfactory`, `Moderate`, `Poor`, `Very Poor`, `Severe`.
- Interactive docs: `http://localhost:8000/docs` (Swagger UI).