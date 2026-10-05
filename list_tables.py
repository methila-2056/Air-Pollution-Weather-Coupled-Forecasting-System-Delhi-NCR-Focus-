from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
    """))

    tables = list(rows)

    for schema, table in tables:
        print(f"{schema}.{table}")

    print(f"\nTOTAL TABLES: {len(tables)}")
