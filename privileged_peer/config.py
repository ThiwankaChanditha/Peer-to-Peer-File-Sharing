import socket
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict, Optional

# Configuration Constants
CHUNK_SIZE = 1024 * 512  # 512 KB
STORAGE_DIR = "storage"
DEFAULT_TRACKER_PORT = 8000

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_lan_ip():
    """Detect the local machine's LAN IP address"""
    try:
        # Connect to a public DNS server (does not actually send data)
        # to determine the most appropriate local interface IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def find_available_port(start_port: int, max_port: int = 65535) -> int:
    """Find an available port starting from start_port"""
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available ports found")

# --- Shared Data Models ---

class PeerInfo(BaseModel):
    peer_id: str
    host: str
    port: int
    status: str = "active"

class ChunkLocation(BaseModel):
    chunk_index: int
    peer_ids: List[str]  # List of peer IDs that have this chunk

class FileMetadata(BaseModel):
    file_name: str
    file_hash: str
    total_chunks: int
    file_size: int
    mime_type: str = "application/octet-stream"

class ChunkData(BaseModel):
    index: int
    hash: str
    filename: str
    size: int
