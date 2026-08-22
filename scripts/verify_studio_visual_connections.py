"""Deterministic non-Kit Task 042 visual-connection acceptance probe."""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import yaml


def _detached(contents):
    from cellforge.studio.application import ProjectContents

    cell = yaml.safe_load(contents.cell_yaml)
    cell["connections"] = [
        item for item in cell["connections"] if item["id"] != "mechanical-robot-gripper"
    ]
    next(item for item in cell["components"] if item["id"] == "gripper-001")["usd_prim"] = (
        "/World/Gripper"
    )
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
    scene = contents.scene_usda.replace(nested, "").replace(
        '    def Xform "Laser" {', f'{detached}    def Xform "Laser" {{'
    )
    return ProjectContents(cell_yaml=yaml.safe_dump(cell, sort_keys=False), scene_usda=scene)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src" / "kit" / "cellforge.studio"))
    from cellforge.studio.application import StudioApplication
    from cellforge.studio.connection_service import deterministic_connection_id
    from cellforge.studio.project_service import ProjectCommandService

    with tempfile.TemporaryDirectory(prefix="cellforge-task042-", dir=root) as directory:
        project = Path(directory) / "pen-project"
        shutil.copytree(root / "examples" / "pen_engraving", project)
        shutil.copytree(root / "schemas", project / "schemas")
        cell_path = project / "cell.yaml"
        cell_path.write_text(
            cell_path.read_text(encoding="utf-8").replace(
                "schema: ../../schemas/recipe.schema.json", "schema: schemas/recipe.schema.json"
            ),
            encoding="utf-8",
            newline="\n",
        )
        backend = ProjectCommandService(root / "schemas")
        opened = backend.inspect(project)
        if opened.contents is None:
            raise RuntimeError("Task 042 probe could not open the reference project")
        graph = backend.ValidateCellConnections(project, opened.contents, query="robot tool_flange")
        if graph.canvas is None or len(graph.canvas.layers) != 4:
            raise RuntimeError("Task 042 probe did not build all four typed canvas layers")
        if graph.canvas.layers[-1].label != "MODELED SAFETY (NON-EXECUTABLE)":
            raise RuntimeError("Task 042 probe lost the distinct modeled-safety layer")

        before = (cell_path.read_bytes(), (project / "scene.usda").read_bytes())
        preview = backend.PreviewCellConnection(
            project,
            opened.contents,
            kind="software",
            from_component="laser-001",
            from_port="cycle_state",
            to_component="camera-001",
            to_port="process_state",
        )
        expected_id = deterministic_connection_id(
            "software", "laser-001", "cycle_state", "camera-001", "process_state"
        )
        if (
            preview.contents is not None
            or preview.connection_preview is None
            or preview.connection_preview.edge_id != expected_id
            or not preview.connection_preview.no_write
        ):
            raise RuntimeError("Task 042 preview did not remain a deterministic no-write DTO")
        if before != (cell_path.read_bytes(), (project / "scene.usda").read_bytes()):
            raise RuntimeError("Task 042 preview mutated canonical files")

        staged = backend.StageCellConnection(
            project,
            opened.contents,
            kind="software",
            from_component="laser-001",
            from_port="cycle_state",
            to_component="camera-001",
            to_port="process_state",
        )
        if staged.contents is None or staged.edge is None or not staged.edge.executable:
            raise RuntimeError("Task 042 probe rejected a compatible software edge")
        if (
            preview.connection_preview.candidate_cell_sha256
            != hashlib.sha256(staged.contents.cell_yaml.encode("utf-8")).hexdigest()
        ):
            raise RuntimeError("Task 042 preview cell hash did not match the staged candidate")
        if (
            preview.connection_preview.candidate_scene_sha256
            != hashlib.sha256(staged.contents.scene_usda.encode("utf-8")).hexdigest()
        ):
            raise RuntimeError("Task 042 preview scene hash did not match the staged candidate")
        saved = backend.save(project, staged.contents)
        reopened = backend.inspect(project)
        if saved.project is None or reopened.contents is None or reopened.validation:
            raise RuntimeError("Task 042 probe could not round-trip the staged edge")

        safety = backend.StageCellConnection(
            project,
            reopened.contents,
            kind="safety",
            from_component="safety-status-001",
            from_port="laser_emission_permitted",
            to_component="laser-001",
            to_port="laser_emission_permitted",
            connection_id="safety-task042-probe",
        )
        if (
            safety.contents is None
            or safety.edge is None
            or not safety.edge.modeled_only
            or safety.edge.executable
        ):
            raise RuntimeError("Task 042 probe made modeled safety executable")

        detached = _detached(opened.contents)
        mechanical = backend.PreviewCellConnection(
            project,
            detached,
            kind="mechanical",
            from_component="robot-001",
            from_port="tool_flange",
            to_component="gripper-001",
            to_port="robot_mount",
        )
        if (
            mechanical.preview is None
            or mechanical.preview.snapped_target_prim != "/World/Robot/Gripper"
            or mechanical.connection_preview is None
            or mechanical.connection_preview.proposed_transform is None
        ):
            raise RuntimeError("Task 042 probe did not produce the mechanical spatial preview")

        application = StudioApplication(backend)
        application.open_project(project)
        application.preview_cell_connection(
            "industrial_io", "fixture-001", "seated", "laser-001", "cycle_start"
        )
        staged_snapshot = application.stage_cell_connection(
            "industrial_io", "fixture-001", "seated", "laser-001", "cycle_start"
        )
        if not staged_snapshot.can_undo or not application.undo().can_redo:
            raise RuntimeError("Task 042 application command undo/redo was not complete")
        application.redo()

    print(
        "Verified Task 042 visual typed connections, spatial preview, safety boundary, "
        "and no-write behavior."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
