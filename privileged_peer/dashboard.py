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
import socket
BASE_DIR = Path(__file__).resolve().parent.parent
def get_lan_ip():
    """Detect the local machine's physical LAN IP address"""
    try:
        host_name = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(host_name)[2]
        
        valid_ips = []
        for ip in ip_addresses:
            if ip.startswith("127."): continue
            if ip.startswith("169.254."): continue
            if ip.startswith("172."): continue  # Docker/WSL/Hyper-V
            if ip.startswith("192.168.56."): continue # VirtualBox Host-Only
            valid_ips.append(ip)
            
        if valid_ips:
            # Prefer typical home router subnets
            for ip in valid_ips:
                if ip.startswith("192.168.") or ip.startswith("10."):
                    return ip
            return valid_ips[0]
            
        # Offline fallback: dummy local connection to force OS to choose an interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('192.168.1.1', 1)) 
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

SERVER_URL = f"http://localhost:{DEFAULT_TRACKER_PORT}"

# Initialize session state
if 'files' not in st.session_state:
    st.session_state.files = {}

st.title("Network Admin Console")
st.sidebar.markdown(f"**Tracker IP:** `{get_lan_ip()}:{DEFAULT_TRACKER_PORT}`")

page = st.sidebar.selectbox("Navigation", ["Publish New File", "Connected Peers", "Submissions"])

# Page 1: Upload Files
if page == "Publish New File":
    st.header("Publish & Share File")
    
    uploaded = st.file_uploader("Upload Assignment/File", type=['pdf', 'docx', 'txt', 'zip', 'jpg', 'png', 'mp4'])
    
    if uploaded:
        # Save uploaded file to project root storage
        # Need to be careful with paths. Chunker expects to write to ../storage/chunks
        # This dashboard runs in privileged_peer/
        
        # Temp save
        temp_dir = BASE_DIR / "temp_uploads"
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
                                                    # Try glob fallback
                                                    for m in (STORAGE_PATH / "metadata").glob("*.json"):
                                                        if m.stem == f['stem']:
                                                            meta_path = m
                                                            break
                                                
                                                if not meta_path.exists():
                                                    st.error(f"Metadata not found locally for {f['stem']}.")
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

# Page 3: Submissions
elif page == "Submissions":
    st.header("📥 Secure Assignment Submissions")

    st.markdown(
        """
        Assignments securely submitted by Peer Nodes.  
        Each file here has passed RSA Signature verification for:

        - **Authenticity**   
        - **Integrity**   
        """
    )
    assignments_dir = STORAGE_PATH / "assignments"

    if not assignments_dir.exists():
        st.info("No assignments received yet.")
    else:
        peer_dirs = [d for d in assignments_dir.iterdir() if d.is_dir()]
        if not peer_dirs:
            st.info("No assignments received yet.")
        else:
            for pdir in peer_dirs:
                peer_id = pdir.name
                files = list(pdir.iterdir())
                if not files:
                    continue
                with st.expander(f"👤 {peer_id} ({len(files)} submissions)"):
                    for file_path in files:
                        col1, col2, col3 = st.columns([3, 2, 1])
                        with col1:
                            st.markdown(f"**{file_path.name}**")
                        with col2:
                            # Already verified by tcp_handler
                            st.success("✅ Verified")
                        with col3:
                            with open(file_path, "rb") as assign_file:
                                st.download_button(
                                    label="Download",
                                    data=assign_file.read(),
                                    file_name=file_path.name,
                                    mime="application/octet-stream",
                                    key=f"dl_{peer_id}_{file_path.name}"

                                )
