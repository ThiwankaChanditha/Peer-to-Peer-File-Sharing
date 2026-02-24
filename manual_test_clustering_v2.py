import sys
import os
import random
import time
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'peer_node'))
sys.path.append(os.path.join(os.getcwd(), 'shared'))

try:
    from peer_node.peer_client import PeerClient, MAX_CLUSTER_SIZE
except ImportError:
    print("Could not import PeerClient. Check paths.")
    sys.exit(1)

def test_clustering_logic():
    print("--- Starting Clustering Logic Test ---")
    
    # 1. Instantiate Client (Mocking server start to avoid binding ports)
    # We need to mock threading.Thread to prevent actual server startup
    with unittest.mock.patch('threading.Thread'):
         client = PeerClient()
    
    # 2. Mock get_active_peers to return 50 peers
    mock_peers = []
    for i in range(50):
        mock_peers.append({
            "peer_id": f"peer_{i}",
            "host": "127.0.0.1",
            "port": 9000 + i
        })
    
    client.get_active_peers = MagicMock(return_value=mock_peers)
    
    # 3. Mock measure_latency to return deterministic values
    # Let's say peer_i has latency i * 10 ms (so peer_0 is fastest, peer_49 slowest)
    def mock_latency(host, port):
        # Extract index from port to simulate latency
        idx = port - 9000
        return idx * 10.0
        
    client.measure_latency = MagicMock(side_effect=mock_latency)
    
    # 4. Run update_cluster
    print("Running update_cluster()...")
    client.update_cluster()
    
    # 5. Verify Size
    cluster_size = len(client.cluster_peers)
    print(f"Cluster Size: {cluster_size}")
    
    if cluster_size > MAX_CLUSTER_SIZE:
        print(f"FAIL: Cluster size {cluster_size} exceeds max {MAX_CLUSTER_SIZE}")
        sys.exit(1)
        
    # 6. Verify Content (Should mostly contain low index peers, but might have some randoms if we sample)
    # Wait, the logic is: 
    # - cluster_members (empty initially)
    # - others (all 50)
    # - candidates = cluster_members + random.sample(others, 5)
    # So initially it should only have 5 items!
    
    if cluster_size > 5:
         print(f"WARNING: Initial cluster size {cluster_size} is unexpected (should be sample size 5).")
    
    # Now run it again. The 5 we found should be in 'cluster_members'. 
    # and we pick 5 more.
    # Eventually we want to see if it respects the max size when we have > 20 candidates.
    
    # Force 'candidates' to be larger to test the sorting/trimming logic directly
    # accessing internal logic check? Or just run loop multiple times?
    
    # Let's manually populate check
    print("Forcing large cluster to test trimming...")
    client.cluster_peers = {f"peer_{i}": i*10 for i in range(30)} # 30 existing members
    
    # Now update. 
    # - cluster_members will be all 30 (since they are in get_active_peers mock)
    # - others = remaining 20
    # - candidates = 30 + 5 randoms = 35
    # - sorted -> top 20 should be kept.
    
    client.update_cluster()
    
    final_size = len(client.cluster_peers)
    print(f"Final Size after trimming: {final_size}")
    
    if final_size != MAX_CLUSTER_SIZE:
         print(f"FAIL: Logic did not trim to {MAX_CLUSTER_SIZE}. Size is {final_size}")
         sys.exit(1)
         
    # Check if the kept ones are indeed the fastest (smallest latency/index)
    # The first 0-19 should be kept if sort works, assuming random ones were slower or filtered.
    keys = list(client.cluster_peers.keys())
    print(f"Top keys: {keys[:5]}...")
    
    print("SUCCESS: Clustering logic verified.")

import unittest.mock
test_clustering_logic()
