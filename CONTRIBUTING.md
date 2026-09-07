# Contributing to AeroCast-NCR

Thanks for helping with the Delhi NCR air-quality forecasting system. This
guide keeps contributions consistent and easy to review.

## Getting started

1. Clone the repository and install dependencies:
   ```bash
   python -m pip install -e ".[dev]"
   cd frontend && npm ci
   ```
2. Copy `.env.example` to `.env` and at least leave the defaults (SQLite local DB).
3. Run the suite before and after your change:
   ```bash
   python -m pytest backend/tests -q      # backend: 129+ tests
   cd frontend && npm run build          # frontend: type-check + build
   ```

## Project layout

```
backend/app         FastAPI application (api/, services/, models/, schemas/)
backend/tests       pytest suite (unit/ + integration/)
ml/features         ML + physics: coupling, dispersion solver, fire, inversion
ml/training         model trainer and feature pipeline
data/               source CSVs and processed datasets (parts split for git)
frontend/src        React + TypeScript dashboard
scripts/            developer + data-pipeline utilities
```

## Workflow

- Create a branch off `main` for each change.
- Keep changes small and focused; one logical idea per commit.
- Write a regression/unit test for new behaviour (see `backend/tests/unit/`).
- Run `python -m pytest backend/tests/unit -q` for a fast loop.

## Commit conventions

- Present-tense imperative summaries ("Add", "Fix", "Refactor").
- Reference the problem statement where relevant, e.g. `(SIH26082)`.
- Do not commit secrets; keep live API keys out of tracked files.

## Testing

- Unit tests must not hit the network or require a real DB (temp SQLite only).
- Integration tests in `backend/tests/integration/` exercise the HTTP layer
  through FastAPI's `TestClient` with the seeded dataset.

## Reporting issues

Include:
- the Python/OS versions and output of `pip freeze`
- the endpoint or code path affected
- logs from `server.log`/`frontend/vite_dev.log` if applicable