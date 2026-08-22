"""Isaac Sim 6/OpenUSD Task 042 visual-connection probe run through Kit ``--exec``."""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

import omni.kit.app
import yaml
from pxr import Usd

from cellforge.studio.application import ProjectContents
from cellforge.studio.project_service import ProjectCommandService


def _quit_on_script_error(exc_type, exc_value, exc_traceback) -> None:
    """Ensure a failed ``--exec`` probe cannot leave Kit running indefinitely."""

    traceback.print_exception(exc_type, exc_value, exc_traceback)
    omni.kit.app.get_app().post_quit(1)


sys.excepthook = _quit_on_script_error

root = Path.cwd().resolve()
with tempfile.TemporaryDirectory(prefix="cellforge-task042-kit-", dir=root) as directory:
    project = Path(directory) / "pen-project"
    shutil.copytree(root / "examples" / "pen_engraving", project)
    shutil.copytree(root / "schemas", project / "schemas")
    cell_path = project / "cell.yaml"
    cell = yaml.safe_load(cell_path.read_text(encoding="utf-8"))
    cell["recipes"][0]["schema"] = "schemas/recipe.schema.json"
    cell["connections"] = [
        item for item in cell["connections"] if item["id"] != "mechanical-robot-gripper"
    ]
    next(item for item in cell["components"] if item["id"] == "gripper-001")["usd_prim"] = (
        "/World/Gripper"
    )
    scene_path = project / "scene.usda"
    scene = scene_path.read_text(encoding="utf-8")
    nested = (
        '        def Xform "Gripper" {\n'
        '            custom string cellforge:instanceId = "gripper-001"\n'
        "        }\n"
    )
    detached = (
        '    def Xform "Gripper" {\n'
        '        custom string cellforge:instanceId = "gripper-001"\n'
        "    }\n"
    )
    scene = scene.replace(nested, "").replace(
        '    def Xform "Laser" {', f'{detached}    def Xform "Laser" {{'
    )
    contents = ProjectContents(cell_yaml=yaml.safe_dump(cell, sort_keys=False), scene_usda=scene)
    backend = ProjectCommandService(root / "schemas")
    preview = backend.PreviewCellConnection(
        project,
        contents,
        kind="mechanical",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
        connection_id="mechanical-task042-kit-probe",
    )
    if preview.preview is None or preview.preview.snapped_target_prim != "/World/Robot/Gripper":
        raise RuntimeError("Kit Task 042 mechanical preview was not coherent")
    staged = backend.StageCellConnection(
        project,
        contents,
        kind="mechanical",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
        connection_id="mechanical-task042-kit-probe",
    )
    if staged.contents is None:
        raise RuntimeError("Kit Task 042 mechanical staging was rejected")
    cell_path.write_text(staged.contents.cell_yaml, encoding="utf-8", newline="\n")
    scene_path.write_text(staged.contents.scene_usda, encoding="utf-8", newline="\n")
    stage = Usd.Stage.Open(str(scene_path))
    if stage is None:
        raise RuntimeError("OpenUSD could not compose the Task 042 snapped stage")
    gripper = stage.GetPrimAtPath("/World/Robot/Gripper")
    if not gripper.IsValid():
        raise RuntimeError("OpenUSD did not compose the Task 042 snapped gripper prim")
    if gripper.GetAttribute("cellforge:mechanicalConnection").Get() != (
        "mechanical-task042-kit-probe"
    ):
        raise RuntimeError("OpenUSD did not compose Task 042 mechanical metadata")
    if not gripper.GetAttribute("xformOp:transform").IsValid():
        raise RuntimeError("OpenUSD did not compose the Task 042 snap transform")

print("Verified Task 042 visual mechanical connection through Isaac Sim 6/OpenUSD.")
omni.kit.app.get_app().post_quit(0)
