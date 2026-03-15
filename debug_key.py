import os
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

print(f"cwd: {os.getcwd()}")
try:
    from shared.config import load_admin_key, __file__ as config_file
    print(f"shared.config path: {config_file}")
    
    config_path = Path(config_file).resolve().parent.parent / "admin_key.txt"
    print(f"Expected admin_key.txt path: {config_path}")
    print(f"Exists: {config_path.exists()}")
    if config_path.exists():
        print(f"Content: {repr(config_path.read_text())}")
        
    print(f"Result of load: {repr(load_admin_key())}")
except Exception as e:
    print(f"Error: {e}")
