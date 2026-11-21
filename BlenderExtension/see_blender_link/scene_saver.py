import bpy
import json
import hashlib
from pathlib import Path
import tempfile
import os
import zipfile
import socket
from datetime import datetime, timezone
import shutil
from .config import HOST, PORT_OUT

CHUNK_SIZE = 1024 * 1024  # 1 MiB
MANIFEST_NAME = "manifest.json"

import time

def timed_call(name, func, *args, **kwargs):
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start

    print(f"[Timing] {name}: {elapsed:.4f} seconds")

    return result

def calculate_manifest(scene_dir: Path) -> dict:
    """Calculate hashes and sizes of all files in the scene folder."""

    assets = []

    for file_path in sorted(scene_dir.rglob("*")):
        if not file_path.is_file():
            continue

        # Ignore the manifest itself and temporary files.
        if file_path.name == MANIFEST_NAME:
            continue
        if file_path.name.endswith(".tmp"):
            continue

        relative_path = file_path.relative_to(scene_dir).as_posix()

        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha256.update(chunk)

        assets.append({
            "Path": relative_path,
            "Sha256": sha256.hexdigest(),
            "Size": file_path.stat().st_size,
        })

    return {
        "SceneName": scene_dir.name,
        "GeneratedAt": datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "Assets": assets,
    }

def read_manifest(manifest_path: Path) -> dict | None:
    """Read the previous manifest, if one exists."""

    if not manifest_path.is_file():
        return None

    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read old manifest: {exc}")
        return None

def compare_manifests(old_manifest: dict | None,
                      new_manifest: dict) -> dict:
    """Identify modified, and deleted assets."""

    old_assets = {
        asset["Path"]: asset
        for asset in (old_manifest or {}).get("Assets", [])
    }

    new_assets = {
        asset["Path"]: asset
        for asset in new_manifest["Assets"]
    }

    updated = []

    for path, new_asset in new_assets.items():
        old_asset = old_assets.get(path)

        if old_asset is None or old_asset["Sha256"] != new_asset["Sha256"]:
            updated.append(new_asset)

    # Files present in the old manifest but absent from the new one.
    deleted = sorted(old_assets.keys() - new_assets.keys())

    return {
        "updated": updated,
        "deleted": deleted,
    }

def save_manifest_atomic(manifest_path: Path, manifest: dict):
    """Write the manifest safely after the server confirms the update."""

    temp_path = manifest_path.with_name(MANIFEST_NAME + ".tmp")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    temp_path.replace(manifest_path)

def send_scene_update(request: dict, scene_dir: Path) -> bool:
    """
    Send changed files as a ZIP, together with the JSON update metadata.

    Returns True only when the server confirms the update.
    """
    scene_dir = Path(scene_dir).resolve()
    zip_path = None

    try:
        # Create a temporary ZIP containing only added/modified files.
        with tempfile.NamedTemporaryFile(
            suffix=".zip", delete=False
        ) as temp:
            zip_path = Path(temp.name)

        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for asset in request["updated"]:
                relative_path = Path(asset["Path"])

                file_path = (scene_dir / relative_path).resolve()

                # Prevent paths from escaping the scene directory.
                if not file_path.is_relative_to(scene_dir):
                    raise ValueError(
                        f"Invalid asset path: {asset['Path']}"
                    )

                if not file_path.is_file():
                    raise FileNotFoundError(file_path)

                archive.write(
                    file_path,
                    arcname=relative_path.as_posix()
                )
             # Add the newly generated manifest.
            manifest_path = scene_dir / "manifest.json"

            if not manifest_path.is_file():
                raise FileNotFoundError(
                    f"Manifest not found: {manifest_path}"
                )

            archive.write(
                manifest_path,
                arcname="manifest.json"
            )

        archive_size = zip_path.stat().st_size

        # Reuse the existing event metadata format.
        header = {
            **request,
            "event": "scene_update",
            "archiveSize": archive_size,
        }

        header_bytes = (
            json.dumps(header).encode("utf-8") + b"\n"
        )

        # Use a separate connection; don't interfere with the
        # persistent socket used by send_to_blazor().
        with socket.create_connection(
            (HOST, PORT_OUT), timeout=30
        ) as sock:
            sock.settimeout(120)

            # 1. Send JSON header.
            sock.sendall(header_bytes)

            # 2. Send exactly archive_size bytes.
            with zip_path.open("rb") as archive_file:
                while True:
                    chunk = archive_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)

            # 3. Wait for the server's JSON acknowledgement.
            response_file = sock.makefile("rb")
            response_line = response_file.readline()

            if not response_line:
                print("[Blender->Blazor] No server confirmation")
                return False

            response = json.loads(response_line.decode("utf-8"))

            if (
                response.get("event") == "archive_received"
                and response.get("success") is True
            ):
                print("[Blender->Blazor] Scene update confirmed")
                return True

            print("[Blender->Blazor] Scene update rejected:", response)
            return False

    except Exception as e:
        print("[Blender->Blazor] ZIP transfer failed:", e)
        return False

    finally:
        if zip_path is not None:
            zip_path.unlink(missing_ok=True)

