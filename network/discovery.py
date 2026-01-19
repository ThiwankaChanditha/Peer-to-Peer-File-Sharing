import socket

def announce_peer(peer_id):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(peer_id.encode(), ("<broadcast>", 9999))
