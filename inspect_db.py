from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as conn:
    print("=== DATABASE ===")
    print(conn.execute(text("SELECT current_database(), current_schema(), current_user")).fetchone())

    print("\n=== ALEMBIC ===")
    print(conn.execute(text("SELECT version_num FROM alembic_version")).fetchall())

    print("\n=== pollution_observations tables ===")
    rows = conn.execute(text("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_name = 'pollution_observations'
    """))
    for row in rows:
        print(row)

    print("\n=== nh3 / pb columns ===")
    rows = conn.execute(text("""
        SELECT table_schema, column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'pollution_observations'
          AND column_name IN ('nh3', 'pb')
        ORDER BY column_name
    """))
    for row in rows:
        print(row)

    print("\n=== migration exists ===")
    rows = conn.execute(text("""
        SELECT version_num
        FROM alembic_version
    """))
    for row in rows:
        print(row)