def update_local_cache(
    temp_dir: Path,
    cache_dir: Path,
    changes: dict,
    new_manifest: dict
):
    """Apply successfully synchronized changes to the local cache."""

    temp_dir = temp_dir.resolve()
    cache_dir = cache_dir.resolve()

    cache_dir.mkdir(parents=True, exist_ok=True)

    # Copy added and modified files.
    for asset in changes["updated"]:
        relative_path = Path(asset["Path"])

        source = (temp_dir / relative_path).resolve()
        destination = (cache_dir / relative_path).resolve()

        if not source.is_relative_to(temp_dir):
            raise ValueError(f"Invalid source path: {relative_path}")

        if not destination.is_relative_to(cache_dir):
            raise ValueError(f"Invalid destination path: {relative_path}")

        destination.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(source, destination)

    # # Remove deleted files.
    # for relative_path in changes["deleted"]:
    #     destination = (cache_dir / relative_path).resolve()

    #     if not destination.is_relative_to(cache_dir):
    #         raise ValueError(f"Invalid deleted path: {relative_path}")

    #     if destination.is_file():
    #         destination.unlink()

    # Save the new manifest after applying file changes.
    save_manifest_atomic(
        cache_dir / MANIFEST_NAME,
        new_manifest
    )

class SEE_SHARP_OT_save_scene(bpy.types.Operator):
    bl_idname = "see_sharp.save_scene"
    bl_label = "Save Scene"
    bl_description = "Save and update the current scene"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Do you want to save and update this scene?")
        layout.label(
            text="If a copy exists in remote storage, it will also be updated."
        )
    
    def execute(self, context):
        cache_dir = bpy.context.preferences.addons["bl_ext.user_default.see_sharp_link"].preferences.cache_directory
        temp_dir = tempfile.mkdtemp(prefix="blender_export_")
        # Save the scene on the temp folder
        loaded_scene_name = bpy.context.window_manager.seesharp_scene_name
        temp_dir = os.path.join(temp_dir, loaded_scene_name)
        filepath = os.path.join(temp_dir, f"{loaded_scene_name}.json")
       
        result = timed_call(
            "Export scene",
            bpy.ops.export.to_seesharp,
            'EXEC_DEFAULT',
            filepath=filepath,
            animations=False,
        )

        # Calculate the manifest of the new scene
        new_manifest = timed_call(
            "Calculate manifest",
            calculate_manifest,
            Path(temp_dir)
        )

        temp_manifest_path = Path(temp_dir) / "manifest.json"
        with temp_manifest_path.open("w", encoding="utf-8") as f:
            json.dump(new_manifest, f, indent=2, ensure_ascii=False)

        # Get the old manifest.json from the same folder
        old_manifest = timed_call(
            "Read old manifest",
            read_manifest,
            Path(os.path.join(cache_dir, loaded_scene_name)) / MANIFEST_NAME
        )
        # Figure which file is being modified and add to the request list
        changes = timed_call(
            "Compare manifests",
            compare_manifests,
            old_manifest,
            new_manifest
        )
       
        # Send the request list to server to update the scene
        if not changes["updated"] and not changes["deleted"]:
            print(f"Scene '{loaded_scene_name}' has no changes.")
        else:
            print("Files being changed: ")
            for change in changes["updated"]:
                print(change)
        # Receive a confirmation from the server after the scene being modified successfully
        changes["sceneName"] = loaded_scene_name
        confirmed = timed_call(
            "Send scene update (including server confirmation)",
            send_scene_update,
            changes,
            Path(temp_dir)
        )
        if confirmed is True:
            timed_call(
                "Update local cache",
                update_local_cache,
                Path(temp_dir),
                Path(os.path.join(cache_dir, loaded_scene_name)),
                changes,
                new_manifest
            )
            print("Remote scene update confirmed; local manifest updated.")
        else:
            print("Remote update not confirmed; old manifest preserved.")

        if 'CANCELLED' in result:
            return {'CANCELLED'}

        self.report({'INFO'}, "Scene saved successfully.")
        return {'FINISHED'}

class SeeSharpSavePanel(bpy.types.Panel):
    bl_label = "Update Scene"
    bl_idname = "SEESHARP_PT_save_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SeeSharp'

    def draw(self, context):
        layout = self.layout

        layout.operator(
            "see_sharp.save_scene",
            text="Save",
            icon='FILE_TICK',
        )

def register():
    bpy.utils.register_class(SEE_SHARP_OT_save_scene)
    bpy.utils.register_class(SeeSharpSavePanel)

def unregister():
    bpy.utils.unregister_class(SeeSharpSavePanel)
    bpy.utils.unregister_class(SEE_SHARP_OT_save_scene)
  