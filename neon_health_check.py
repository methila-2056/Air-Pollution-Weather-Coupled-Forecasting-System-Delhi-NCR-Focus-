import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path.cwd() / ".env")

url = os.getenv("DATABASE_URL")
if not url:
    raise RuntimeError("DATABASE_URL is missing from the project's .env file")

engine = create_engine(url, pool_pre_ping=True)


def probe(conn, label, sql, params=None):
    """Run one check; a failure must not abort the rest of the report."""
    try:
        return conn.execute(text(sql), params or {}).all()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        first = str(exc).splitlines()[0]
        print(f"{label:<13}: n/a ({first[:90]})")
        return None


with engine.connect() as conn:
    conn.execute(text("select 1"))
    print("connect      : OK (round-trip)")

    ver = conn.execute(text("select version()")).scalar()
    print(f"server       : {ver.split(',')[0]}")

    endpoint = probe(
        conn, "neon endpoint", "select current_setting('neon.compute_endpoint_id', true)"
    )
    if endpoint:
        print(f"neon endpoint : {endpoint[0][0] or 'n/a (not exposed to this role)'}")

    size = probe(conn, "db size", "select pg_size_pretty(pg_database_size(current_database()))")
    if size:
        print(f"db size       : {size[0][0]}")

    schemas = probe(
        conn,
        "schema",
        "select table_schema, count(*) from information_schema.tables "
        "where table_schema not in ('pg_catalog','information_schema') "
        "group by table_schema order by table_schema",
    )
    if schemas:
        for s, n in schemas:
            print(f"schema        : {s} ({n} tables)")

    head = probe(conn, "alembic head", "select version_num from alembic_version")
    if head:
        print(f"alembic head  : {head[0][0]}")

    tables = probe(
        conn,
        "tables",
        "select tablename from pg_tables where schemaname = 'public' order by tablename",
    )
    names = [r[0] for r in tables] if tables else []
    if names:
        print(f"tables        : {', '.join(names)}")
        for table in names:
            if table == "alembic_version":
                continue
            rows = probe(conn, f"rows:{table}", f'select count(*) from "{table}"')
            if rows:
                print(f"rows          : {table} = {rows[0][0]:,}")

    for table in names:
        cols = probe(
            conn,
            f"tscol:{table}",
            "select column_name from information_schema.columns "
            "where table_schema = 'public' and table_name = :t "
            "and (column_name = 'timestamp' or column_name like '%_at')",
            {"t": table},
        )
        if not cols:
            continue
        col = cols[0][0]
        latest = probe(conn, f"latest:{table}", f'select max("{col}") from "{table}"')
        if latest:
            print(f"latest        : {table}.{col} = {latest[0][0]}")

    others = probe(
        conn,
        "other conns",
        "select count(*) from pg_stat_activity "
        "where datname = current_database() and pid <> pg_backend_pid()",
    )
    if others:
        print(f"other conns   : {others[0][0]}")
