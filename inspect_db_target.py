from pathlib import Path
from sqlalchemy.engine import make_url
from dotenv import load_dotenv
import os

load_dotenv(Path.cwd() / ".env")
url = os.getenv("DATABASE_URL")

if not url:
    print("DATABASE_URL not found")
else:
    parsed = make_url(url)
    print("Database host:", parsed.host)
    print("Database name:", parsed.database)
    print("Database user:", parsed.username)
