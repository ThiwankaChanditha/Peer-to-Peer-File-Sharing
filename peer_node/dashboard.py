import streamlit as st
import time
import requests
import json
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
elif not hasattr(st.session_state.client, 'get_active_peers'):
    st.warning("Applying system updates... Re-initializing Client to load new features.")
    del st.session_state.client
    st.rerun()

client = st.session_state.client

st.title(f"File Sharing Hub")
st.caption(f"Node ID: {client.peer_id}")

# Sidebar status
st.sidebar.success(f"Status: Online")
st.sidebar.info(f"HTTP: {client.host}:{client.port}")
if hasattr(client, 'tcp_port') and client.tcp_port:
    st.sidebar.info(f"TCP: {client.host}:{client.tcp_port}")
else:
    st.sidebar.warning("TCP: Not running")

# Tracker Connection Settings
st.sidebar.divider()
st.sidebar.subheader("Network Settings")
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
st.sidebar.subheader("Neighbors (Peers)")
# We can use find_chunk_owners logic or just ask for all peers?
# Client doesn't have a public get_peers method, but we can hit the endpoint manually or add it.
# For simplicity, we can try to guess or just show count if possible.
# Wait, the prompt says "peer discovery should be also in the peer dashboard".
# We should probably add a get_peers method to client or just call the API.
try:
    # Quick hack to get peers from tracker public endpoint
    r = requests.get(
        f"{client.tracker_url}/admin/peers",
        timeout=2
    )

    if r.status_code == 200:
        peers = r.json()
        st.sidebar.write(f"Active Nodes: {len(peers)}")

        for p in peers:
            if p.get("peer_id") != client.peer_id:
                st.sidebar.caption(f"👤 {p['peer_id']}")
    else:
        st.sidebar.caption("Peer list unavailable")

except Exception as e:
    st.sidebar.caption("Peer list unavailable")
    st.sidebar.caption(f"⚠️ {type(e).__name__}")

# -----------------------------

st.sidebar.divider()
st.sidebar.subheader("My Cluster (Network Health)")

if hasattr(client, "cluster_peers") and client.cluster_peers:
    for pid, lat in client.cluster_peers.items():
        color = "green" if lat < 50 else "orange" if lat < 200 else "red"
        st.sidebar.markdown(f":{color}[**{pid}**: {lat:.1f} ms]")
else:
    st.sidebar.caption("Calculating latency...")

if st.sidebar.button("🔄 Refresh Cluster"):
    client.update_cluster()
    st.rerun()

st.header("Network Library")

with st.expander("Browse & Download", expanded=True):
    # Search
    search_query = st.text_input("🔍 Search Files", placeholder="Type name to filter...")

    if st.button("Refresh Library"):
        st.rerun()
        
    network_files = client.list_files()
    if network_files:
        # Filter
        filtered = [f for f in network_files if search_query.lower() in f['name'].lower()]
        
        if not filtered:
            st.info("No files match your search.")
            
        for f in filtered:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                with c1:
                    st.markdown(f"**📄 {f['name']}**")
                    st.caption(f"Size: {f['total_chunks']} chunks | Type: {f.get('mime_type', 'unknown')}")
                with c2:
                    if st.button("📥 Download", key=f"dl_{f['stem']}", use_container_width=True):
                        # Verify we want to download this
                        with st.status(f"Downloading {f['name']}...", expanded=True) as status:
                            res = client.download_file(f['stem'])
                            if "complete" in res:
                                status.update(label="Complete!", state="complete")
                                st.success(f"Saved {f['name']}")
                                st.balloons()
                            elif "Partial" in res:
                                status.update(label="Partial Download", state="warning")
                                st.warning(res)
                            else:
                                status.update(label="Failed", state="error")
                                st.error(res)
                with c3:
                    # Integrated Push
                    # Using popover if available in this streamlit version, otherwise expander
                    with st.expander("Distribute"):
                        active_peers = client.get_active_peers()
                        others = [p for p in active_peers if p['peer_id'] != client.peer_id]
                        peer_opts = {f"{p['peer_id']} ({p['host']})": p for p in others}
                        
                        tgt_key = st.selectbox("To:", list(peer_opts.keys()), key=f"tgt_{f['stem']}")
                        if st.button("Send", key=f"snd_{f['stem']}"):
                            if tgt_key:
                                target = peer_opts[tgt_key]
                                tcp_port = target['port'] + 1
                                st.toast(f"Pushing to {target['host']}...")
                                status = client.push_file_tcp(target['host'], int(tcp_port), f['stem'])
                                if "Success" in status:
                                    st.success("Sent!")
                                else:
                                    st.error(status)
    else:
        st.info("Library is empty. (Check connection or wait for uploads)")


