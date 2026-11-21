import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty, IntProperty
from pathlib import Path

def get_default_cache_directory() -> Path:
    config_dir = bpy.utils.user_resource("CONFIG")
    if config_dir is None:
        raise RuntimeError("Cannot determine Blender's configuration directory")

    return Path(config_dir) / "SeeSharp" / "cache"

class SeeSharpPreferences(AddonPreferences):
    bl_idname = __package__

    cache_directory: StringProperty(
        name="Scene Cache Directory",
        description="Directory used to cache downloaded SeeSharp scene assets",
        subtype="DIR_PATH",
        default=str(get_default_cache_directory()),
    )

    server_host: StringProperty(
        name="Server IP",
        description="IP address of the SeeSharp Blazor server",
        default="127.0.0.1"
    )

    server_port: IntProperty(
        name="Server Port",
        description="TCP port of the SeeSharp server",
        default=5052,
        min=1,
        max=65535
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "cache_directory")
        layout.prop(self, "server_host")
        layout.prop(self, "server_port")

def register():
    bpy.utils.register_class(SeeSharpPreferences)


def unregister():
    bpy.utils.unregister_class(SeeSharpPreferences)