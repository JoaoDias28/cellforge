"""Isaac Sim 6/OpenUSD Task 016 placement probe executed through Kit ``--exec``."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import UUID

import omni.kit.app
from pxr import Usd

from cellforge.studio.component_service import ComponentPlacementService
from cellforge.studio.project_service import ProjectCommandService

root = Path.cwd().resolve()
with tempfile.TemporaryDirectory(prefix="cellforge-task016-kit-", dir=root) as directory:
    project = Path(directory) / "pen-project"
    shutil.copytree(root / "examples" / "pen_engraving", project)
    shutil.copytree(root / "schemas", project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    components = ComponentPlacementService(
        root / "schemas",
        new_uuid=lambda: UUID("12345678-1234-5678-1234-567812345678"),
    )
    backend = ProjectCommandService(root / "schemas", component_service=components)
    opened = backend.inspect(project)
    if opened.contents is None:
        raise RuntimeError("Kit Task 016 probe could not open the reference project")
    placed = backend.place_component(
        project,
        opened.contents,
        component="generic.pen_fixture.reference",
        version="0.1.0",
        alias="kit_probe_fixture",
        variants={},
    )
    if placed.contents is None or placed.instance_id is None:
        raise RuntimeError("Kit Task 016 probe placement was rejected")
    saved = backend.save(project, placed.contents)
    if saved.project is None:
        raise RuntimeError("Kit Task 016 probe save failed")
    stage = Usd.Stage.Open(str(project / "scene.usda"))
    if stage is None:
        raise RuntimeError("OpenUSD could not compose the saved Task 016 stage")
    matching = [
        prim
        for prim in stage.Traverse()
        if prim.HasAttribute("cellforge:instanceId")
        and prim.GetAttribute("cellforge:instanceId").Get() == placed.instance_id
    ]
    if len(matching) != 1:
        raise RuntimeError("OpenUSD did not compose exactly one placed component instance")

print("Verified Task 016 linked placement through Isaac Sim 6/OpenUSD.")
omni.kit.app.get_app().post_quit(0)
