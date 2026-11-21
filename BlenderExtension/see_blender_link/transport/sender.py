import socket
import json
import threading

_blazor_socket = None
_socket_lock = threading.Lock()

def set_socket(sock):
    """Called by the listener when a connection is established."""
    global _blazor_socket
    _blazor_socket = sock


def clear_socket(sock):
    """Called by the listener when the connection is closed."""
    global _blazor_socket
    if _blazor_socket is sock:
        _blazor_socket = None

def send_to_blazor(data: dict):
    if _blazor_socket is None:
        print("[Blender->Blazor] Not connected")
        return

    try:
        msg = json.dumps(data) + "\n"
        with _socket_lock:
            _blazor_socket.sendall(msg.encode("utf8"))
    except Exception as e:
        print("[Blender->Blazor] Send failed:", e)
