import streamlit as st
import requests
import json
from pathlib import Path
import time

# Local imports
from chunker import chunk_file
from metadata import save_metadata
from config import DEFAULT_TRACKER_PORT
from tcp_handler import send_tcp_packet, STORAGE_PATH

SERVER_URL = f"http://localhost:{DEFAULT_TRACKER_PORT}"

# Initialize session state
if 'files' not in st.session_state:
    st.session_state.files = {}

st.title("Admin (Tracker) Dashboard")

page = st.sidebar.selectbox("Navigation", ["Upload Files", "Peer Management"])

# Page 1: Upload Files
if page == "Upload Files":
    st.header("Upload and Chunk Files")
    
    uploaded = st.file_uploader("Upload Assignment/File", type=['pdf', 'docx', 'txt', 'zip', 'jpg', 'png', 'mp4'])
    
    if uploaded:
        # Save uploaded file to project root storage
        # Need to be careful with paths. Chunker expects to write to ../storage/chunks
        # This dashboard runs in privileged_peer/
        
        # Temp save
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        file_path = temp_dir / uploaded.name
        
        with open(file_path, "wb") as f:
            f.write(uploaded.read())
        
        # Chunk the file
        # chunker.py uses STORAGE_PATH = ../storage
        chunk_info = chunk_file(str(file_path))
        save_metadata(chunk_info)
        
        st.session_state.files[uploaded.name] = chunk_info
        st.success(f"File chunked into {chunk_info['total_chunks']} parts")
        
        # Notify Server (Register the file)
        try:
            reg_payload = {
                "file_stem": chunk_info['file_stem'],
                "original_name": chunk_info['original_name'],
                "total_chunks": chunk_info['total_chunks'],
                "mime_type": chunk_info.get('mime_type', 'application/octet-stream')
            }
            res = requests.post(f"{SERVER_URL}/register_file", json=reg_payload)
            if res.status_code == 200:
                st.info("File registered with network tracker.")
            else:
                 st.error(f"Failed to register file: {res.status_code} {res.text}")
        except Exception as e:
            st.error(f"Failed to register file with tracker: {e}")

        with st.expander("Chunk Details"):
            st.write(f"Original: {chunk_info['original_name']}")
            st.write(f"MIME: {chunk_info.get('mime_type')}")
            st.dataframe(chunk_info['chunks'])

    st.divider()
    st.subheader("Active Shared Files (Network Registry)")
    
    if st.button("Refresh File List"):
        st.rerun()

    try:
        res = requests.get(f"{SERVER_URL}/files")
        if res.status_code == 200:
            files = res.json()
            if files:
                for f in files:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{f['name']}**")
                        st.caption(f"Stem: `{f['stem']}` | Chunks: {f['total_chunks']}")
                    with col2:
                        st.success("Shared")
                    st.divider()
            else:
                st.info("No files currently registered.")
        else:
            st.warning("Could not fetch file list.")
    except Exception:
        st.warning("Tracker offline?")

