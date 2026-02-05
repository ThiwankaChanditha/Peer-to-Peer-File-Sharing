import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os
import sys
import threading

class P2PLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P Network Launcher")
        self.root.geometry("400x350")
        self.root.resizable(False, False)
        
        # Style
        style = ttk.Style()
        style.configure("TButton", font=("Helvetica", 12), padding=10)
        style.configure("Title.TLabel", font=("Helvetica", 16, "bold"))
        
        # Title
        title = ttk.Label(root, text="P2P File Sharing System", style="Title.TLabel")
        title.pack(pady=20)
        
        # Instructions
        desc = ttk.Label(root, text="Select a component to launch:", font=("Helvetica", 10))
        desc.pack(pady=5)
        
        # Buttons
        self.btn_admin = ttk.Button(root, text="🚀 Launch Admin Console\n(Privileged Node & Tracker)", command=self.launch_admin)
        self.btn_admin.pack(pady=15, fill="x", padx=40)
        
        self.btn_peer = ttk.Button(root, text="👤 Launch Peer Node\n(File Sharing Hub)", command=self.launch_peer)
        self.btn_peer.pack(pady=15, fill="x", padx=40)
        
        # Status
        self.status = ttk.Label(root, text="Ready", foreground="gray")
        self.status.pack(side="bottom", pady=10)
        
        # Setup Env
        self.cwd = os.path.dirname(os.path.abspath(__file__))

    def run_streamlit(self, script_path, title):
        try:
            # Check if file exists
            if not os.path.exists(os.path.join(self.cwd, script_path)):
                messagebox.showerror("Error", f"File not found: {script_path}")
                return

            # Use sys.executable (which points to .venv python if started from batch)
            python_exe = sys.executable
            
            # Use cmd /k to keep the window open so we can see errors
            if os.name == 'nt':
                cmd = ["cmd", "/k", python_exe, "-m", "streamlit", "run", script_path]
                subprocess.Popen(cmd, cwd=self.cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                cmd = [python_exe, "-m", "streamlit", "run", script_path]
                subprocess.Popen(cmd, cwd=self.cwd)
                
            self.status.config(text=f"Launched {title}...")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch: {e}")

    def launch_admin(self):
        # Start the Tracker Server (FastAPI) in a separate process
        try:
            server_script = os.path.join(self.cwd, "privileged_peer", "server.py")
            if os.path.exists(server_script):
                python_exe = sys.executable
                if os.name == 'nt':
                    cmd = ["cmd", "/k", python_exe, server_script]
                    subprocess.Popen(cmd, cwd=self.cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    cmd = [python_exe, server_script]
                    subprocess.Popen(cmd, cwd=self.cwd)
                self.status.config(text="Started Tracker Server...")
            else:
                messagebox.showerror("Error", f"Server script not found: {server_script}")
        except Exception as e:
             messagebox.showerror("Error", f"Failed to start server: {e}")

        # Start the Dashboard
        self.run_streamlit("privileged_peer/dashboard.py", "Admin Node")

    def launch_peer(self):
        self.run_streamlit("peer_node/dashboard.py", "Peer Node")

if __name__ == "__main__":
    root = tk.Tk()
    app = P2PLauncher(root)
    root.mainloop()