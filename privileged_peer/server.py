from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pathlib import Path
import json, time, asyncio, secrets
from typing import Dict, List, Set, Optional
from pydantic import BaseModel

import os
import socket, logging, sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from security.auth import issue_token, validate_token, revoke_token
from security.hashing import sha256
from security.crypto import load_or_generate_keys
from tcp_handler import TCPServer
from shared.config import (
    DEFAULT_TRACKER_PORT, STORAGE_DIR, get_lan_ip,
    sanitize_stem, PeerInfo, FileMetadata, ChunkLocation, ChunkData
)

# Configuration Constants
CHUNK_SIZE = 1024 * 512  # 512 KB
# Resolve STORAGE_DIR relative to this script:
# privileged_peer/server.py -> parent(privileged_peer) -> parent(Network) -> storage
STORAGE_PATH = BASE_DIR / "storage"
STORAGE_DIR = "storage" # Legacy/Unused mostly but kept for consts
DEFAULT_TRACKER_PORT = 8000

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_lan_ip():
    """Detect the local machine's physical LAN IP address"""
    try:
        host_name = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(host_name)[2]
        
        valid_ips = []
        for ip in ip_addresses:
            if ip.startswith("127."): continue
            if ip.startswith("169.254."): continue
            if ip.startswith("172."): continue  # Docker/WSL/Hyper-V
            if ip.startswith("192.168.56."): continue # VirtualBox Host-Only
            valid_ips.append(ip)
            
        if valid_ips:
            # Prefer typical home router subnets
            for ip in valid_ips:
                if ip.startswith("192.168.") or ip.startswith("10."):
                    return ip
            return valid_ips[0]
            
        # Offline fallback: dummy local connection to force OS to choose an interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('192.168.1.1', 1)) 
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def find_available_port(start_port: int, max_port: int = 65535):
    """Find an available port starting from start_port"""
    port = start_port
    while port <= max_port:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                return port
        except OSError:
            port += 1
    raise RuntimeError(f"No available ports found between {start_port} and {max_port}")

from shared.config import load_admin_key
admin_key_path = BASE_DIR / "admin_key.txt"
ADMIN_API_KEY = load_admin_key()
if not ADMIN_API_KEY:
    ADMIN_API_KEY = secrets.token_urlsafe(24)
    admin_key_path.write_text(ADMIN_API_KEY)
    print(f"[SECURITY] Auto-generated and saved Admin API Key to {admin_key_path}")
else:
    print(f"[SECURITY] Loaded Admin API Key: {ADMIN_API_KEY[:5]}***")

_admin_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

async def require_admin(key: str = Depends(_admin_header)):
    if key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

app = FastAPI(title="Privileged Peer Tracker")

# Store approved peers: peer_id -> PeerInfo
approved_peers: Dict[str, PeerInfo] = {}

# track chunk locations: file_hash -> chunk_index -> Set[peer_id]
chunk_locations: Dict[str, Dict[int, Set[str]]] = {}

# file metadata cache: file_stem -> FileMetadata
file_registry: Dict[str, FileMetadata] = {}

def generate_token():
    return secrets.token_urlsafe(32)

@app.on_event("startup")
async def startup_event():
    # Load existing metadata into registry
    metadata_dir = STORAGE_PATH / "metadata"
    if metadata_dir.exists():
        for meta_file in metadata_dir.glob("*.json"):
            try:
                with open(meta_file, "r") as f:
                    data = json.load(f)
                    # Support legacy format by checking keys
                    if "file_stem" in data:
                        stem = data["file_stem"]
                        # Assume hash is stem for now if not present (legacy compat)
                        file_hash = data.get("file_hash", stem) 
                        file_registry[stem] = FileMetadata(
                            file_name=data.get("original_name", stem),
                            file_hash=file_hash,
                            total_chunks=data.get("total_chunks", 0),
                            file_size=0, # Legacy might not have this
                            mime_type=data.get("mime_type", "application/octet-stream")
                        )
            except Exception as e:
                print(f"Failed to load metadata {meta_file}: {e}")

@app.post("/join")
async def join(peer: PeerInfo):
    peer.last_seen = time.time()
    if peer.peer_id in approved_peers:
        approved_peers[peer.peer_id] = peer
        # Re-issue token so the peer gets a fresh one
        token = issue_token(peer.peer_id)
        return {"status": "rejoined", "token": token}

    token = issue_token(peer.peer_id)
    approved_peers[peer.peer_id] = peer
    return {
        "status": "approved",
        "token": token,
        "peer_id": peer.peer_id,
        "tracker_ip": get_lan_ip()
    }

class Announcement(BaseModel):
    file_stem: str
    chunk_index: int

