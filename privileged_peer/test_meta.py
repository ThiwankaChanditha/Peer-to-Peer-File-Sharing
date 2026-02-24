import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_PATH = BASE_DIR / "storage"

print(f"STORAGE_PATH is {STORAGE_PATH}")

try:
    pres = requests.get("http://localhost:8000/files")
    if pres.status_code == 200:
        files = pres.json()
        print(f"Files from tracker: {len(files)}")
        for f in files:
            meta_path = STORAGE_PATH / "metadata" / f"{f['stem']}.json"
            print(f"Checking {meta_path}...")
            print(f"Exists: {meta_path.exists()}")
except Exception as e:
    print(f"Error: {e}")
