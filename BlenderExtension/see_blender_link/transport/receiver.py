import socket
import threading
import select
from ..core.receiver import Receiver
import tempfile
from pathlib import Path
import json
import bpy
import os
import zipfile

_receiver_thread = None
_stop = False
# _blazor_socket = None

MAX_ARCHIVE_SIZE = 1024 * 1024 * 1024  # 1 GiB

def archive_handler(scene_name: str, zip_path: str):
    """Extract a received scene ZIP into its scene-specific cache folder."""
    # Create the cache directory if necessary.
    cache_directory = bpy.context.preferences.addons["bl_ext.user_default.see_sharp_link"].preferences.cache_directory
    os.makedirs(cache_directory, exist_ok=True)

    # Create a folder named after the scene.
    scene_directory = os.path.join(cache_directory, scene_name)
    os.makedirs(scene_directory, exist_ok=True)

    # Extract the ZIP contents into the scene folder.
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(scene_directory)

    print(f"[Receiver] Extracted scene '{scene_name}' to: {scene_directory}")

    json_path = os.path.join(scene_directory, f"{scene_name}.json")
    
    def run():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')    
            
        # clear the current scene
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        # Remove all meshes, materials, images, etc.
        for block in bpy.data.meshes:
            bpy.data.meshes.remove(block)
        for block in bpy.data.materials:
            bpy.data.materials.remove(block)
        for block in bpy.data.textures:
            bpy.data.textures.remove(block)
        for block in bpy.data.images:
            bpy.data.images.remove(block)
        
        scene_collection = bpy.context.scene.collection
        for col in list(bpy.data.collections):
            if col != scene_collection:
                bpy.data.collections.remove(col)

        if os.path.exists(json_path):
            print(f"Importing scene from json: {json_path}")
            bpy.ops.import_scene.seesharp(filepath=json_path)
            return None
    bpy.app.timers.register(run, first_interval=0)

def _handle_connection(conn, receiver):
    # Keep unread bytes here. They may contain the beginning
    # of a ZIP immediately after its JSON header.
    buffer = bytearray()

    while not _stop:
        # Read only when we don't already have a complete line.
        newline = buffer.find(b"\n")

        while newline < 0:
            if len(buffer) > 1024 * 1024:
                raise ValueError("JSON header too large")

            chunk = conn.recv(64 * 1024)

            if not chunk:
                return

            buffer.extend(chunk)
            newline = buffer.find(b"\n")

        # Extract one newline-terminated JSON message.
        line = bytes(buffer[:newline])
        del buffer[:newline + 1]

        if not line.strip():
            continue

        # Inspect the command before passing it to Receiver.
        try:
            msg = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print("[Receiver] Invalid JSON header")
            continue

        if msg.get("command") != "receive_archive":
            # Existing commands follow exactly the old path.
            receiver.handle_message(line.decode("utf-8"))
            continue

        # Special case: receive a ZIP as raw bytes.
        scene = msg.get("scene")
        size = msg.get("size")

        if not isinstance(scene, str) or not scene:
            raise ValueError("Invalid scene name")

        if scene in (".", "..") or Path(scene).name != scene:
            raise ValueError("Invalid scene name")

        if type(size) is not int or not (0 < size <= MAX_ARCHIVE_SIZE):
            raise ValueError("Invalid archive size")

        print(f"[Receiver] Receiving {scene}.zip ({size} bytes)")

        # Stream the ZIP to disk rather than storing it all in RAM.
        with tempfile.NamedTemporaryFile(
            suffix=".zip", delete=False
        ) as temp:
            zip_path = Path(temp.name)

            try:
                remaining = size

                # First consume bytes already received with the header.
                if buffer and remaining:
                    count = min(len(buffer), remaining)
                    temp.write(buffer[:count])
                    del buffer[:count]
                    remaining -= count

                # Read precisely the remaining ZIP bytes.
                while remaining > 0:
                    chunk = conn.recv(min(1024 * 1024, remaining))

                    if not chunk:
                        raise ConnectionError(
                            "Connection closed during archive transfer"
                        )

                    temp.write(chunk)
                    remaining -= len(chunk)

            except Exception:
                zip_path.unlink(missing_ok=True)
                raise

        try:
            print(f"[Receiver] Archive received: {zip_path}")

            # if archive_handler is None:
            #     print(
            #         "[Receiver] No archive handler configured; "
            #         "ZIP saved but not imported."
            #     )
            # else:
                # The handler must finish using the ZIP before returning.
            archive_handler(scene, zip_path)

        finally:
            zip_path.unlink(missing_ok=True)

def _receiver_loop(receiver):
    global _stop

    from .sender import set_socket, clear_socket

    while not _stop:
        sock = None

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)

            HOST = bpy.context.preferences.addons["bl_ext.user_default.see_sharp_link"].preferences.server_host
            PORT_OUT = bpy.context.preferences.addons["bl_ext.user_default.see_sharp_link"].preferences.server_port

            print(f"[Blender] Connecting to Blazor at {HOST}:{PORT_OUT}...")
            sock.connect((HOST, PORT_OUT))

            # Connection established
            sock.settimeout(120)
            set_socket(sock)

            print("[Blender] Connected to Blazor")

            # Receive commands and archives using the same socket
            _handle_connection(sock, receiver)

        except Exception as e:
            if not _stop:
                print("[Blender] Connection error:", e)

        finally:
            if sock is not None:
                clear_socket(sock)
                try:
                    sock.close()
                except Exception:
                    pass

            if not _stop:
                print("[Blender] Reconnecting in 3 seconds...")
                threading.Event().wait(3)

def start(receiver: Receiver):
    global _receiver_thread, _stop
    if _receiver_thread and _receiver_thread.is_alive():
        return
    _stop = False
    _receiver_thread = threading.Thread(target=_receiver_loop, args=(receiver,) ,daemon=True)
    _receiver_thread.start()


def stop():
    global _stop
    _stop = True

    from .sender import _blazor_socket

    if _blazor_socket:
        try:
            _blazor_socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass