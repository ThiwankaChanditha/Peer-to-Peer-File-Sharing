import sys
from pathlib import Path

# Add peer_node to path
sys.path.append(str(Path("e:/NETWORK/Peer-to-Peer-File-Sharing").resolve() / "peer_node"))

from peer_client import PeerClient

if __name__ == "__main__":
    import time
    client = PeerClient()
    if client.join_network():
        print("Joined network.")
        test_file = Path("test_assignment.txt")
        test_file.write_text("Hello assignment")
        
        # Give tracker a bit of time
        time.sleep(1)
        
        tracker_parts = client.tracker_url.replace("http://", "").replace("https://", "").split(":")
        tracker_ip = tracker_parts[0]
        tracker_tcp_port = int(tracker_parts[1]) + 1
        
        print(f"Submitting to {tracker_ip}:{tracker_tcp_port}")
        success, msg = client.submit_assignment_tcp(tracker_ip, tracker_tcp_port, test_file)
        print(f"Success: {success}, Msg: {msg}")
    else:
        print("Failed to join")
