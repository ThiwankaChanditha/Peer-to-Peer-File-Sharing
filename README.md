# Peer-to-Peer File Sharing Network

A decentralized, trust-based peer-to-peer file-sharing application built with Python. 

The network relies on a central **Tracker (Privileged Peer)** to manage active nodes, authenticate sessions, and track file chunks across the network, while **Peer Nodes** communicate via a resilient HTTP & custom TCP protocol to assemble chunks into full files using concurrent downloads.

## Features
- **Concurrent Chunk Downloads**: Pull file chunks dynamically from multiple peers across the network to maximize download speeds.
- **Dynamic Peer Discovery**: Uses UDP broadcasting (with TOFU signature validation) to automatically discover the Tracker on the LAN.
- **Secure Authentication**: Tracker handles session token issuing, verified across file, metadata, and chunk endpoints.
- **File Distribution**: Integrated feature to manually push chunks from your library to specific neighbors over TCP.
- **Streamlit Dashboards**: Full UI interfaces for both the administrative tracker tasks and peer node browsing.

---

## 🛠 Prerequisites

1. **Python 3.9+** installed.
2. Install the necessary dependencies:
   ```bash
   pip install fastapi uvicorn pydantic requests streamlit cryptography
   ```

---

## 🚀 How to Launch the Application

The network requires exactly **one Tracker** running before any Peer Nodes can successfully join. 

### Step 1: Start the Tracker (Privileged Peer)
The Tracker serves as the network's address book and metadata store. It consists of a FastAPI backend and a Streamlit admin dashboard.

1. Open a terminal and start the backend Tracker Server:
   ```bash
   python privileged_peer/server.py
   ```
   *(This starts the HTTP tracker on port `8000` and the TCP handler on `8001`)*

2. Open a **second** terminal and start the Admin Dashboard:
   ```bash
   streamlit run privileged_peer/dashboard.py --server.port 8501
   ```
   *(Access the admin dashboard at `http://localhost:8501` to view network health and active peers)*

> 🔒 **Security Note**: The system secures admin routes using an `ADMIN_API_KEY`. This key is auto-generated and stored in `admin_key.txt` in the root folder. Both dashboards will load this automatically. If running peers across different machines, copy `admin_key.txt` to the root folder of each machine.

### Step 2: Start a Peer Node
You can spin up as many peer nodes as you want. Each peer node runs its own auto-assigned HTTP and TCP backend within the Streamlit process.

1. Open a **new** terminal for each peer node you want to start.
2. Launch the Peer Node Dashboard:
   ```bash
   streamlit run peer_node/dashboard.py --server.port 8502
   ```
   *(Access your peer node at `http://localhost:8502`)*

3. Repeat Step 2 on different ports (e.g., `8503`, `8504`) or different machines on the same LAN to spawn additional peers!

---

## 📁 Project Structure

- `privileged_peer/`: The central tracking server and its admin UI.
- `peer_node/`: The client daemon handling chunk chunking, TCP downloading, and UI capabilities.
- `shared/`: Shared Pydantic data models, cross-node constants, and file path sanitization logic.
- `security/`: Handles token-based auth, password hashing, and RSA signature bindings.
- `storage/`: (Auto-generated) Data directory holding downloaded files, peer chunk data, metadata maps, and RSA keys.
