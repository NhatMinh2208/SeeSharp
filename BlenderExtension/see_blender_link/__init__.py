from .addons import path_viewer, cursor_tracker
from . import preferences, scene_saver
modules = (preferences, path_viewer, cursor_tracker, scene_saver)

def register():
    for m in modules:
        m.register()

def unregister():
    for m in reversed(modules):
        m.unregister()