# shared/config.py
import socket
import re
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional

CHUNK_SIZE = 1024 * 512          
STORAGE_DIR = "storage"
DEFAULT_TRACKER_PORT = 8000
MAX_CLUSTER_SIZE = 20
PEER_SAMPLE_SIZE = 5
MAX_ASSIGNMENT_SIZE = 50 * 1024 * 1024  
BOOTSTRAP_PEERS: List[str] = []          

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_lan_ip() -> str:
    try:
        host_name = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(host_name)[2]
        valid = [
            ip for ip in ip_addresses
            if not ip.startswith(("127.", "169.254.", "172.", "192.168.56."))
        ]
        for ip in valid:
            if ip.startswith(("192.168.", "10.")):
                return ip
        if valid:
            return valid[0]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("192.168.1.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def find_available_port(start_port: int, max_port: int = 65535,
                         host: str = "") -> int:
    for port in range(start_port, max_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            continue
    raise RuntimeError("No available ports found")


def sanitize_stem(stem: str) -> str:
    """
    Strip path components and allow only safe characters.
    Call this on EVERY file_stem received from the network
    before touching the filesystem.
    """
    name = Path(stem).name          
    return re.sub(r"[^\w\-.]", "_", name)

def normalize_stem(filename: str, max_len: int = 60) -> str:
    """
    Produce a short, URL-safe stem from an original filename.
    Keeps it deterministic so the same file always gets the same stem.
    """
    import re, hashlib
    from pathlib import Path
    stem = Path(filename).stem
    # Replace spaces and unsafe chars with underscores
    safe = re.sub(r"[^\w\-]", "_", stem)
    # If too long, truncate and append a short hash for uniqueness
    if len(safe) > max_len:
        suffix = hashlib.sha256(stem.encode()).hexdigest()[:8]
        safe = safe[:max_len] + "_" + suffix
    return safe

class PeerInfo(BaseModel):
    peer_id: str
    host: str
    port: int
    status: str = "active"
    public_key: Optional[str] = None
    last_seen: float = 0.0          


class ChunkLocation(BaseModel):
    chunk_index: int
    peer_ids: List[str]


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

import os

def load_admin_key() -> str:
    """
    Load admin key from environment first, then fall back to
    admin_key.txt at the project root.
    """
    import os
    
    # 1. Environment variable takes priority
    key = os.environ.get("ADMIN_API_KEY", "")
    if key:
        return key
    
    # 2. Fall back to admin_key.txt at project root
    config_path = Path(__file__).resolve().parent.parent / "admin_key.txt"
    if config_path.exists():
        key = config_path.read_text().strip()
        if key:
            return key
    
    logging.warning("No ADMIN_API_KEY found in environment or admin_key.txt")
    return ""
