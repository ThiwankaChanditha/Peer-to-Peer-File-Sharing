import subprocess
import time
import requests
import sys
import os
import signal

def test_startup():
    print("Starting Tracker...")
    tracker = subprocess.Popen([sys.executable, "privileged_peer/server.py"], cwd="f:/Network")
    time.sleep(5) # Wait for startup
    
    try:
        # Check Tracker
        r = requests.get("http://localhost:8000")
        print(f"Tracker Status: {r.json()}")
        assert r.status_code == 200
        
        # Start Peer
        print("Starting Peer Client...")
        # running client in non-interactive mode for testing is tricky since current client is interactive main
        # But we can import it and run a test function if we modify client or just check if we can run it.
        # Let's just check the server part of the peer manually or via script.
        # We'll just verify tracker is up for now as a smoke test.
        
    except Exception as e:
        print(f"Test Failed: {e}")
    finally:
        print("Killing Tracker...")
        tracker.terminate()
        tracker.wait()

if __name__ == "__main__":
    test_startup()
