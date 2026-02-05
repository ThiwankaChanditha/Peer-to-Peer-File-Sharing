
import socket
import threading
import time
import json
import sys

def listener():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        udp.bind(("", 9999))
        print("[LISTENER] Listening on 0.0.0.0:9999")
    except Exception as e:
        print(f"[LISTENER] Failed to bind: {e}")
        return

    udp.settimeout(10)
    start = time.time()
    
    while time.time() - start < 15:
        try:
            data, addr = udp.recvfrom(1024)
            print(f"[LISTENER] Received from {addr}: {data.decode()}")
        except socket.timeout:
            pass
        except Exception as e:
            print(f"[LISTENER] Error: {e}")
            break
    
    udp.close()
    print("[LISTENER] Stopped.")

def broadcaster():
    time.sleep(1)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    msg = json.dumps({"test": "hello"}).encode()
    
    print("[BROADCASTER] Sending to <broadcast>...")
    try:
        udp.sendto(msg, ('<broadcast>', 9999))
        print("[BROADCASTER] Sent 1.")
    except Exception as e:
        print(f"[BROADCASTER] Error sending to <broadcast>: {e}")

    # Try 255.255.255.255 explicitly
    print("[BROADCASTER] Sending to 255.255.255.255...")
    try:
        udp.sendto(msg, ('255.255.255.255', 9999))
        print("[BROADCASTER] Sent 2.")
    except Exception as e:
        print(f"[BROADCASTER] Error sending to 255.255.255.255: {e}")
        
    udp.close()

if __name__ == "__main__":
    t = threading.Thread(target=listener)
    t.start()
    
    broadcaster()
    t.join()
