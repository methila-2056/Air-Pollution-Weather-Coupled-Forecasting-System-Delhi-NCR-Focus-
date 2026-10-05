from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv(Path.cwd() / ".env")

url = os.getenv("DATABASE_URL")
if not url:
    raise RuntimeError("DATABASE_URL is missing from the project's .env file")

engine = create_engine(url)

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT pid, state, wait_event_type, wait_event,
               now() - query_start AS query_duration,
               left(query, 180) AS query
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
          AND usename = current_user
        ORDER BY query_start NULLS LAST
    """))
    for row in rows:
        print(row)
