from pathlib import Path
import hashlib
import mimetypes

CHUNK_SIZE = 1024 * 512  # 512 KB
ADMIN_PORT = 8000
CHUNK_PORT = 9000

STORAGE_DIR = "storage"

def sha256(data: bytes) -> str:
    """Compute SHA256 hash of data and return as hex string"""
    return hashlib.sha256(data).hexdigest()

def detect_mime_type(file_path: Path) -> str:
    """
    Detect MIME type of a file
    
    Args:
        file_path: Path to the file
    
    Returns:
        str: MIME type (e.g., 'application/pdf', 'image/jpeg')
    """
    # Initialize mimetypes
    mimetypes.init()
    
    # Try to guess from extension
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    if mime_type:
        return mime_type
    
    # Fallback: detect by reading file signature (magic bytes)
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)
        
        # Common file signatures
        if header.startswith(b'%PDF'):
            return 'application/pdf'
        elif header.startswith(b'\x89PNG'):
            return 'image/png'
        elif header.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        elif header.startswith(b'GIF8'):
            return 'image/gif'
        elif header.startswith(b'PK\x03\x04'):
            return 'application/zip'
        elif header.startswith(b'Rar!'):
            return 'application/x-rar-compressed'
    except:
        pass
    
    return 'application/octet-stream'

def chunk_file(file_path: str, out_dir: str):
    """
    Chunk a file into smaller pieces with automatic file type detection
    
    Args:
        file_path: Path to the file to chunk
        out_dir: Directory to save chunks
    
    Returns:
        dict: Dictionary containing chunks list and file metadata
    """
    chunks = []
    file_path = Path(file_path)
    
    # Create output directory if it doesn't exist
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    
    # Detect MIME type
    mime_type = detect_mime_type(file_path)

    with open(file_path, "rb") as f:
        index = 0
        while True:
            data = f.read(CHUNK_SIZE)
            if not data:
                break

            chunk_hash = sha256(data)
            
            # Create chunk filename without extension for easier handling
            # Format: originalname_chunk_0, originalname_chunk_1, etc.
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

    # Return both chunks and original file info with MIME type
    return {
        "original_name": file_path.name,
        "original_extension": file_path.suffix,
        "file_stem": file_path.stem,
        "mime_type": mime_type,
        "chunks": chunks,
        "total_chunks": len(chunks)
    }

def get_chunk_info(chunk_dir: str = "storage/chunks"):
    """
    Get information about all chunks in a directory
    
    Args:
        chunk_dir: Directory containing chunks
    
    Returns:
        dict: Dictionary mapping file names to their chunks
    """
    chunk_dir_path = Path(chunk_dir)
    
    if not chunk_dir_path.exists():
        return {}
    
    file_chunks = {}
    
    for chunk_file in chunk_dir_path.iterdir():
        if chunk_file.is_file():
            # Parse filename: originalname_chunk_0
            parts = chunk_file.name.split("_chunk_")
            if len(parts) == 2:
                file_base = parts[0]
                try:
                    chunk_idx = int(parts[1])
                    
                    with open(chunk_file, "rb") as f:
                        data = f.read()
                    
                    if file_base not in file_chunks:
                        file_chunks[file_base] = []
                    
                    file_chunks[file_base].append({
                        'index': chunk_idx,
                        'filename': chunk_file.name,
                        'hash': sha256(data),
                        'size': len(data)
                    })
                except ValueError:
                    continue
    
    # Sort chunks by index
    for file_base in file_chunks:
        file_chunks[file_base].sort(key=lambda x: x['index'])
    
    return file_chunks