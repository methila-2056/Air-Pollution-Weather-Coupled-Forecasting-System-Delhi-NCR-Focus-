FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# runtime dependencies only (models/ml/data arrive via docker-compose volumes)
COPY backend/requirements.txt requirements.txt
RUN pip install -r requirements.txt

# application + Alembic migration scripts (migrations run at container start)
COPY backend/app ./app
COPY alembic.ini .
COPY alembic ./alembic

# run as an unprivileged user
RUN useradd --create-home --uid 10001 aerocast \
    && chown -R aerocast:aerocast /app
USER aerocast

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
