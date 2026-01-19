import requests
import sys

BASE_URL = "http://localhost:8000"

print(f"Checking server at {BASE_URL}...")

endpoints = [
    ("/files", "GET"),
    ("/register_file", "POST"), # We'll just check if it exists (405 or 422 is fine, 404 is bad)
    ("/docs", "GET"), # FastAPI docs
    ("/admin/peers", "GET")
]

for endpoint, method in endpoints:
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=2)
        else:
            r = requests.post(url, timeout=2) # Empty post to check existence
        
        print(f"[{method}] {endpoint}: Status {r.status_code}")
        
    except Exception as e:
        print(f"[{method}] {endpoint}: Connection Failed - {e}")
