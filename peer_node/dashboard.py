import streamlit as st
import time
import requests
from pathlib import Path
import socket
import logging
from pydantic import BaseModel
from typing import List, Dict, Optional

from peer_client import PeerClient

# Configuration Constants
CHUNK_SIZE = 1024 * 512  # 512 KB
STORAGE_DIR = "storage"
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


# Initialize PeerClient in session state
if 'client' not in st.session_state:
    with st.spinner("Initializing Peer Node & Server..."):
        st.session_state.client = PeerClient()
        # Auto-join
        if st.session_state.client.join_network():
            st.toast(f"Connected to network as {st.session_state.client.peer_id}")
        else:
            st.error("Failed to auto-join network. Check Tracker.")

client = st.session_state.client

st.title(f"Peer Node: {client.peer_id}")

# Sidebar status
st.sidebar.success(f"ID: {client.peer_id}")
st.sidebar.success(f"ID: {client.peer_id}")
st.sidebar.info(f"HTTP: {client.host}:{client.port}")
if hasattr(client, 'tcp_port') and client.tcp_port:
    st.sidebar.info(f"TCP: {client.host}:{client.tcp_port}")
else:
    st.sidebar.warning("TCP: Not running")

# Tracker Connection Settings
st.sidebar.divider()
st.sidebar.subheader("Connection Settings")
new_tracker_url = st.sidebar.text_input("Tracker URL", value=client.tracker_url)

if st.sidebar.button("Update / Reconnect"):
    # cleanup: remove trailing slash
    new_tracker_url = new_tracker_url.rstrip("/")
    
    # Auto-fix: Add port if missing (heuristic: no colon after the protocol part)
    # Simple check: if it looks like just an IP "192.168.1.5", add :8000
    if ":" not in new_tracker_url.replace("http://", "").replace("https://", ""):
        new_tracker_url = f"{new_tracker_url}:{DEFAULT_TRACKER_PORT}"

    # Auto-fix: Add protocol
    if not new_tracker_url.startswith("http"):
        new_tracker_url = f"http://{new_tracker_url}"
    
    client.tracker_url = new_tracker_url
    if client.join_network():
        st.toast(f"Connected to {new_tracker_url}")
        st.rerun()
    else:
        st.error(f"Could not connect to {new_tracker_url}")

if not client.token:
    st.sidebar.warning("Disconnected")
    if st.sidebar.button("Try Auto-Connect"):
        if client.join_network():
            st.toast("Connected!")
            st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Network Peers")
# We can use find_chunk_owners logic or just ask for all peers?
# Client doesn't have a public get_peers method, but we can hit the endpoint manually or add it.
# For simplicity, we can try to guess or just show count if possible.
# Wait, the prompt says "peer discovery should be also in the peer dashboard".
# We should probably add a get_peers method to client or just call the API.
try:
    # Quick hack to get peers from tracker public endpoint
    # The endpoint is /admin/peers but maybe we should use that
    r = requests.get(f"{client.tracker_url}/admin/peers")
    if r.status_code == 200:
        peers = r.json()
        st.sidebar.write(f"Active Peers: {len(peers)}")
        for p in peers:
            if p['peer_id'] != client.peer_id:
                st.sidebar.caption(f"👤 {p['peer_id']}")
except:
    st.sidebar.caption("Peer list unavailable")


st.header("Available Files")

with st.expander("Browse Network Files", expanded=True):
    if st.button("Refresh File List"):
        st.rerun()
        
    network_files = client.list_files()
    if network_files:
        for f in network_files:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**📄 {f['name']}**")
                    st.write(f"Size: {f['total_chunks']} chunks | Type: {f.get('mime_type', 'unknown')}")
                with c2:
                    if st.button("Download", key=f"dl_{f['stem']}", use_container_width=True):
                        # Verify we want to download this
                        with st.status(f"Downloading {f['name']}...", expanded=True) as status:
                            res = client.download_file(f['stem'])
                            if "complete" in res:
                                status.update(label="Complete!", state="complete")
                                st.success(f"Saved {f['name']}")
                                st.balloons()
                            else:
                                status.update(label="Failed", state="error")
                                st.error(res)
    else:
        st.info("No files found on network.")

st.header("Direct TCP Transfer (Push)")
with st.expander("Push Chunk to Peer", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        target_ip = st.text_input("Target IP", placeholder="192.168.1.X")
    with c2:
        target_tcp_port = st.text_input("Target TCP Port", value="9001", placeholder="9001")
    
    # Files to send (from available list)
    files = client.list_files()
    file_options = {f['name']: f['stem'] for f in files} if files else {}
    
    selected_file = st.selectbox("Select File", options=list(file_options.keys()) if file_options else ["No files available"])
    
    if selected_file and file_options:
        selected_stem = file_options[selected_file]
        # Find max chunks for this file
        total_chunks = next((f['total_chunks'] for f in files if f['stem'] == selected_stem), 1)
        chunk_idx = st.number_input("Chunk Index", min_value=0, max_value=total_chunks-1, step=1)
        
        if st.button("Push Chunk via TCP"):
            if not target_ip or not target_tcp_port:
                st.error("Please enter Target IP and TCP Port")
            else:
                with st.spinner(f"Pushing chunk {chunk_idx} to {target_ip}:{target_tcp_port}..."):
                    status = client.push_chunk_tcp(target_ip, int(target_tcp_port), selected_stem, chunk_idx)
                    if "Success" in status:
                        st.success(f"Chunk sent successfully!")
                    else:
                        st.error(status)

st.header("Manual Download (Advanced)")

file_stem = st.text_input("Enter File Name (stem) to Download", placeholder="my_document")

if st.button("Download File"):
    if not client.token:
        st.error("Cannot download: Not connected to network.")
    else:
        with st.status("Downloading...", expanded=True) as status:
            st.write("Fetching metadata...")
            meta = client.get_metadata(file_stem)
            if not meta:
                status.update(label="File not found!", state="error")
                st.error("File not found on tracker.")
            else:
                st.write(f"Found {meta['original_name']} ({meta['total_chunks']} chunks). Finding peers...")
                result = client.download_file(file_stem)
                
                if "complete" in result:
                    status.update(label="Download Complete!", state="complete")
                    st.success(f"File saved to `storage/downloads/{meta['original_name']}`.\nCheck terminal for debug path.")
                    st.balloons()
                else:
                    status.update(label="Download Failed", state="error")
                    st.error(result)

st.divider()
st.subheader("My Received Chunks")
# Just scan directory to show what we have
chunk_dir = Path("..") / "storage" / "received_chunks"
if chunk_dir.exists():
    chunks = list(chunk_dir.glob("*_chunk_*"))
    st.write(f"Total Chunks Stored: {len(chunks)}")
    if chunks:
        with st.expander("View Chunks"):
            st.write([c.name for c in chunks])
else:
    st.write("No chunks received yet.")
