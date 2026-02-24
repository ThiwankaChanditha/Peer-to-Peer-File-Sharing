import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")
print(f"Sys Path: {sys.path}")

try:
    import requests
    print(f"Requests version: {requests.__version__}")
except ImportError:
    print("Requests not found")

print("Attempting to import PeerClient...")
sys.path.append(os.path.join(os.getcwd(), 'peer_node'))
sys.path.append(os.path.join(os.getcwd(), 'shared'))

try:
    from peer_node.peer_client import PeerClient
    print("PeerClient imported successfully")
except Exception as e:
    print(f"Import failed: {e}")