@app.post("/announce_chunk")
async def announce_chunk_endpoint(announcement: Announcement,
                                   peer_id: str, token: str):
    if not validate_token(peer_id, token):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    # Update last_seen
    if peer_id in approved_peers:
        approved_peers[peer_id].last_seen = time.time()

    file_id = sanitize_stem(announcement.file_stem)   # ← sanitize here
    if file_id not in chunk_locations:
        chunk_locations[file_id] = {}
    chunk_locations[file_id].setdefault(announcement.chunk_index, set()).add(peer_id)
    return {"status": "acknowledged"}

@app.get("/peers/{file_stem:path}/{chunk_index}")
async def get_chunk_owners(file_stem: str, chunk_index: int,
                            peer_id: str, token: str):
    if not validate_token(peer_id, token):
        raise HTTPException(status_code=403, detail="Unauthorized")

    file_stem = sanitize_stem(file_stem)   # ← sanitize here
    owners, result = set(), []

    tracker_path = STORAGE_PATH / "chunks" / f"{file_stem}_chunk_{chunk_index}"
    if tracker_path.exists():
        owners.add("privileged_peer")

    if file_stem in chunk_locations and chunk_index in chunk_locations[file_stem]:
        owners.update(chunk_locations[file_stem][chunk_index])

    if "privileged_peer" in owners:
        result.append({"peer_id": "privileged_peer", "host": get_lan_ip(),
                        "port": DEFAULT_TRACKER_PORT, "type": "tracker"})
        owners.discard("privileged_peer")

    for oid in owners:
        if oid in approved_peers:
            result.append(approved_peers[oid].model_dump())

    return {"owners": result}

@app.get("/metadata/{file_stem:path}")
async def get_metadata(file_stem: str, peer_id: str, token: str):
    if not validate_token(peer_id, token):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    print(f"[DEBUG] Request for metadata: {file_stem}")
    meta_path = STORAGE_PATH / "metadata" / f"{file_stem}.json"
    print(f"[DEBUG] Checking: {meta_path}")
    
    # Try direct match
    if not meta_path.exists():
        # Try urllib decoded
        from urllib.parse import unquote
        decoded_stem = unquote(file_stem)
        meta_path = STORAGE_PATH / "metadata" / f"{decoded_stem}.json"
        print(f"[DEBUG] Checking decoded: {meta_path}")
        
        if not meta_path.exists():
            # Try to match stem in dir directly
            found = False
            metadata_dir = STORAGE_PATH / "metadata"
            if metadata_dir.exists():
                for f in metadata_dir.glob("*.json"):
                    if f.stem == file_stem or f.stem == decoded_stem:
                        meta_path = f
                        found = True
                        print(f"[DEBUG] Found via glob: {meta_path}")
                        break
            if not found:
                print(f"[ERROR] Metadata not found for {file_stem} in {metadata_dir}")
                raise HTTPException(status_code=404, detail=f"Metadata not found for {file_stem}")
        
    with open(meta_path, "r", encoding='utf-8') as f: # Added 'encoding' just in case
        return json.load(f)

@app.get("/chunk/{file_stem:path}/{chunk_index}")
async def download_chunk(file_stem: str, chunk_index: int, peer_id: str, token: str):
    if not validate_token(peer_id, token):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    chunk_name = f"{file_stem}_chunk_{chunk_index}"
    chunk_name = f"{file_stem}_chunk_{chunk_index}"
    chunk_path = STORAGE_PATH / "chunks" / chunk_name
    
    if not chunk_path.exists():
         # Try decoded
         from urllib.parse import unquote
         decoded_stem = unquote(file_stem)
         chunk_name = f"{decoded_stem}_chunk_{chunk_index}"
         chunk_path = STORAGE_PATH / "chunks" / chunk_name
         
         if not chunk_path.exists():
             print(f"[ERROR] Chunk not found: {chunk_path}")
             raise HTTPException(status_code=404, detail="Chunk not found")
         
    return FileResponse(chunk_path)

@app.get("/tracker_pubkey")
async def tracker_pubkey():
    """Allows peers to fetch and cache the tracker's public key (TOFU model)."""
    key_path = BASE_DIR / "storage" / "tracker_public_key.pem"
    if not key_path.exists():
        raise HTTPException(status_code=404, detail="Key not generated yet")
    return {"public_key": key_path.read_text()}

@app.get("/files")
async def list_files():
    """List all files available on the network"""
    return [
        {
            "stem": stem,
            "name": meta.file_name,
            "size": meta.file_size, # Might be 0 if legacy
            "total_chunks": meta.total_chunks,
            "mime_type": meta.mime_type
        }
        for stem, meta in file_registry.items()
    ]

class FileRegistration(BaseModel):
    file_stem: str
    original_name: str
    total_chunks: int
    mime_type: str = "application/octet-stream"