st.header("Advanced Actions")
with st.expander("Manual Download via ID"):
    file_stem = st.text_input("Enter File ID (stem)", placeholder="my_document")

    if st.button("Download by ID"):
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
                        st.success(f"File saved to `storage/downloads/{meta['original_name']}`.")
                        st.balloons()
                    elif "Partial" in result:
                        status.update(label="Partial Download", state="warning")
                        st.warning(result)
                        if st.button("Retry / Repair Missing Chunks"):
                            with st.spinner("Retrying..."):
                                res_retry = client.repair_file(file_stem)
                                if "complete" in res_retry:
                                    st.success("Repair successful!")
                                    st.rerun()
                                else:
                                    st.error(f"Still missing chunks: {res_retry}")
                    else:
                        status.update(label="Download Failed", state="error")
                        st.error(result)

st.divider()
st.subheader("My Library (Downloads)")

# Search Received
recv_search = st.text_input("🔍 Search Local Files", placeholder="Filter...")

# Scan for metadata files in storage/metadata
meta_dir = Path("..") / "storage" / "metadata"
if meta_dir.exists():
    meta_files = list(meta_dir.glob("*.json"))
    if meta_files:
        # Filter
        filtered_meta = []
        for mf in meta_files:
            try:
                with open(mf, "r") as f:
                    m = json.load(f)
                name = m.get('original_name', mf.stem)
                if recv_search.lower() in name.lower():
                     filtered_meta.append((mf, m))
            except:
                pass
                
        if not filtered_meta:
            st.info("No files match.")

        for mf, meta in filtered_meta:
             try:
                 stem = mf.stem
                 original_name = meta.get('original_name', stem)
                 total = meta.get('total_chunks', 0)
                 
                 # Check if we have all chunks (received_chunks)
                 chunk_dir = Path("..") / "storage" / "received_chunks"
                 have_count = 0
                 for i in range(total):
                     if (chunk_dir / f"{stem}_chunk_{i}").exists():
                         have_count += 1
                 
                 # Check if final download exists
                 download_dir = Path("..") / "storage" / "downloads"
                 final_path = download_dir / original_name
                 is_done = final_path.exists()
                 
                 with st.container(border=True):
                     c1, c2, c3 = st.columns([3, 2, 1])
                     with c1:
                         st.markdown(f"**{original_name}**")
                         st.caption(f"Stem: `{stem}`")
                     with c2:
                         if is_done:
                             st.success("✅ Assembled")
                         elif have_count == total:
                             st.info(f"Chunks Ready ({have_count}/{total})")
                             if st.button("Finalize", key=f"fin_{stem}"):
                                 ok, msg = client.reassemble_local_file(stem)
                                 if ok:
                                     st.balloons()
                                     st.rerun()
                         else:
                             st.warning(f"Incomplete ({have_count}/{total})")
                     with c3:
                         if st.button("Delete", key=f"del_{stem}", type="primary"):
                             # Delete all traces
                             try:
                                 # 1. Metadata
                                 mf.unlink()
                                 # 2. Received Chunks
                                 for p in chunk_dir.glob(f"{stem}_chunk_*"):
                                     p.unlink()
                                 # 3. Final File (Optional? Let's do it to clean up)
                                 if final_path.exists():
                                     final_path.unlink()
                                 # 4. Standard Chunks (if we acted as uploader?)
                                 # Careful, maybe we shouldn't delete if we are the uploader of this file?
                                 # For this task, we assume 'My Received Files' targets things we downloaded/received.
                                 # But metadata is shared. 
                                 # Let's delete safely.
                                 st.toast(f"Deleted {original_name}")
                                 time.sleep(1)
                                 st.rerun()
                             except Exception as e:
                                 st.error(f"Error: {e}")

             except Exception as e:
                 st.error(f"Error reading {mf.name}: {e}")
    else:
        st.info("No local files found (no metadata).")
else:
    st.info("Storage/metadata folder missing.")

st.divider()
st.subheader("My Received Chunks (Raw)")
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
