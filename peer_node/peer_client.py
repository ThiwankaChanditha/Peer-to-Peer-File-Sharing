import requests
import threading
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Optional

# Local imports
import socket
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict, Optional

# Configuration Constants
CHUNK_SIZE = 1024 * 512  # 512 KB
# Resolve STORAGE_DIR relative to this script:
# peer_node/peer_client.py -> parent(peer_node) -> parent(Network) -> storage
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_PATH = BASE_DIR / "storage"
STORAGE_DIR = "storage" # Legacy/Unused mostly but kept for consts
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

def find_available_port(start_port: int, max_port: int = 65535, host: str = "") -> int:
    """Find an available port starting from start_port"""
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # Bind to the specific host we intend to use, or "" for all
                s.bind((host, port))
                return port
            except OSError:
                continue
    # If we get here, no port found or race condition. 
    import random
    raise RuntimeError("No available ports found (checked range)")
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


from peer_server import start_peer_server
from tcp_handler import TCPServer, send_tcp_packet

class PeerClient:
    def __init__(self, tracker_url: str = f"http://localhost:{DEFAULT_TRACKER_PORT}"):
        self.tracker_url = tracker_url
        self.peer_id = f"peer_{int(time.time())}"
        self.host = get_lan_ip()
        self.port = find_available_port(9000, host=self.host)
        self.token = None
        self.running = True
        
        # Start the background server for uploading chunks
        self.server_thread = threading.Thread(
            target=start_peer_server, 
            args=(self.host, self.port),
            daemon=True
        )
        self.server_thread.start()
        print(f"Peer Node (HTTP) started at {self.host}:{self.port}")

        # Start TCP Server for raw transfers
        # Try to bind to port + 1, otherwise let it find one
        self.tcp_port = self.port + 1
        self.tcp_server = TCPServer(self.host, self.tcp_port)
        try:
            self.tcp_port = self.tcp_server.start()
            print(f"Peer Node (TCP) started at {self.host}:{self.tcp_port}")
        except Exception as e:
            print(f"Failed to start TCP server: {e}")
            self.tcp_port = 0



    def join_network(self) -> bool:
        """Register with the tracker"""
        try:
            payload = {
                "peer_id": self.peer_id,
                "host": self.host,
                "port": self.port,
                "status": "active"
            }
            res = requests.post(f"{self.tracker_url}/join", json=payload)
            if res.status_code == 200:
                data = res.json()
                self.token = data.get("token")
                return True
            else:
                print(f"Failed to join: {res.text}")
                return False
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def get_metadata(self, file_stem: str) -> Optional[dict]:
        try:
            from urllib.parse import quote
            safe_stem = quote(file_stem)
            params = {"peer_id": self.peer_id, "token": self.token}
            # Use safe_stem in URL path
            res = requests.get(f"{self.tracker_url}/metadata/{safe_stem}", params=params)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception:
            return None

    def list_files(self) -> List[dict]:
        """Fetch list of available files from tracker"""
        try:
            res = requests.get(f"{self.tracker_url}/files")
            if res.status_code == 200:
                return res.json()
            return []
        except Exception:
            return []

    def find_chunk_owners(self, file_stem: str, chunk_index: int) -> List[dict]:
        try:
            from urllib.parse import quote
            safe_stem = quote(file_stem)
            params = {"peer_id": self.peer_id, "token": self.token}
            res = requests.get(
                f"{self.tracker_url}/peers/{safe_stem}/{chunk_index}", 
                params=params
            )
            if res.status_code == 200:
                return res.json().get("owners", [])
            return []
        except Exception:
            return []

    def download_file(self, file_stem: str):
        metadata = self.get_metadata(file_stem)
        if not metadata:
            return "Metadata not found"

        local_storage = STORAGE_PATH / "received_chunks"
        local_storage.mkdir(parents=True, exist_ok=True)

        downloaded_chunks = []

        for i in range(metadata['total_chunks']):
            success = False
            
            # Check if we already have this chunk locally
            chunk_name = f"{file_stem}_chunk_{i}"
            chunk_path = local_storage / chunk_name
            if chunk_path.exists():
                with open(chunk_path, "rb") as f:
                    chunk_data = f.read()
                if hashlib.sha256(chunk_data).hexdigest() == metadata['chunks'][i]['hash']:
                    print(f"[DEBUG] Found chunk locally: {chunk_name}")
                    downloaded_chunks.append({"index": i, "filename": chunk_name})
                    # Announce it just in case we haven't yet
                    self.announce_chunk(file_stem, i)
                    success = True
                    continue # Skip to next chunk
            
            # If not found locally, try peers
            peers = self.find_chunk_owners(file_stem, i)
            
            for peer in peers:
                if peer['peer_id'] == self.peer_id: continue

                target_host = peer['host']
                target_port = peer['port']
                
                from urllib.parse import quote
                safe_stem = quote(file_stem)
                
                url = f"http://{target_host}:{target_port}/chunk/{safe_stem}/{i}"
                
                try:
                    params = {}
                    if peer.get('type') == 'tracker':
                         params = {"peer_id": self.peer_id, "token": self.token}
                    
                    r = requests.get(url, params=params, timeout=10)
                    
                    if r.status_code == 200:
                        chunk_data = r.content
                        if hashlib.sha256(chunk_data).hexdigest() == metadata['chunks'][i]['hash']:
                            # chunk_name already defined above
                            with open(local_storage / chunk_name, "wb") as f:
                                f.write(chunk_data)
                            
                            self.announce_chunk(file_stem, i)
                            downloaded_chunks.append({"index": i, "filename": chunk_name})
                            success = True
                            break
                except Exception:
                    continue
            
            if not success:
                return f"Failed to download chunk {i}"

        if self.reassemble(file_stem, metadata, downloaded_chunks):
            return "Download complete"
        return "Reassembly failed"

    def announce_chunk(self, file_stem: str, chunk_index: int):
        try:
            requests.post(
                f"{self.tracker_url}/announce_chunk",
                params={"peer_id": self.peer_id, "token": self.token},
                json={"file_stem": file_stem, "chunk_index": chunk_index}
            )
        except Exception:
            pass

    def reassemble(self, file_stem: str, metadata: dict, chunks: list):
        out_dir = STORAGE_PATH / "downloads"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = metadata.get("original_name", f"{file_stem}.out")
        out_path = out_dir / fname
        
        chunks.sort(key=lambda x: x['index'])
        
        try:
            print(f"[DEBUG] Reassembling to: {out_path}")
            with open(out_path, "wb") as outfile:
                for c in chunks:
                    chunk_path = STORAGE_PATH / "received_chunks" / c['filename']
                    print(f"[DEBUG] Reading chunk: {chunk_path}")
                    with open(chunk_path, "rb") as infile:
                        outfile.write(infile.read())
            print(f"[DEBUG] Reassembly success: {out_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Reassembly failed: {e}")
            return False

    def push_file_tcp(self, target_ip, target_port, file_stem):
        """
        Manually push an entire file (metadata + all chunks) to another peer via TCP
        """
        try:
            # 1. Send Metadata
            meta_path = STORAGE_PATH / "metadata" / f"{file_stem}.json"
            if not meta_path.exists():
                return "Metadata file not found"
            
            with open(meta_path, "r") as f:
                meta = json.load(f)
            
            print(f"[TCP] Pushing Metadata: {file_stem}")
            header = {"packet_type": "metadata", "file_stem": file_stem}
            success, msg = send_tcp_packet(target_ip, target_port, header, meta_path)
            if not success:
                return f"Failed to send metadata: {msg}"
            
            # 2. Send Chunks
            total_chunks = meta['total_chunks']
            sent_count = 0
            
            for i in range(total_chunks):
                chunk_name = f"{file_stem}_chunk_{i}"
                chunk_path = STORAGE_PATH / "chunks" / chunk_name
                # Fallback check
                if not chunk_path.exists():
                    chunk_path = STORAGE_PATH / "received_chunks" / chunk_name
                
                if not chunk_path.exists():
                    return f"Chunk {i} not found locally"

                # Send Chunk Packet
                header = {
                    "packet_type": "chunk", 
                    "file_stem": file_stem, 
                    "chunk_index": i
                }
                success, msg = send_tcp_packet(target_ip, target_port, header, chunk_path)
                if not success:
                    return f"Stopped at chunk {i}: {msg}"
                sent_count += 1
                
            return f"Success! Sent metadata + {sent_count} chunks."

        except Exception as e:
            return f"Error: {e}"

if __name__ == "__main__":
    pass
