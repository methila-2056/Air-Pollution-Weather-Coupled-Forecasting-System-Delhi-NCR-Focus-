import os


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
EXTERNAL_DIR = os.path.join(DATA_DIR, "external")

for _dir in (RAW_DIR, PROCESSED_DIR, EXTERNAL_DIR):
    os.makedirs(_dir, exist_ok=True)
