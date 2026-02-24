import sys
import threading
import time
import requests
from pathlib import Path
import json

BASE_DIR = Path("e:/NETWORK/Peer-to-Peer-File-Sharing").resolve()
sys.path.append(str(BASE_DIR))
sys.path.append(str(BASE_DIR / "privileged_peer"))
sys.path.append(str(BASE_DIR / "peer_node"))

# Launch Tracker
def start_tracker():
    import uvicorn
    from privileged_peer.server import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

t = threading.Thread(target=start_tracker, daemon=True)
t.start()
time.sleep(2) # wait for startup

from peer_node.peer_client import PeerClient
client = PeerClient(tracker_url="http://127.0.0.1:8000")
if client.join_network():
    print(f"Peer joined: {client.peer_id}")
    
    # Check what tracker recorded
    peers = requests.get("http://127.0.0.1:8000/admin/peers").json()
    print("Tracker active peers:")
    print(json.dumps(peers, indent=2))
    
    test_file = BASE_DIR / "test_assign.txt"
    test_file.write_text("Hello")
    
    print("\nSubmitting assignment...")
    success, msg = client.submit_assignment_tcp("127.0.0.1", 8001, test_file)
    print(f"Result: {success} - {msg}")
else:
    print("Failed to join.")
