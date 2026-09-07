# Deployment

Two supported paths: **Docker Compose** (self-contained) and **bare metal**
(system Python + npm).

## Docker Compose (recommended)

```bash
cp .env.example .env      # optional: set NASA_FIRMS_MAP_KEY for live fires
docker compose up --build
```

Services:
- `db` — PostgreSQL 16 (healthchecked), volume `pgdata`
- `backend` — FastAPI on `:8000`; `ml/`, `models/`, `data/` mounted read-only
- `frontend` — nginx on `:5173`(host→80) serving the SPA and proxying `/api`

Notes:
- To use Postgres, set `DATABASE_URL=postgresql://aerocast:aerocast_secret_2024@db:5432/aerocast_ncr`
  (compose already does). The local development default is SQLite; migrations
  are additive and run at startup.
- First boot seeds five DEFAULT NCR stations and demo readings. Provide a real
  FIRMS key + run `scripts/download_*.py` inside the backend container for
  live data.

## Bare metal

```bash
python -m pip install -e ".[dev]"
cp .env.example .env

# backend
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000

# frontend (separate terminal)
cd frontend && npm ci && npm run dev
```

## Environment reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///./aerocast_ncr.db` | SQLAlchemy connection string |
| `NASA_FIRMS_MAP_KEY` | *(empty)* | Optional FIRMS API key for live fire data |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed browser origins |
| `ENVIRONMENT` | `development` | App runtime environment label |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `LIVE_REFRESH_ENABLED` | derived | Whether the refresh scheduler runs |
| `LIVE_REFRESH_INTERVAL_HOURS` | `3` | Scheduler cadence |

## Health & operations

- `GET /health` — liveness (also the container HEALTHCHECK).
- `GET /api/data-quality` — per-table row counts and missing-value audit.
- Logs: `server.log` / `server_err.log` (backend), `vite_dev.log` /
  `vite_dev_err.log` (frontend dev server).

## Security notes

- Never commit real API keys; `.env` is tracked only because the sample values
  are placeholders. Rotate before production use.
- Postgres credentials in `docker-compose.yml` are development-only defaults.