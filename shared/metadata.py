import json
from pathlib import Path
import mimetypes

def save_metadata(chunk_info: dict):
    """
    Save file metadata including original filename and extension
    
    Args:
        chunk_info: Dictionary from chunk_file() containing:
            - original_name: Full filename with extension
            - original_extension: File extension (.pdf, .jpg, etc.)
            - file_stem: Filename without extension
            - chunks: List of chunk dictionaries
            - total_chunks: Total number of chunks
            - mime_type: MIME type of the file
    """
    meta = {
        "original_name": chunk_info["original_name"],
        "original_extension": chunk_info["original_extension"],
        "file_stem": chunk_info["file_stem"],
        "mime_type": chunk_info.get("mime_type", "application/octet-stream"),
        "total_chunks": chunk_info["total_chunks"],
        "chunks": chunk_info["chunks"]
    }
    
    Path("storage/metadata").mkdir(parents=True, exist_ok=True)
    
    # Save metadata with file stem name (without problematic characters)
    safe_name = chunk_info['file_stem'].replace('/', '_').replace('\\', '_')
    metadata_file = f"storage/metadata/{safe_name}.json"
    with open(metadata_file, "w", encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    
    print(f"Metadata saved: {metadata_file}")
    return metadata_file

def load_metadata(file_name: str):
    """
    Load metadata for a file
    
    Args:
        file_name: Name of the file (with or without .json extension)
    
    Returns:
        dict: Metadata or None if not found
    """
    # Try different variations of the filename
    metadata_dir = Path("storage/metadata")
    
    if not metadata_dir.exists():
        return None
    
    # Try exact match first
    metadata_path = metadata_dir / f"{file_name}.json"
    if not metadata_path.exists():
        metadata_path = metadata_dir / file_name
    
    # If still not found, try to find by matching stem
    if not metadata_path.exists():
        for meta_file in metadata_dir.glob("*.json"):
            try:
                with open(meta_file, "r", encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("file_stem") == file_name or data.get("original_name") == file_name:
                        return data
            except:
                continue
        return None
    
    try:
        with open(metadata_path, "r", encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def list_available_files():
    """
    List all files that have metadata stored
    
    Returns:
        list: List of file information dictionaries
    """
    metadata_dir = Path("storage/metadata")
    
    if not metadata_dir.exists():
        return []
    
    files = []
    for metadata_file in metadata_dir.glob("*.json"):
        try:
            with open(metadata_file, "r", encoding='utf-8') as f:
                meta = json.load(f)
                files.append({
                    "name": meta.get("original_name"),
                    "extension": meta.get("original_extension"),
                    "mime_type": meta.get("mime_type"),
                    "chunks": meta.get("total_chunks"),
                    "file_stem": meta.get("file_stem")
                })
        except:
            continue
    
    return files

def get_file_metadata_by_stem(file_stem: str):
    """
    Get metadata by matching the file stem (name without extension)
    
    Args:
        file_stem: The base name of the file without extension
    
    Returns:
        dict: Metadata or None if not found
    """
    metadata_dir = Path("storage/metadata")
    
    if not metadata_dir.exists():
        return None
    
    for meta_file in metadata_dir.glob("*.json"):
        try:
            with open(meta_file, "r", encoding='utf-8') as f:
                data = json.load(f)
                if data.get("file_stem") == file_stem:
                    return data
        except:
            continue
    
    return None