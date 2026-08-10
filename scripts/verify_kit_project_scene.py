"""Isaac Sim 6 Task 015 project/scene acceptance probe executed through Kit ``--exec``."""

from pathlib import Path

import omni.kit.app
from pxr import Usd

from cellforge.studio.backend import create_default_application

root = Path.cwd().resolve()
project = root / "examples" / "pen_engraving"
application = create_default_application()
snapshot = application.open_project(project)
if snapshot.project is None or snapshot.validation:
    raise RuntimeError("Cell Studio could not open the canonical pen project")

stage = Usd.Stage.Open(str(project / snapshot.project.scene))
if stage is None:
    raise RuntimeError("OpenUSD could not open the canonical pen scene")
scene_ids = {
    prim.GetAttribute("cellforge:instanceId").Get()
    for prim in stage.Traverse()
    if prim.HasAttribute("cellforge:instanceId")
}
if len(scene_ids) != snapshot.project.component_count:
    raise RuntimeError("OpenUSD instance IDs do not match the operational component count")

print("Cell Studio opened and linked the pen project through the Isaac Sim 6 OpenUSD runtime.")
omni.kit.app.get_app().post_quit(0)
