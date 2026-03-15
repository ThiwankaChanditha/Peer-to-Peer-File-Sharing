# Peer-to-Peer File Sharing Network

> **Decentralised · Trust-Based · Concurrent Chunk Downloads**
>
> Built with Python · FastAPI · Streamlit · RSA Cryptography

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-latest-green)
![Streamlit](https://img.shields.io/badge/Streamlit-latest-red)
![Licence](https://img.shields.io/badge/Licence-MIT-yellow)

---

## Table of Contents

1. [Project Description](#1-project-description)
2. [System Architecture & Design](#2-system-architecture--design)
3. [Technologies Used](#3-technologies-used)
4. [Installation Instructions](#4-installation-instructions)
5. [Usage Instructions](#5-usage-instructions)
6. [Dataset](#6-dataset)
7. [Project Structure](#7-project-structure)
8. [Screenshots & Demo](#8-screenshots--demo)
9. [Contributors](#9-contributors)
10. [Contact Information](#10-contact-information)
11. [Licence](#11-licence)

---

## 1. Project Description

### Problem Statement

Centralised file distribution systems create **single points of failure**. When a central server goes offline, all transfers stop. At scale, bandwidth bottlenecks form as hundreds of clients simultaneously request the same file from one host, driving up infrastructure costs and degrading performance. Most common tools also offer no built-in mechanism to verify the **identity of participants** or the **integrity of transferred files**, leaving networks vulnerable to impersonation, data corruption, and unauthorised submissions.

### Objectives

- Distribute both file storage and transfer load across all participating peer nodes.
- Enable **parallel, concurrent chunk downloads** from multiple peers simultaneously to maximise throughput.
- Provide **automatic, zero-configuration Tracker discovery** across a LAN via signed UDP broadcasts.
- Authenticate all peers with session tokens issued on joining; protect every sensitive endpoint.
- Guarantee chunk integrity at every step using **SHA-256 hashes** verified before reassembly.
- Support **secure, RSA-signed file submissions** from peers to the Tracker with server-side verification.
- Deliver usable **Streamlit dashboards** for both administrators and end-users — no command line required for day-to-day use.

### Target Users

- **Students and educators** — secure assignment submission and course-material distribution without cloud infrastructure.
- **Network architecture learners** — a fully-commented, runnable reference implementation of P2P fundamentals.
- **Small LAN teams** — lightweight file distribution across machines without cloud dependencies or static server provisioning.

### System Overview

The system operates with two distinct roles. A **Tracker (Privileged Peer)** coordinates the network — it chunks uploaded files, maintains a live registry of active peers and their tokens, and tracks which node holds which file chunk. It is **never in the data path** for downloads; it only answers *"who has chunk N?"*

**Peer Nodes** are the actual participants: they store chunks, serve them over HTTP to other peers, download chunks in parallel from multiple sources at once, verify each chunk's SHA-256 hash, then reassemble the complete file locally. Each peer also maintains a **latency-ranked cluster** of its best-performing neighbours, routing chunk requests through the fastest available peers.

---

## 2. System Architecture & Design

### Network Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LAN / Network                               │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │               TRACKER  (Privileged Peer)                    │   │
│   │                                                             │   │
│   │  ┌──────────────────────┐   ┌──────────────────────────┐   │   │
│   │  │  FastAPI HTTP :8000  │   │  Streamlit Admin  :8501  │   │   │
│   │  │  /join  /metadata    │   │  Publish · Peers ·       │   │   │
│   │  │  /peers /heartbeat   │   │  Submissions             │   │   │
│   │  └──────────────────────┘   └──────────────────────────┘   │   │
│   │  ┌──────────────────────┐   ┌──────────────────────────┐   │   │
│   │  │  TCP Server   :8001  │   │  UDP Broadcast    :9999  │   │   │
│   │  │  Assignments ·       │   │  Signed Presence         │   │   │
│   │  │  Metadata · Chunks   │   │  Announcements           │   │   │
│   │  └──────────────────────┘   └──────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────┘   │
│           ▲   /join /metadata /peers /announce_chunk                │
│           │   /files /register_file /heartbeat /admin               │
│           │                                                         │
│   ┌───────┴────────────┐            ┌──────────────────────────┐   │
│   │    PEER NODE  A    │◄──chunks──►│      PEER NODE  B        │   │
│   │                    │  (direct)  │                          │   │
│   │  HTTP    :5000     │            │  HTTP    :5002           │   │
│   │  TCP     :5001     │            │  TCP     :5003           │   │
│   │  Streamlit :8502   │            │  Streamlit :8503         │   │
│   └────────────────────┘            └──────────────────────────┘   │
│                                                                     │
│   ┌────────────────────┐            ┌──────────────────────────┐   │
│   │    PEER NODE  C    │            │      PEER NODE  D        │   │
│   │  HTTP    :5004     │            │  HTTP    :5006           │   │
│   │  TCP     :5005     │            │  TCP     :5007           │   │
│   │  Streamlit :8504   │            │  Streamlit :8505         │   │
│   └────────────────────┘            └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Core Components

#### Tracker (`privileged_peer/`)

| File | Responsibility |
|------|----------------|
| `server.py` | FastAPI application: peer registration, token issuance/validation, chunk location tracking, file registry, heartbeat, peer cleanup after 5 min inactivity |
| `tcp_handler.py` | TCP server (port HTTP+1): receives metadata packets, file chunks, and RSA-signed assignment submissions with full signature verification |
| `chunker.py` | Splits uploaded files into 512 KB chunks; computes SHA-256 per chunk; detects MIME type via extension and magic-byte sniffing |
| `metadata.py` | Persists file metadata (name, extension, MIME, chunk list, hashes) as JSON; loaded into registry on startup |
| `dashboard.py` | Streamlit Admin UI: publish files, browse the registry, distribute to peers, view connected nodes, review verified submissions |

#### Peer Node (`peer_node/`)

| File | Responsibility |
|------|----------------|
| `peer_client.py` | Core client: joins network, stores token, downloads files concurrently (ThreadPoolExecutor), maintains latency cluster, pushes files via TCP, submits signed assignments |
| `peer_server.py` | FastAPI HTTP server (auto-assigned port): serves locally-held chunks to other peers on `GET /chunk/{stem}/{index}` |
| `tcp_handler.py` | TCP server (HTTP port+1): receives pushed metadata and chunks from other peers; saves directly to storage |
| `dashboard.py` | Streamlit Peer UI: browse network library, search, download, distribute files to selected peers, submit assignments, view local library |
| `reassemble.py` | Utility: sorts chunks by index, reads from storage, writes assembled output file |

#### Shared (`shared/`) & Security (`security/`)

| Module | Responsibility |
|--------|----------------|
| `shared/config.py` | Canonical constants (`CHUNK_SIZE`, `DEFAULT_TRACKER_PORT`, `MAX_CLUSTER_SIZE`), all Pydantic models (`PeerInfo`, `FileMetadata`, `ChunkData`, `ChunkLocation`), utility functions |
| `shared/chunker.py` | Shared chunking logic reused by both Tracker and Peer components |
| `shared/metadata.py` | Shared metadata read/write helpers; searches by stem, original name, or glob fallback |
| `security/auth.py` | In-memory token store: issues 32-byte URL-safe tokens on `/join`; validates with constant-time compare; enforces 1-hour TTL; revokes on peer cleanup |
| `security/crypto.py` | RSA-2048 key generation and PEM serialisation; load-or-generate on startup; PSS+SHA256 signing; signature verification |
| `security/hashing.py` | SHA-256 helper wrapping `hashlib`; used for chunk integrity and `peer_id` derivation |

### File Download Data Flow

```
 Peer A wants  report.pdf
       │
  1 ──►│  GET /metadata/report   ──────────────────►  Tracker
       │  ◄── { chunks: [...], hashes: [...] } ────────────────
       │
  2 ──►│  [Parallel — ThreadPoolExecutor(max_workers=8)]
       │
       ├── chunk 0: GET /peers/report/0  ──►  Tracker
       │           ◄── [Peer B, Peer C] ──────────────
       │           Sort by cluster latency
       │           GET http://PeerB:5000/chunk/report/0
       │           Verify SHA-256  ✓
       │           Write  storage/received_chunks/report_chunk_0
       │           POST /announce_chunk  ──►  Tracker  (I now have chunk 0)
       │
       ├── chunk 1: (same flow, different peers — in parallel)
       ├── chunk 2: ...
       └── chunk N: ...
       │
  3 ──►│  Reassemble chunks 0..N in order
       └──►  storage/downloads/report.pdf  ✓  Complete
```

### Security Model

| Mechanism | Details |
|-----------|---------|
| **Session Tokens** | Issued on `/join`; 32-byte URL-safe random; 1-hour TTL; constant-time comparison; required on all `/metadata`, `/peers`, `/announce_chunk`, `/heartbeat` calls |
| **Admin API Key** | Separate 24-byte key auto-generated to `admin_key.txt`; required as `X-Admin-Key` header on `/admin/*` endpoints; loaded from env var or file |
| **RSA-2048 Key Pairs** | Generated per-peer on first run; persisted to `storage/peer_data/{peer_id}/`; public key submitted to Tracker on `/join` |
| **UDP Broadcast Signing** | Tracker signs each presence broadcast with its private key; peers verify on receipt; Trust-On-First-Use (TOFU) on very first broadcast; key cached thereafter |
| **Assignment Verification** | Submitting peer signs file bytes with PSS+SHA256; Tracker retrieves peer's registered public key and verifies before writing — tampered files are silently dropped |
| **Chunk Integrity** | Every downloaded chunk is SHA-256 verified against the hash in metadata; corrupted or malicious chunks are discarded and retried |
| **Peer Cleanup** | Background asyncio task removes peers unseen for 5 minutes; their tokens are revoked, preventing stale credentials |
| **Path Sanitisation** | `sanitize_stem()` strips path components and non-word characters from all `file_stem` values received from the network before any filesystem access |

---

## 3. Technologies Used

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| Language | Python | 3.9+ | All backend services, TCP/UDP networking, crypto, chunking |
| HTTP Framework | FastAPI | Latest | Async REST API for Tracker and Peer HTTP servers |
| ASGI Server | Uvicorn | Latest | Production ASGI runner for all FastAPI instances |
| UI Framework | Streamlit | Latest | Admin Console and Peer Node interactive dashboards |
| Cryptography | `cryptography` | Latest | RSA-2048 key generation, PSS signing, signature verification |
| Data Validation | Pydantic | v2 | Request/response models; strict type validation across all nodes |
| HTTP Client | `requests` | Latest | All outbound HTTP calls from peers to Tracker and other peers |
| Parallelism | `concurrent.futures` | stdlib | `ThreadPoolExecutor` for parallel chunk downloads |
| Networking | `socket` | stdlib | Custom TCP binary protocol and UDP broadcast discovery |
| Hashing | `hashlib` | stdlib | SHA-256 chunk integrity verification and `peer_id` derivation |
| Launcher | `tkinter` | stdlib | Desktop one-click launcher GUI |
| Packaging | uv / pip | Latest | Virtual environment creation and dependency installation |

---

## 4. Installation Instructions

### Requirements

- Python 3.9 or higher
- pip (bundled with Python 3.4+)
- Network access between machines if running across multiple hosts

### Option A — Windows (Fully Automated)

Double-click or run in a terminal:

```batch
run_app.bat
```

This script automatically: installs the `uv` package manager if absent, creates a `.venv` virtual environment, installs all dependencies from `requirements.txt`, and launches the Tkinter GUI launcher.

### Option B — Manual (All Platforms)

**1. Clone the repository**

```bash
git clone https://github.com/[your-username]/p2p-file-sharing-network.git
cd p2p-file-sharing-network
```

**2. Create and activate a virtual environment**

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

**3. Install dependencies**

```bash
pip install -r requirements.txt

# or manually:
pip install fastapi uvicorn pydantic requests streamlit cryptography
```

### How to Run

See [Usage Instructions](#5-usage-instructions) below. The network requires the **Tracker to be started before any Peer Node** attempts to join.

---

## 5. Usage Instructions

### Step 1 — Start the Tracker

Open **two** terminals:

```bash
# Terminal 1 — Tracker backend
python privileged_peer/server.py
# Starts HTTP API on :8000 and TCP server on :8001
# Begins signed UDP broadcasts every 5 seconds on :9999
```

```bash
# Terminal 2 — Admin Dashboard
streamlit run privileged_peer/dashboard.py --server.port 8501
# Open http://localhost:8501 in your browser
```

> **Security note:** An admin API key is auto-generated and saved to `admin_key.txt` in the project root. Both dashboards load this automatically. When deploying across multiple machines, copy `admin_key.txt` to the root folder of each machine.

### Step 2 — Start Peer Nodes

Open a **new terminal** for each peer. Peers on the same LAN discover the Tracker automatically via UDP.

```bash
# First peer
streamlit run peer_node/dashboard.py --server.port 8502

# Second peer (new terminal)
streamlit run peer_node/dashboard.py --server.port 8503

# Third peer (new terminal — or on a different machine on the same LAN)
streamlit run peer_node/dashboard.py --server.port 8504
```

### Step 3 — Publish a File (Admin)

1. Open the Admin Dashboard at `http://localhost:8501`
2. Navigate to **Publish New File**
3. Upload any file (PDF, DOCX, ZIP, JPG, PNG, MP4, etc.)
4. The Tracker chunks the file into 512 KB pieces, computes SHA-256 hashes, registers it in the network library, and makes it immediately downloadable by all peers.

### Step 4 — Download a File (Peer)

1. Open any Peer Dashboard (e.g. `http://localhost:8502`)
2. Under **Network Library**, click **Refresh Library** to see all registered files
3. Click the **Download** button next to any file
4. The peer fetches chunk locations from the Tracker, downloads all chunks in parallel from the fastest available peers, verifies each hash, then reassembles the complete file to `storage/downloads/`

### Step 5 — Submit an Assignment (Peer)

1. Open a Peer Dashboard
2. Expand the **Assignment Submission** section
3. Upload your file and click **Sign & Submit**
4. The peer signs the file bytes with its RSA private key and sends the payload over TCP to the Tracker
5. The Tracker verifies the signature using the peer's registered public key — only verified files are saved
6. View all received and verified submissions in the Admin Dashboard under **Submissions**

### Step 6 — Distribute a File to Specific Peers

1. In either dashboard, find the file in the library
2. Expand the **Distribute** section and select one or more target peers
3. Click **Send / Start Transfer** — the system pushes metadata and all chunks via TCP directly to the selected peers

### Example Inputs and Outputs

| Action | Input | Output / Result |
|--------|-------|-----------------|
| Publish file | Upload `report.pdf` (2 MB) via Admin Dashboard | 4 chunks in `storage/chunks/` · file registered in network library |
| Download file | Click Download on `report.pdf` in Peer Dashboard | `storage/downloads/report.pdf` — reassembled from up to 4 parallel sources |
| Submit assignment | Upload `assignment.docx`, click Sign & Submit | Saved to `storage/assignments/{peer_id}/assignment.docx` after RSA verification |
| Distribute to peer | Select target peer, click Start Transfer | Metadata + all chunks pushed via TCP to target · target can immediately serve the file |
| Automatic discovery | Start a new Peer Node on the same LAN | Peer auto-discovers Tracker via UDP within 5 seconds; joins without manual IP config |
| Cluster update | Background thread runs every 15 seconds | Top-N lowest-latency peers stored in cluster dict; used to prioritise chunk requests |

---

## 6. Dataset

This project does not use a fixed or pre-existing dataset. It operates on **arbitrary user-supplied files of any binary type**. File type detection is handled automatically:

- **Extension-based detection** — via Python's `mimetypes` module
- **Magic-byte detection** — fallback inspection of the first 16 bytes for PDF (`%PDF`), PNG (`\x89PNG`), JPEG (`\xFF\xD8\xFF`), GIF (`GIF8`), ZIP (`PK\x03\x04`), and RAR (`Rar!`) signatures
- **Default fallback** — `application/octet-stream` for unrecognised types

The Streamlit Admin Dashboard explicitly accepts: `pdf`, `docx`, `txt`, `zip`, `jpg`, `png`, `mp4`. Peer-to-peer TCP transfers and manual downloads accept any file type.

---

## 7. Project Structure

```
p2p-file-sharing-network/
│
├── privileged_peer/             # Tracker / Privileged Node
│   ├── server.py                #   FastAPI backend (auth, registry, heartbeat)
│   ├── dashboard.py             #   Streamlit Admin UI
│   ├── chunker.py               #   File → chunk splitting with MIME detection
│   ├── metadata.py              #   JSON metadata persistence
│   ├── tcp_handler.py           #   TCP server (assignments, metadata, chunks)
│   └── config.py                #   Local constants (legacy shim)
│
├── peer_node/                   # Client Peer Node
│   ├── peer_client.py           #   Core P2P logic: join, download, cluster, push
│   ├── peer_server.py           #   FastAPI HTTP chunk-serving endpoint
│   ├── dashboard.py             #   Streamlit Peer UI
│   ├── tcp_handler.py           #   TCP server (incoming pushes)
│   ├── metadata.py              #   Local metadata helpers
│   ├── reassemble.py            #   Chunk reassembly utility
│   └── config.py                #   Local constants (legacy shim)
│
├── shared/                      # Shared across all components
│   ├── __init__.py              #   Package-level exports
│   ├── config.py                #   Canonical constants + Pydantic models
│   ├── chunker.py               #   Shared chunking logic
│   └── metadata.py              #   Shared metadata read/write helpers
│
├── security/                    # Security primitives
│   ├── __init__.py
│   ├── auth.py                  #   Token issuance & validation (TTL-based)
│   ├── crypto.py                #   RSA-2048 keygen, PSS signing, verification
│   └── hashing.py               #   SHA-256 helper
│
├── network/                     # Network utilities
│   ├── __init__.py
│   └── discovery.py             #   UDP peer announcement helper
│
├── storage/                     # Auto-generated at runtime (gitignored)
│   ├── chunks/                  #   Tracker-held original file chunks
│   ├── received_chunks/         #   Peer-downloaded chunks (pre-reassembly)
│   ├── downloads/               #   Final reassembled files
│   ├── metadata/                #   JSON metadata per registered file
│   ├── assignments/             #   RSA-verified peer submissions
│   └── peer_data/               #   Per-peer RSA key pairs
│
├── launcher.py                  # Tkinter one-click desktop launcher
├── run_app.bat                  # Windows: automated venv setup + launch
├── requirements.txt             # Python dependencies
├── admin_key.txt                # Auto-generated admin API key (gitignored)
└── README.md                    # This file
```

---

## 8. Screenshots & Demo

> 📹 **Demo Video:** `[Insert link — YouTube / Google Drive / institution host]`

| Screenshot | Description |
|-----------|-------------|
| ![Screenshot](images/Admin Dashboard — Publish New File) | File upload widget, chunk count display, MIME detection result, registry list with search and Remove buttons |
| ![Screenshot](images/Admin Dashboard — Connected Peers) | Live table of active peer nodes showing `peer_id`, `host:port`, and online status |
| ![Screenshot](images/Admin Dashboard — Submissions) | Per-peer expandable sections listing verified assignment files with RSA verification badge and Download button |
| ![Screenshot](images/Peer Dashboard — Network Library) | Searchable grid of available files with Download and Distribute expanders |
| ![Screenshot](images/Peer Dashboard — Download in Progress) | `st.status` widget showing chunk fetch progress, hash verification steps, and completion confirmation |
| ![Screenshot](images/Peer Dashboard — Download in Progress) | Latency display for each neighbour peer (green < 50 ms, orange < 200 ms, red otherwise) |
| ![Screenshot](images/Peer Dashboard — My Library) | Local file list showing chunk completeness, Assembled / Incomplete / Chunks Ready states, and Delete action |


---

## 9. Contributors

| Name | Registration No. | Role & Contribution |
|------|-----------------|---------------------|
| S. T Chanditha | 2021/CSC/053 | Tracker server, authentication system, FastAPI endpoints, concurrent download engine, RSA crypto integration |
| B.M.C Bandaranayake | 2021/CSC/098 | Peer client, cluster management |
| R.G.M.S Siriwardana | 2021/CSC/106 | TCP handler, assignment submission |
| K.L.C Dilshan | 2021/CSC/032 | Peer Node Streamlit dashboards, file chunking/reassembly, UDP discovery |
| W.M.S.S Wijesinghe | 2021/CSC/063 | Privileged Streamlit dashboards, file chunking/reassembly, UDP discovery |

---

## 10. Contact Information

| Name | Email | Institution |
|------|-------|-------------|
| S. T Chanditha | thiwankachandithasinhalage@gmail.com | University of Jaffna, Department of Computer Science |
| B.M.C Bandaranayake | smartchinthaka512@gmail.com | University of Jaffna, Department of Computer Science |
| R.G.M.S Siriwardana | malinthassiriwardhana@gmail.com | University of Jaffna, Department of Computer Science |
| K.L.C Dilshan | chamiyadilshanofficial@gmail.com | University of Jaffna, Department of Computer Science |
| W.M.S.S Wijesinghe | sewwandiwijesinghe68@gmail.com | University of Jaffna, Department of Computer Science |

---

## 11. Licence

**MIT Licence**

Copyright (c) 2025 [Team Name / Authors]

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
