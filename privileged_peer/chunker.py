from pathlib import Path
import hashlib
import mimetypes

# Local import
from config import STORAGE_DIR, CHUNK_SIZE

# Ensure we point to the project root storage if running from subdirectory
# Resolve STORAGE_PATH relative to this script:
# privileged_peer/chunker.py -> parent(privileged_peer) -> parent(Network) -> storage
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_PATH = BASE_DIR / "storage"

def sha256(data: bytes) -> str:
    """Compute SHA256 hash of data and return as hex string"""
    return hashlib.sha256(data).hexdigest()

def detect_mime_type(file_path: Path) -> str:
    mimetypes.init()
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type:
        return mime_type
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)
        if header.startswith(b'%PDF'): return 'application/pdf'
        elif header.startswith(b'\x89PNG'): return 'image/png'
        elif header.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
        elif header.startswith(b'GIF8'): return 'image/gif'
        elif header.startswith(b'PK\x03\x04'): return 'application/zip'
        elif header.startswith(b'Rar!'): return 'application/x-rar-compressed'
    except:
        pass
    return 'application/octet-stream'

def chunk_file(file_path: str, out_dir: str = None):
    chunks = []
    file_path = Path(file_path)
    if out_dir:
        out_dir_path = Path(out_dir)
    else:
        out_dir_path = STORAGE_PATH / "chunks"

    out_dir_path.mkdir(parents=True, exist_ok=True)
    mime_type = detect_mime_type(file_path)

    with open(file_path, "rb") as f:
        index = 0
        while True:
            data = f.read(CHUNK_SIZE)
            if not data:
                break

            chunk_hash = sha256(data)
            chunk_name = f"{file_path.stem}_chunk_{index}"
            chunk_path = out_dir_path / chunk_name

            with open(chunk_path, "wb") as cf:
                cf.write(data)

            chunks.append({
                "index": index,
                "hash": chunk_hash,
                "filename": chunk_name,
                "size": len(data)
            })
            index += 1

    return {
        "original_name": file_path.name,
        "original_extension": file_path.suffix,
        "file_stem": file_path.stem,
        "mime_type": mime_type,
        "chunks": chunks,
        "total_chunks": len(chunks)
    }