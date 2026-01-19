from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import json
import secrets
from typing import Dict, List, Set
from pydantic import BaseModel

import socket
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict, Optional

# Configuration Constants
CHUNK_SIZE = 1024 * 512  # 512 KB
# Resolve STORAGE_DIR relative to this script:
# privileged_peer/server.py -> parent(privileged_peer) -> parent(Network) -> storage
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


app = FastAPI(title="Privileged Peer Tracker")

# Store approved peers: peer_id -> PeerInfo
approved_peers: Dict[str, PeerInfo] = {}
peer_tokens: Dict[str, str] = {}

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
    """Register a peer with the tracker"""
    if peer.peer_id in approved_peers:
        # Update existing info
        approved_peers[peer.peer_id] = peer
        return {"status": "rejoined", "token": peer_tokens[peer.peer_id]}
    
    token = generate_token()
    approved_peers[peer.peer_id] = peer
    peer_tokens[peer.peer_id] = token
    
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
async def announce_chunk_endpoint(announcement: Announcement, peer_id: str, token: str):
    if peer_id not in approved_peers or peer_tokens.get(peer_id) != token:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    file_id = announcement.file_stem
    if file_id not in chunk_locations:
        chunk_locations[file_id] = {}
    
    if announcement.chunk_index not in chunk_locations[file_id]:
        chunk_locations[file_id][announcement.chunk_index] = set()
    
    chunk_locations[file_id][announcement.chunk_index].add(peer_id)
    return {"status": "acknowledged"}

@app.get("/peers/{file_stem}/{chunk_index}")
async def get_chunk_owners(file_stem: str, chunk_index: int, peer_id: str, token: str):
    """Get list of peers that own a specific chunk"""
    if peer_id not in approved_peers:
        if peer_tokens.get(peer_id) != token:
             raise HTTPException(status_code=403, detail="Unauthorized")

    owners = set()
    
    # 1. Check if Tracker (Privileged Peer) has it
    tracker_path = STORAGE_PATH / "chunks" / f"{file_stem}_chunk_{chunk_index}"
    if tracker_path.exists():
        owners.add("privileged_peer")
        
    # 2. Check other peers
    if file_stem in chunk_locations and chunk_index in chunk_locations[file_stem]:
        owners.update(chunk_locations[file_stem][chunk_index])
    
    # Convert to PeerInfo list
    result = []
    if "privileged_peer" in owners:
        result.append({
            "peer_id": "privileged_peer",
            "host": get_lan_ip(),
            "port": DEFAULT_TRACKER_PORT,
            "type": "tracker"
        })
        owners.discard("privileged_peer")
        
    for owner_id in owners:
        if owner_id in approved_peers:
            p = approved_peers[owner_id]
            result.append(p.dict())
            
    return {"owners": result}

@app.get("/metadata/{file_stem}")
async def get_metadata(file_stem: str, peer_id: str, token: str):
    if peer_id not in approved_peers or peer_tokens.get(peer_id) != token:
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

@app.get("/chunk/{file_stem}/{chunk_index}")
async def download_chunk(file_stem: str, chunk_index: int, peer_id: str, token: str):
    if peer_id not in approved_peers or peer_tokens.get(peer_id) != token:
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

@app.get("/admin/peers")
async def get_all_peers():
    """Endpoint for Dashboard to list peers"""
    return [p.dict() for p in approved_peers.values()]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_TRACKER_PORT)
