.PHONY: install install-dev test test-unit test-integration run-api run-api-reload build discipline clean-data pip-audit

# Project: AeroCast-NCR (SIH26082). Central developer commands.
# Detects OS differences so the same targets work on Windows + Linux/macOS.

PY ?= python
PIP ?= $(PY) -m pip

install:            ## Install runtime dependencies from pyproject.toml
	$(PIP) install -e .

install-dev:        ## Install runtime + dev/test dependencies
	$(PIP) install -e ".[dev]"

test:               ## Run the full pytest suite (unit + integration)
	$(PY) -m pytest backend/tests -q

test-unit:          ## Fast unit-level tests only
	$(PY) -m pytest backend/tests/unit -q

test-integration:   ## End-to-end API/integration tests
	$(PY) -m pytest backend/tests -q -m "not unit"

run-api:            ## Serve the FastAPI backend on :8000
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000

run-api-reload:     ## Serve backend with auto-reload for development
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

build:              ## Type-check + production-build the frontend
	cd frontend && npm run build

discipline:         ## Quick hygiene: import-list + syntax compile check
	$(PY) -m scripts.environment_check

clean-data:         ## Remove regenerable data artifacts (keep source CSVs)
	$(PY) scripts/clean_generated.py

pip-audit:          ## Security audit of pinned dependencies
	$(PIP) install pip-audit && $(PIP) audit