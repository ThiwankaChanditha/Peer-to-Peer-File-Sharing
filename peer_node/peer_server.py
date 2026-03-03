from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import uvicorn
from pathlib import Path

# Local import
from shared.config import (
    CHUNK_SIZE, DEFAULT_TRACKER_PORT, get_lan_ip,
    find_available_port, sanitize_stem,
    PeerInfo, ChunkLocation, FileMetadata, ChunkData
)


BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_PATH = BASE_DIR / "storage"

app = FastAPI(title="Peer Node Server")

@app.get("/chunk/{file_stem}/{chunk_index}")
async def upload_chunk(file_stem: str, chunk_index: int):
    # Verify we actually have this chunk
    chunk_name = f"{file_stem}_chunk_{chunk_index}"
    # Default storage for received chunks
    chunk_path = STORAGE_PATH / "received_chunks" / chunk_name
    
    if not chunk_path.exists():
        chunk_path = STORAGE_PATH / "chunks" / chunk_name

    if not chunk_path.exists():
        raise HTTPException(status_code=404, detail="Chunk not found")
        
    return FileResponse(chunk_path)

@app.get("/")
def health_check():
    return {"status": "online", "role": "peer_node"}

def start_peer_server(host, port):
    uvicorn.run(app, host=host, port=port, log_level="error")
