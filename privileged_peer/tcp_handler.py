import socket
import threading
import json
import struct
import logging
from pathlib import Path

# Resolve STORAGE_PATH relative to this script:
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_PATH = BASE_DIR / "storage"

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TCP_Handler")

class TCPServer:
    def __init__(self, host: str, start_port: int):
        self.host = host
        self.port = start_port
        self.socket = None
        self.running = False
        self.thread = None

    def start(self):
        """Start the TCP server on an available port"""
        self.port = self._bind_socket(self.port)
        self.running = True
        self.thread = threading.Thread(target=self._accept_clients, daemon=True)
        self.thread.start()
        logger.info(f"TCP Server started at {self.host}:{self.port}")
        print(f"TCP Server started at {self.host}:{self.port}")
        return self.port

    def _bind_socket(self, start_port):
        """Find an available port and bind"""
        port = start_port
        while port < 65535:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.bind((self.host, port))
                self.socket.listen(5)
                return port
            except OSError:
                port += 1
        raise RuntimeError("No available TCP ports found")

    def _accept_clients(self):
        """Main loop to accept incoming connections"""
        while self.running:
            try:
                client_sock, addr = self.socket.accept()
                logger.info(f"Accepted TCP connection from {addr}")
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock,),
                    daemon=True
                )
                client_thread.start()
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}")

    def _handle_client(self, conn: socket.socket):
        """Handle a single client connection"""
        try:
            # Protocol:
            # 1. 4 Bytes: Header Length (Network Byte Order - Big Endian)
            # 2. N Bytes: JSON Header
            # 3. M Bytes: Raw Data
            
            # Read Header Length
            raw_len = self._recv_exact(conn, 4)
            if not raw_len:
                return
            header_len = struct.unpack("!I", raw_len)[0]
            
            # Read Header
            header_json = self._recv_exact(conn, header_len)
            header = json.loads(header_json.decode('utf-8'))
            
            file_stem = header.get("file_stem")
            chunk_index = header.get("chunk_index")
            
            logger.info(f"Receiving chunk via TCP: {file_stem} [{chunk_index}]")
            print(f"[TCP] Receiving: {file_stem} chunk {chunk_index}")
            
            # Read Data (Process until EOF)
            # Ideally header should have content-length, but for now we read until socket close
            # or we can add content-length to header. Let's read chunks.
            
            chunk_name = f"{file_stem}_chunk_{chunk_index}"
            save_path = STORAGE_PATH / "received_chunks" / chunk_name
            STORAGE_PATH.joinpath("received_chunks").mkdir(parents=True, exist_ok=True)
            
            with open(save_path, "wb") as f:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    f.write(data)
            
            logger.info(f"Saved TCP chunk to {save_path}")
            print(f"[TCP] Saved: {save_path}")
            
        except Exception as e:
            logger.error(f"TCP Handler Error: {e}")
            print(f"[TCP] Error: {e}")
        finally:
            conn.close()

    def _recv_exact(self, conn, n):
        """Helper to receive exactly n bytes"""
        data = b''
        while len(data) < n:
            packet = conn.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data

def send_chunk_tcp(target_ip: str, target_port: int, file_stem: str, chunk_index: int, chunk_path: Path):
    """
    Send a chunk to a target peer via TCP
    """
    try:
        if not chunk_path.exists():
            raise FileNotFoundError(f"Chunk not found: {chunk_path}")
            
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((target_ip, int(target_port)))
            
            # Prepare Header
            header = {
                "file_stem": file_stem,
                "chunk_index": chunk_index
            }
            header_bytes = json.dumps(header).encode('utf-8')
            header_len = len(header_bytes)
            
            # Send Length (4 bytes) + Header
            s.sendall(struct.pack("!I", header_len))
            s.sendall(header_bytes)
            
            # Send Data
            with open(chunk_path, "rb") as f:
                while True:
                    data = f.read(4096)
                    if not data:
                        break
                    s.sendall(data)
            
            print(f"[TCP] Sent {file_stem} chunk {chunk_index} to {target_ip}:{target_port}")
            return True, "Success"
            
    except Exception as e:
        print(f"[TCP] Send Error: {e}")
        return False, str(e)
