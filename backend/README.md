# AeroCast-NCR Backend

FastAPI service for the Delhi NCR 72-hour air-quality & plume forecasting
system. Serves the REST API, runs the prediction/coupling workflows, and
persists readings, forecasts, fires, alerts and model metrics.

## Layout

```
app/
  api/        route modules (forecast, weather, coupling, dispersion, grid, …)
  services/   business logic (forecast_service, dispersion_service, grid_service, …)
  models/     SQLAlchemy ORM models (db_models.py)
  schemas/    Pydantic request/response schemas
  utils/      shared helpers
  config.py   pydantic-settings environment config
  database.py engine/session + seed + additive migrations
  main.py     FastAPI app (lifespan, routers, health, data-quality)
```

## Run

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
# from repo root
python -m pytest backend/tests -q
```

Tests use a throwaway temp SQLite DB (`backend/conftest.py`) — no network,
no real data. Unit tests live in `backend/tests/unit/`, HTTP-level integration
tests in `backend/tests/integration/`.

## Config

All settings come from environment variables (see `.env.example` / `app/config.py`).
Defaults are safe for local development: SQLite, localhost CORS, INFO logging.

## Access

- Swagger UI: `http://localhost:8000/docs`
- Health: `GET /health`
- Data audit: `GET /api/data-quality`