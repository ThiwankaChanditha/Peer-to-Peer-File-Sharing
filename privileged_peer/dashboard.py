import streamlit as st
import requests
import json
from pathlib import Path
import time

# Local imports
from chunker import chunk_file
from metadata import save_metadata
from config import DEFAULT_TRACKER_PORT
from tcp_handler import send_chunk_tcp, STORAGE_PATH

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
    
    st.header("Direct TCP Transfer (Push)")
    with st.expander("Push Chunk to Peer", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            target_ip = st.text_input("Target IP", placeholder="192.168.1.X")
        with c2:
            target_tcp_port = st.text_input("Target TCP Port", value="9001", placeholder="9001")
        
        # Files to send (fetch from server API or local logic)
        try:
            res = requests.get(f"{SERVER_URL}/files")
            files = res.json() if res.status_code == 200 else []
        except:
            files = []
            
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
                    # Resolve chunk path
                    chunk_name = f"{selected_stem}_chunk_{chunk_idx}"
                    chunk_path = STORAGE_PATH / "chunks" / chunk_name
                    
                    if not chunk_path.exists():
                        # Maybe it is in received_chunks if we are hybrid
                        chunk_path = STORAGE_PATH / "received_chunks" / chunk_name

                    if not chunk_path.exists():
                         st.error(f"Chunk file not found locally: {chunk_name}")
                    else:
                        with st.spinner(f"Pushing chunk {chunk_idx} to {target_ip}:{target_tcp_port}..."):
                            success, msg = send_chunk_tcp(target_ip, int(target_tcp_port), selected_stem, chunk_idx, chunk_path)
                            if success:
                                st.success(f"Chunk sent successfully!")
                            else:
                                st.error(f"Failed to send: {msg}")