# Page 2: Peer Management
elif page == "Peer Management":
    st.header("Peer Management")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Connected Peers (Live from API)")
    with col2:
        if st.button("Refresh List"):
            st.rerun()
    
    try:
        res = requests.get(f"{SERVER_URL}/admin/peers")
        if res.status_code == 200:
            peers = res.json()
            if peers:
                for peer in peers:
                    with st.container():
                        c1, c2, c3 = st.columns([2, 2, 1])
                        with c1:
                            st.markdown(f"**{peer['peer_id']}**")
                        with c2:
                            st.code(f"{peer['host']}:{peer['port']}")
                        with c3:
                            st.write("🟢 Active")
                        st.divider()
            else:
                st.info("No peers connected.")
        else:
            st.error(f"Failed to fetch peers: {res.status_code}")
            st.warning("Make sure server.py is running!")
    except Exception as e:
        st.error(f"Error connecting to server: {e}")
        st.warning("Make sure server.py is running!")

    # Manual Add (Simulated via Client logic really, but here for Admin override?)
    st.divider()
    
    # --- Enhanced Peer Management & Sending ---
    st.divider()
    
    st.header("Direct TCP Transfer (Push)")
    
    # Files to send
    try:
        res = requests.get(f"{SERVER_URL}/files")
        files = res.json() if res.status_code == 200 else []
    except:
        files = []
        
    file_options = {f['name']: f['stem'] for f in files} if files else {}
    selected_file_name = st.selectbox("Select File to Send", options=list(file_options.keys()) if file_options else ["No files available"])
    
    if selected_file_name and file_options:
        selected_stem = file_options[selected_file_name]
        total_chunks = next((f['total_chunks'] for f in files if f['stem'] == selected_stem), 1)
        st.info(f"Selected: **{selected_file_name}** ({total_chunks} Chunks)")
        
        # Target Selection
        st.subheader("Select Targets")
        
        # fetch peers again or use from above
        active_peers = []
        try:
             res = requests.get(f"{SERVER_URL}/admin/peers")
             if res.status_code == 200:
                 peers_data = res.json()
                 # Format for multiselect
                 peer_map = {f"{p['peer_id']} ({p['host']})": p for p in peers_data}
                 active_peers = list(peer_map.keys())
        except:
             pass
        
        target_options = ["Send to ALL Connected Peers"] + active_peers
        selected_targets = st.multiselect("Choose Recipients", target_options, default="Send to ALL Connected Peers")
        
        if st.button("🚀 Initiating Transfer"):
            if not selected_targets:
                st.warning("No targets selected.")
            else:
                # Determine actual targets
                final_targets = []
                if "Send to ALL Connected Peers" in selected_targets:
                    final_targets = peers_data # all of them
                else:
                    for t in selected_targets:
                        if t in peer_map:
                            final_targets.append(peer_map[t])
                
                st.write(f"Preparing to send to {len(final_targets)} peers...")
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                success_count = 0
                
                for idx, peer in enumerate(final_targets):
                    target_ip = peer['host']
                    # We assume peer is listenting on TCP = port + 1 (convention)
                    # Ideally we should store TCP port in peer info, but for now we follow convention or explicit input?
                    # The prompt says "privileged peers should be systematically displayed... and send to many peers"
                    # We'll try to guess TCP port or use a known offset. 
                    # In peer_client.py: self.tcp_port = self.port + 1
                    target_port = peer['port'] + 1
                    
                    status_text.text(f"Sending to {peer['peer_id']} ({target_ip}:{target_port})...")
                    
                    try:
                         # 1. Send Metadata
                        meta_path = STORAGE_PATH / "metadata" / f"{selected_stem}.json"
                        ok, msg = send_tcp_packet(target_ip, target_port, {"packet_type": "metadata", "file_stem": selected_stem}, meta_path)
                        
                        if not ok:
                            st.error(f"❌ Failed to connect to {peer['peer_id']}: {msg}")
                            continue
                            
                        # 2. Send Chunks
                        chunk_errors = False
                        for i in range(total_chunks):
                            chunk_name = f"{selected_stem}_chunk_{i}"
                            chunk_path = STORAGE_PATH / "chunks" / chunk_name
                            
                            ok, msg = send_tcp_packet(target_ip, target_port, {"packet_type": "chunk", "file_stem": selected_stem, "chunk_index": i}, chunk_path)
                            if not ok:
                                st.error(f"Failed chunk {i} to {peer['peer_id']}")
                                chunk_errors = True
                                break
                        
                        if not chunk_errors:
                            st.success(f"✅ Sent to {peer['peer_id']}")
                            success_count += 1
                            
                    except Exception as e:
                        st.error(f"Error with {peer['peer_id']}: {e}")
                    
                    progress_bar.progress((idx + 1) / len(final_targets))
                
                status_text.text("Batch sending complete.")
                if success_count == len(final_targets):
                    st.balloons()
