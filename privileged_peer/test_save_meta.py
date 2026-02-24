import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from privileged_peer.metadata import save_metadata

chunk_info = {
    "original_name": "Vectordb_By_Hand_Final_Blank.txt",
    "original_extension": ".txt",
    "file_stem": "Vectordb_By_Hand_Final_Blank",
    "mime_type": "text/plain",
    "total_chunks": 1,
    "chunks": []
}

try:
    path = save_metadata(chunk_info)
    print(f"Saved correctly to {path}")
    print(f"Exists? {Path(path).exists()}")
except Exception as e:
    print(f"Exception: {e}")
