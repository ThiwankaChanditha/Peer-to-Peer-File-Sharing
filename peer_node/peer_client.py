# peer_node/peer_client.py — top of file
import requests, threading, time, hashlib, json, random, socket, logging, sys
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from security.hashing import sha256
from security.crypto import load_or_generate_keys
from shared.config import (
    CHUNK_SIZE, DEFAULT_TRACKER_PORT, MAX_CLUSTER_SIZE, PEER_SAMPLE_SIZE,
    get_lan_ip, find_available_port, sanitize_stem,
    PeerInfo, ChunkLocation, FileMetadata, ChunkData
)

STORAGE_PATH = BASE_DIR / "storage"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
from peer_server import start_peer_server
from tcp_handler import TCPServer, send_tcp_packet

class PeerClient:
    def __init__(self, tracker_url: str = f"http://localhost:{DEFAULT_TRACKER_PORT}"):
        self.tracker_url = tracker_url
        self.peer_storage_path = BASE_DIR / "storage" / "peer_data" / "this_peer"
        self.private_key, self.public_key_obj = load_or_generate_keys(self.peer_storage_path)

        from security.crypto import serialize_public_key
        import hashlib as _hl
        self.public_key = serialize_public_key(self.public_key_obj)
        self.peer_id = "peer_" + _hl.sha256(self.public_key.encode()).hexdigest()[:16]
        self.host = get_lan_ip()
        
        # Find contiguous ports for HTTP (port) and TCP (port + 1)
        def find_port_pair(start):
            p = start
            while p < 65500:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s1:
                        s1.bind((self.host, p))
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                            s2.bind((self.host, p + 1))
                            return p
                except OSError:
                    p += 1
            return start

        self.port = find_port_pair(5000)
        self.tcp_port = self.port + 1

        self.tcp_server = TCPServer(self.host, self.tcp_port)
        # We override the inner auto-increment since we verified the port
        self.tcp_server.port = self.tcp_port
        self.tcp_server.start()
        
        # Start the HTTP chunk server
        threading.Thread(target=start_peer_server, args=(self.host, self.port), daemon=True).start()

        # Generate or load RSA Keys for this peer
        self.peer_storage_path = BASE_DIR / "storage" / "peer_data" / self.peer_id
        self.private_key, self.public_key_obj = load_or_generate_keys(self.peer_storage_path)
        
        from security.crypto import serialize_public_key
        self.public_key = serialize_public_key(self.public_key_obj)

        self.token = None
        self.active_peers = []
        
        # cluster: dict mapping peer_id -> latency (ms)
        self.cluster = {}
        
        # Start background threads
        # Start the UDP broadcaster listener thread
        # We'll rely on Tracker config but it listens on UDP 8001
        threading.Thread(target=self.listen_for_broadcasts, daemon=True).start()
        
        # Start cluster update thread (heartbeat & latency checks)
        threading.Thread(target=self.update_cluster_loop, daemon=True).start()
        
        logging.info(f"Initialized Peer {self.peer_id} at {self.host}:{self.port}")
        
    def update_cluster_loop(self):
        """Background thread to periodically update cluster latencies"""
        while True:
            time.sleep(15) # Refresh every 15 seconds
            try:
                self.update_cluster()
            except Exception as e:
                logging.error(f"Failed to update cluster: {e}")

    def measure_latency(self, host: str, port: int) -> float:
        """Measure latency to a peer (tcp handshake time approximation)"""
        start = time.time()
        try:
            with socket.create_connection((host, int(port)), timeout=2.0) as s:
                pass
            return (time.time() - start) * 1000 # ms
        except Exception:
            return float('inf')

    def _heartbeat_loop(self):
        """Send a heartbeat to the tracker every 30 seconds."""
        while True:
            time.sleep(30)
            if self.token:
                try:
                    requests.post(
                        f"{self.tracker_url}/heartbeat",
                        params={"peer_id": self.peer_id, "token": self.token},
                        timeout=5
                    )
                except Exception:
                    pass

    def update_cluster(self):
        """
        Refreshes the local cluster of 'best' peers.
        Strategy:
        1. Always re-check existing cluster members (to verify they are still fast).
        2. Randomly sample a few new peers from the rest of the network (to explore).
        3. Keep only the top MAX_CLUSTER_SIZE peers sorted by latency.
        """
        all_peers = self.get_active_peers()
        if not all_peers:
            return

        network_peers = {p['peer_id']: p for p in all_peers if p['peer_id'] != self.peer_id}
        
        # 1. Existing members
        candidates = set(self.cluster.keys())
        
        # 2. Add random samples from network
        available = list(set(network_peers.keys()) - candidates)
        if available:
            sample_size = min(PEER_SAMPLE_SIZE, len(available))
            candidates.update(random.sample(available, sample_size))
            
        new_cluster_latencies = {}
        
        for pid in candidates:
            if pid in network_peers:
                p_info = network_peers[pid]
                lat = self.measure_latency(p_info['host'], p_info['port'])
                if lat < float('inf'):
                    new_cluster_latencies[pid] = lat
                    
        # 3. Sort and keep top ones
        sorted_peers = sorted(new_cluster_latencies.items(), key=lambda x: x[1])
        top_peers = sorted_peers[:MAX_CLUSTER_SIZE]
        
        self.cluster = dict(top_peers)
        logging.debug(f"Updated Cluster (Size: {len(self.cluster)}): {self.cluster}")

    def listen_for_broadcasts(self):
        udp_port = 9999
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try: sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError: pass
        sock.bind(("", udp_port))

        # Load tracker public key if we have it pre-seeded
        tracker_pub_key_path = BASE_DIR / "storage" / "tracker_public_key.pem"

        while True:
            try:
                data, addr = sock.recvfrom(4096)
                outer = json.loads(data.decode())

                payload_str = outer.get("payload")
                signature   = outer.get("signature")

                # ── Verify if we have the tracker public key ───
                if tracker_pub_key_path.exists() and signature:
                    from security.crypto import verify_signature
                    pub_key = tracker_pub_key_path.read_text()
                    if not verify_signature(pub_key, payload_str.encode(), signature):
                        logging.warning(f"[UDP] Rejected unsigned/forged broadcast from {addr}")
                        continue
                # If we don't have the key yet, trust first broadcast (TOFU)
                # and save the key from the tracker's /tracker_pubkey endpoint
                elif not tracker_pub_key_path.exists():
                    logging.warning("[UDP] No tracker public key — trusting first broadcast (TOFU)")

                msg = json.loads(payload_str)
                if msg.get("action") == "tracker_presence":
                    ip   = msg.get("ip")
                    port = msg.get("port", DEFAULT_TRACKER_PORT)
                    new_url = f"http://{ip}:{port}"
                    if new_url != self.tracker_url:
                        logging.info(f"Discovered tracker at {new_url}")
                        self.tracker_url = new_url
                        # Cache the key for future verification
                        if not tracker_pub_key_path.exists():
                            try:
                                r = requests.get(f"{new_url}/tracker_pubkey", timeout=3)
                                if r.status_code == 200:
                                    tracker_pub_key_path.write_text(r.json()["public_key"])
                            except Exception:
                                pass
                        self.join_network()
            except Exception as e:
                logging.error(f"UDP listener error: {e}")
                time.sleep(2)

    def join_network(self) -> bool:
        """Register with the tracker"""
        url = f"{self.tracker_url}/join"
        data = {
            "peer_id": self.peer_id,
            "host": self.host,
            "port": self.port,
            "status": "active",
            "public_key": self.public_key
        }
        try:
            response = requests.post(url, json=data, timeout=5)
            if response.status_code == 200:
                resp_json = response.json()
                if "token" in resp_json:
                    self.token = resp_json["token"]
                logging.info(f"Joined network successfully. Configured port: {self.port}")
                return True
            logging.error(f"Join failed: {response.text}")
            return False
        except requests.RequestException as e:
            logging.error(f"Could not connect to tracker: {e}")
            return False

    def get_metadata(self, file_stem: str) -> Optional[dict]:
        try:
            from urllib.parse import quote
            safe_stem = quote(file_stem)
            params = {"peer_id": self.peer_id, "token": self.token}
            # Use safe_stem in URL path
            res = requests.get(f"{self.tracker_url}/metadata/{safe_stem}", params=params)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception:
            return None

    def get_active_peers(self) -> List[dict]:
        try:
            from shared.config import load_admin_key
            admin_key = load_admin_key()
            res = requests.get(
                f"{self.tracker_url}/admin/peers",
                headers={"X-Admin-Key": admin_key},
                timeout=5
            )
            if res.status_code == 200:
                return res.json()
            return []
        except Exception as e:
            logging.error(f"Error fetching peers: {e}")
            return []

    def list_files(self) -> List[dict]:
        """Fetch list of available files from tracker"""
        try:
            res = requests.get(f"{self.tracker_url}/files")
            if res.status_code == 200:
                return res.json()
            return []
        except Exception:
            return []

    def find_chunk_owners(self, file_stem: str, chunk_index: int) -> List[dict]:
        try:
            from urllib.parse import quote
            safe_stem = quote(file_stem)
            params = {"peer_id": self.peer_id, "token": self.token}
            res = requests.get(
                f"{self.tracker_url}/peers/{safe_stem}/{chunk_index}", 
                params=params
            )
            if res.status_code == 200:
                return res.json().get("owners", [])
            return []
        except Exception:
            return []

    def download_file(self, file_stem: str):
        file_stem = sanitize_stem(file_stem)
        metadata = self.get_metadata(file_stem)
        if not metadata:
            return "Metadata not found"

        local_storage = STORAGE_PATH / "received_chunks"
        local_storage.mkdir(parents=True, exist_ok=True)

        meta_dir = STORAGE_PATH / "metadata"
        meta_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(meta_dir / f"{file_stem}.json", "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logging.warning(f"Failed to save metadata locally: {e}")

        missing = []

        def fetch_chunk(i: int) -> bool:
            chunk_name = f"{file_stem}_chunk_{i}"
            chunk_path = local_storage / chunk_name

            # Already have it locally?
            if chunk_path.exists():
                with open(chunk_path, "rb") as f:
                    data = f.read()
                if hashlib.sha256(data).hexdigest() == metadata["chunks"][i]["hash"]:
                    self.announce_chunk(file_stem, i)
                return True

            peers = self.find_chunk_owners(file_stem, i)
            peers.sort(key=lambda p: self.cluster.get(p["peer_id"], 9999))

            for peer in peers:
                if peer["peer_id"] == self.peer_id:
                    continue
                url = f"http://{peer['host']}:{peer['port']}/chunk/{file_stem}/{i}"
                try:
                    params = {"peer_id": self.peer_id, "token": self.token} \
                            if peer.get("type") == "tracker" else {}
                    r = requests.get(url, params=params, timeout=10)
                    if r.status_code == 200:
                        chunk_data = r.content
                        if hashlib.sha256(chunk_data).hexdigest() == metadata["chunks"][i]["hash"]:
                            with open(chunk_path, "wb") as f:
                                f.write(chunk_data)
                            self.announce_chunk(file_stem, i)
                            return True
                except Exception:
                    continue
            return False

        # ── Parallel download ──────────────────────────────────
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(fetch_chunk, i): i
                    for i in range(metadata["total_chunks"])}
            for future in as_completed(futures):
                i = futures[future]
                if not future.result():
                    missing.append(i)

        if missing:
            return f"Partial Download. Missing chunks: {sorted(missing)}"

        downloaded = [{"index": i,
                    "filename": f"{file_stem}_chunk_{i}"}
                    for i in range(metadata["total_chunks"])]
        if self.reassemble(file_stem, metadata, downloaded):
            return "Download complete"
        return "Reassembly failed"

    def repair_file(self, file_stem: str):
        """Attempt to download missing chunks for a file"""
        return self.download_file(file_stem)

    def announce_chunk(self, file_stem: str, chunk_index: int):
        try:
            requests.post(
                f"{self.tracker_url}/announce_chunk",
                params={"peer_id": self.peer_id, "token": self.token},
                json={"file_stem": file_stem, "chunk_index": chunk_index}
            )
        except Exception:
            pass

    def reassemble(self, file_stem: str, metadata: dict, chunks: list):
        out_dir = STORAGE_PATH / "downloads"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = metadata.get("original_name", f"{file_stem}.out")
        out_path = out_dir / fname
        
        chunks.sort(key=lambda x: x['index'])
        
        try:
            print(f"[DEBUG] Reassembling to: {out_path}")
            with open(out_path, "wb") as outfile:
                for c in chunks:
                    chunk_path = STORAGE_PATH / "received_chunks" / c['filename']
                    print(f"[DEBUG] Reading chunk: {chunk_path}")
                    with open(chunk_path, "rb") as infile:
                        outfile.write(infile.read())
            print(f"[DEBUG] Reassembly success: {out_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Reassembly failed: {e}")
            return False

    def push_file_tcp(self, target_ip, target_port, file_stem):
        """
        Manually push an entire file (metadata + all chunks) to another peer via TCP
        """
        # 1. Send Metadata
        meta_path = BASE_DIR / "storage" / "metadata" / f"{file_stem}.json"
        
        # Load meta to know how many chunks
        try:
            with open(meta_path, 'r') as f:
                meta_json = json.load(f)
        except Exception as e:
            return False, f"Could not read metadata for {file_stem}: {e}"

        meta_header = {
            "packet_type": "metadata",
            "file_stem": file_stem
        }
        success, msg = send_tcp_packet(target_ip, target_port, meta_header, meta_path)
        if not success:
            return False, f"Failed to send metadata: {msg}"
        
        # 2. Send Chunks
        total_chunks = meta_json.get("total_chunks", 0)

        for i in range(total_chunks):
            chunk_name = f"{file_stem}_chunk_{i}"

            # Check storage/chunks first, then fall back to storage/received_chunks
            chunk_path = BASE_DIR / "storage" / "chunks" / chunk_name
            if not chunk_path.exists():
                chunk_path = BASE_DIR / "storage" / "received_chunks" / chunk_name

            chunk_header = {
                "packet_type": "chunk",
                "file_stem": file_stem,
                "chunk_index": i
            }
            c_success, c_msg = send_tcp_packet(target_ip, target_port, chunk_header, chunk_path)
            if not c_success:
                return False, f"Failed to send chunk {i}: {c_msg}"
                
        return True, "File pushed successfully"

    def reassemble_local_file(self, file_stem: str):
        """Reassemble a file from locally stored received chunks"""
        meta_path = STORAGE_PATH / "metadata" / f"{file_stem}.json"
        try:
            with open(meta_path, "r") as f:
                metadata = json.load(f)
        except Exception as e:
            return False, f"Could not read metadata: {e}"

        chunks = []
        for i in range(metadata['total_chunks']):
            chunk_name = f"{file_stem}_chunk_{i}"
            chunks.append({"index": i, "filename": chunk_name})

        ok = self.reassemble(file_stem, metadata, chunks)
        if ok:
            return True, "Reassembly successful"
        return False, "Reassembly failed"

    def submit_assignment_tcp(self, target_ip: str, target_port: int, file_path: Path) -> tuple[bool, str]:
        """
        Signs the assignment file and submits it to the Privileged Node via TCP.
        Returns (success, message)
        """
        try:
            if not file_path.exists():
                return False, f"File not found: {file_path}"
                
            # Read file data to sign
            with open(file_path, "rb") as f:
                data = f.read()
                
            from security.crypto import sign_data
            signature = sign_data(self.private_key, data)
            
            file_stem = file_path.stem
            original_name = file_path.name
            
            assignment_header = {
                "packet_type": "assignment",
                "file_stem": file_stem,
                "original_name": original_name,
                "peer_id": self.peer_id,
                "signature": signature
            }
            
            success, msg = send_tcp_packet(target_ip, target_port, assignment_header, file_path)
            return success, msg
            
        except Exception as e:
            msg = f"Failed to submit assignment: {e}"
            logging.error(msg)
            return False, msg

if __name__ == "__main__":
    pass