@app.post("/register_file")
async def register_file(file_info: FileRegistration):
    """Manually register a file (called by Admin Dashboard)"""
    file_registry[file_info.file_stem] = FileMetadata(
        file_name=file_info.original_name,
        file_hash=file_info.file_stem, # fallback
        total_chunks=file_info.total_chunks,
        file_size=0,
        mime_type=file_info.mime_type
    )
    return {"status": "registered", "file_stem": file_info.file_stem}

@app.delete("/flush_registry")
async def flush_registry():
    """Admin: Clear all files from registry"""
    count = len(file_registry)
    file_registry.clear()
    
    # Delete all metadata files
    try:
        meta_dir = STORAGE_PATH / "metadata"
        if meta_dir.exists():
            for f in meta_dir.glob("*.json"):
                f.unlink()
    except Exception as e:
        print(f"Error flushing metadata: {e}")
        
    print(f"[ADMIN] Flushed registry. Removed {count} items.")
    return {"status": "flushed", "removed_count": count}

class FileUnregistration(BaseModel):
    file_stem: str

@app.post("/unregister_file")
async def unregister_file(info: FileUnregistration):
    """Admin: Remove file from registry"""
    if info.file_stem in file_registry:
        del file_registry[info.file_stem]
        
        # Also delete the metadata file from disk so it doesn't reappear on restart
        meta_path = STORAGE_PATH / "metadata" / f"{info.file_stem}.json"
        try:
            if meta_path.exists():
                meta_path.unlink()
        except Exception as e:
            print(f"Error deleting metadata {meta_path}: {e}")
            
        return {"status": "unregistered"}
    return {"status": "not_found", "message": "File not in registry"}

@app.get("/admin/peers")
async def get_all_peers(_: None = Depends(require_admin)):
    return [p.model_dump() for p in approved_peers.values()]

@app.get("/peers")
async def list_peers(peer_id: str, token: str):
    """Public (token-authenticated) peer list for peer nodes."""
    if not validate_token(peer_id, token):
        raise HTTPException(status_code=403, detail="Unauthorized")
    return [
        {"peer_id": p.peer_id, "host": p.host, "port": p.port}
        for p in approved_peers.values()
    ]

def broadcast_presence():
    import time
    from security.crypto import sign_data, load_or_generate_keys, serialize_public_key
    
    key_path = BASE_DIR / "storage" / "tracker_keys"
    private_key, pub_key_obj = load_or_generate_keys(key_path)
    pub_key_str = serialize_public_key(pub_key_obj)
    
    # Write public key to a well-known file so peers can be pre-seeded with it
    (BASE_DIR / "storage").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "storage" / "tracker_public_key.pem").write_text(pub_key_str)
    
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while True:
        try:
            payload = json.dumps({
                "action": "tracker_presence",
                "ip": get_lan_ip(),
                "port": DEFAULT_TRACKER_PORT
            })
            signature = sign_data(private_key, payload.encode())
            message = json.dumps({
                "payload": payload,
                "signature": signature
            }).encode()
            udp_socket.sendto(message, ("<broadcast>", 9999))
            time.sleep(5)
        except Exception as e:
            logging.error(f"[UDP] Broadcast error: {e}")
            time.sleep(5)

@app.on_event("startup")
async def start_tcp_server():
    try:
        def get_peer_pk(peer_id):
            p = approved_peers.get(peer_id)
            print(f"[DEBUG] TCP get_peer_pk: peer_id={peer_id}, found={p is not None}, total_peers={len(approved_peers)}")
            if p:
                print(f"[DEBUG] TCP get_peer_pk: public_key={p.public_key[:20] if p.public_key else None}")
            return p.public_key if p else None

        tcp_port = DEFAULT_TRACKER_PORT + 1
        tcp_server = TCPServer(
            host="0.0.0.0", 
            start_port=tcp_port,
            get_public_key_cb=get_peer_pk
        )
        actual_port = tcp_server.start()
        print(f"[TCP] Server started on port {actual_port}")
    except Exception as e:
        print(f"[TCP] Failed to start TCP server: {e}")

@app.on_event("startup")
async def start_broadcaster():
    import threading
    t = threading.Thread(target=broadcast_presence, daemon=True)
    t.start()

@app.on_event("startup")
async def start_peer_cleanup():
    async def _cleanup():
        while True:
            await asyncio.sleep(60)
            cutoff = time.time() - 300   # 5 minutes — gives peers time to start up and send heartbeats
            stale = [pid for pid, p in approved_peers.items()
                     if p.last_seen > 0 and p.last_seen < cutoff]
            for pid in stale:
                logging.info(f"[CLEANUP] Removing stale peer: {pid}")
                del approved_peers[pid]
                revoke_token(pid)
    asyncio.create_task(_cleanup())

@app.post("/heartbeat")
async def heartbeat(peer_id: str, token: str):
    if not validate_token(peer_id, token):
        raise HTTPException(status_code=403, detail="Unauthorized")
    if peer_id in approved_peers:
        approved_peers[peer_id].last_seen = time.time()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_TRACKER_PORT)
