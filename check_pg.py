from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT
            pid,
            state,
            wait_event_type,
            wait_event,
            now() - query_start AS duration,
            LEFT(query, 300) AS query
        FROM pg_stat_activity
        WHERE datname = current_database()
        ORDER BY pid
    """))

    for row in rows:
        print(row)
