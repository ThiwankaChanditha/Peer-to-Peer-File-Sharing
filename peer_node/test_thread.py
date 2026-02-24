import threading
import time

def start_server():
    from fastapi import FastAPI
    import uvicorn
    app = FastAPI()
    @app.get("/")
    def read_root(): return {"Hello": "World"}
    try:
        uvicorn.run(app, host="127.0.0.1", port=9000, log_level="error")
    except Exception as e:
        print(f"Error: {e}")

threading.Thread(target=start_server, daemon=True).start()
time.sleep(2)
try:
    import urllib.request
    print(urllib.request.urlopen("http://127.0.0.1:9000/").read())
except Exception as e:
    print(f"Failed to fetch: {e}")
print("Done")
