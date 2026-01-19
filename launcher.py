import subprocess
import sys
import os

def run_component(module_path):
    """
    Runs a Python module using the current virtual environment 
    and the -m flag to resolve all internal paths correctly.
    """
    print(f"\n>>> Starting: {module_path}")
    try:
        # sys.executable ensures it uses your active 'venv'
        subprocess.run([sys.executable, "-m", module_path])
    except KeyboardInterrupt:
        print(f"\n>>> Stopped: {module_path}")

if __name__ == "__main__":
    print("--- P2P System Launcher ---")
    print("1) Run Privileged Peer (Tracker/Server)")
    print("2) Run Peer Client")
    print("3) Run Peer Server")
    
    choice = input("\nSelect a component to start (1-3): ")
    
    if choice == "1":
        run_component("privileged_peer.server")
    elif choice == "2":
        run_component("peer_node.peer_client")
    elif choice == "3":
        run_component("peer_node.peer_server")
    else:
        print("Invalid selection.")