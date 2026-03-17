import socket
import json
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

def announce_peer(peer_id, private_key=None):
    from security.crypto import sign_data
    from shared.config import get_lan_ip
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    payload = json.dumps({
        "action": "peer_presence",
        "peer_id": peer_id,
        "ip": get_lan_ip(),
        "port": 8000
    })
    
    signature = sign_data(private_key, payload.encode()) if private_key else ""

    message = json.dumps({
        "payload": payload,
        "signature": signature
    }).encode()
    
    sock.sendto(message, ("<broadcast>", 9999))
