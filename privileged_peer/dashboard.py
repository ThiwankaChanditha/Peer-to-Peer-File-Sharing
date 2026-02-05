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

st.title("Network Admin Console")

page = st.sidebar.selectbox("Navigation", ["Publish New File", "Connected Peers"])

# Page 1: Upload Files
if page == "Publish New File":
    st.header("Publish & Share File")
    
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
        st.success(f"File processed: {chunk_info['total_chunks']} chunks created.")
        
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
                st.info("File registered and live on network.")
            else:
                 st.error(f"Failed to register file: {res.status_code} {res.text}")
        except Exception as e:
            st.error(f"Failed to register file with tracker: {e}")

        with st.expander("Technical Details (Chunks)"):
            st.write(f"Original: {chunk_info['original_name']}")
            st.write(f"MIME: {chunk_info.get('mime_type')}")
            st.dataframe(chunk_info['chunks'])

    st.divider()
    st.subheader("Global File Registry (Active Shares)")

    # Search Bar
    search_query = st.text_input("🔍 Search Files", placeholder="Type to filter...")

    if st.button("Refresh File List"):
        st.rerun()

    if st.button("Clear Registry", type="primary"):
        try:
             res = requests.delete(f"{SERVER_URL}/flush_registry")
             if res.status_code == 200:
                 st.success("Registry cleared.")
                 time.sleep(1)
                 st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    try:
        res = requests.get(f"{SERVER_URL}/files")
        if res.status_code == 200:
            files = res.json()
            if files:
                # Filter files
                filtered_files = [f for f in files if search_query.lower() in f['name'].lower()]
                
                if not filtered_files:
                    st.info("No files match your search.")
                
                for f in filtered_files:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3, 1, 1])
                        with c1:
                            st.markdown(f"**{f['name']}**")
                            st.caption(f"Stem: `{f['stem']}` | Chunks: {f['total_chunks']}")
                        with c2:
                            st.write("✅ Shared")
                        with c3:
                            if st.button("Remove", key=f"unreg_{f['stem']}", help="Unregister from network", type="primary"):
                                try:
                                    # Call unregister endpoint
                                    del_res = requests.post(f"{SERVER_URL}/unregister_file", json={"file_stem": f['stem']})
                                    if del_res.status_code == 200:
                                        st.toast(f"Unregistered {f['name']}")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("Failed")
                                except Exception as e:
                                    st.error(f"Error: {e}")

                        # Integrated Distribute / Push
                        with st.expander(f"🚀 Distribute '{f['name']}' to Peers"):
                            # Helper to fetch active peers for dropdown
                            # We fetch every render, which is fine for small scale
                            peer_options = {}
                            try:
                                pres = requests.get(f"{SERVER_URL}/admin/peers")
                                if pres.status_code == 200:
                                     for p in pres.json():
                                         peer_options[f"{p['peer_id']} ({p['host']})"] = p
                            except:
                                pass
                            
                            target_opts = ["All Active Peers"] + list(peer_options.keys())
                            selected_targets = st.multiselect("Select Recipients", target_opts, default="All Active Peers", key=f"tgt_{f['stem']}")
                            
                            if st.button("Start Transfer", key=f"push_{f['stem']}"):
                                if not selected_targets:
                                    st.warning("Select recipients first.")
                                else:
                                    # Resolve targets
                                    final_targets = []
                                    if "All Active Peers" in selected_targets:
                                        final_targets = list(peer_options.values())
                                    else:
                                        for k in selected_targets:
                                            if k in peer_options:
                                                final_targets.append(peer_options[k])
                                    
                                    if not final_targets:
                                        st.warning("No active peers found.")
                                    else:
                                        with st.spinner(f"Sending to {len(final_targets)} peers..."):
                                            progress_bar = st.progress(0)
                                            success_cnt = 0
                                            
                                            for idx, peer in enumerate(final_targets):
                                                target_ip = peer['host']
                                                # Convention: tcp = http port + 1
                                                target_port = peer['port'] + 1
                                                
                                                # 1. Send Metadata
                                                meta_path = STORAGE_PATH / "metadata" / f"{f['stem']}.json"
                                                if not meta_path.exists():
                                                    st.error("Metadata not found locally.")
                                                    continue
                                                    
                                                ok, msg = send_tcp_packet(target_ip, target_port, {"packet_type": "metadata", "file_stem": f['stem']}, meta_path)
                                                if not ok:
                                                    st.error(f"Failed to connect to {peer['peer_id']}: {msg}")
                                                    continue
                                                    
                                                # 2. Send Chunks
                                                err = False
                                                for i in range(f['total_chunks']):
                                                     chunk_name = f"{f['stem']}_chunk_{i}"
                                                     chunk_path = STORAGE_PATH / "chunks" / chunk_name
                                                     if not chunk_path.exists():
                                                         # Try fallback (received?)
                                                         chunk_path = STORAGE_PATH / "received_chunks" / chunk_name
                                                     
                                                     ok, msg = send_tcp_packet(target_ip, target_port, {"packet_type": "chunk", "file_stem": f['stem'], "chunk_index": i}, chunk_path)
                                                     if not ok:
                                                         st.error(f"Chunk {i} failed to {peer['peer_id']}")
                                                         err = True
                                                         break
                                                
                                                if not err:
                                                    st.toast(f"Sent to {peer['peer_id']}")
                                                    success_cnt += 1
                                                
                                                progress_bar.progress((idx + 1) / len(final_targets))
                                            
                                            if success_cnt == len(final_targets):
                                                st.success("Transfer Completed Successfully!")

            else:
                st.info("No files currently registered.")
        else:
            st.warning("Could not fetch file list.")
    except Exception as e:
        st.warning(f"Tracker error: {e}")

# Page 2: Connected Peers
elif page == "Connected Peers":
    st.header("Network Status: Connected Peers")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Active Peer Nodes")
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

