"""Isaac Sim 6 lifecycle probe executed inside Kit via ``--exec``."""

import omni.kit.app
import omni.ui as ui

EXTENSION_ID = "cellforge.studio"
WINDOWS = ("CellForge Project", "CellForge Validation", "CellForge Log")

app = omni.kit.app.get_app()
manager = app.get_extension_manager()

if not manager.is_extension_enabled(EXTENSION_ID):
    raise RuntimeError(f"{EXTENSION_ID} was not enabled")
for title in WINDOWS:
    if ui.Workspace.get_window(title) is None:
        raise RuntimeError(f"missing Cell Studio window: {title}")

manager.set_extension_enabled_immediate(EXTENSION_ID, False)
if manager.is_extension_enabled(EXTENSION_ID):
    raise RuntimeError(f"{EXTENSION_ID} did not unload")

print("Cell Studio extension loaded, created all panels, and unloaded cleanly.")
app.post_quit(0)
