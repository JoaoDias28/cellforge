"""Task 042 typed connection canvas, spatial pairing, and transactional tests."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
import yaml

from cellforge.studio.application import (
    ConnectionLayoutEntry,
    ConnectionLayoutMetadata,
    ProjectContents,
    StudioApplication,
)
from cellforge.studio.connection_service import (
    ConnectionAuthoringService,
    deterministic_connection_id,
)
from cellforge.studio.project_service import ProjectCommandService, ProjectSaveError
from cellforge.studio.schema_authoring import SchemaAuthoringService

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PEN_PROJECT = REPOSITORY_ROOT / "examples" / "pen_engraving"
SCHEMAS = REPOSITORY_ROOT / "schemas"


def _project_copy(tmp_path: Path) -> Path:
    project = tmp_path / "pen-project"
    shutil.copytree(PEN_PROJECT, project)
    shutil.copytree(SCHEMAS, project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    return project


def _contents(project: Path) -> ProjectContents:
    return ProjectContents(
        cell_yaml=(project / "cell.yaml").read_text(encoding="utf-8"),
        scene_usda=(project / "scene.usda").read_text(encoding="utf-8"),
    )


def _detached_gripper(contents: ProjectContents) -> ProjectContents:
    cell = yaml.safe_load(contents.cell_yaml)
    cell["connections"] = [
        item for item in cell["connections"] if item["id"] != "mechanical-robot-gripper"
    ]
    gripper = next(item for item in cell["components"] if item["id"] == "gripper-001")
    gripper["usd_prim"] = "/World/Gripper"
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


def _without_connections(contents: ProjectContents, *connection_ids: str) -> ProjectContents:
    cell = yaml.safe_load(contents.cell_yaml)
    cell["connections"] = [
        item for item in cell["connections"] if item["id"] not in set(connection_ids)
    ]
    return ProjectContents(
        cell_yaml=yaml.safe_dump(cell, sort_keys=False),
        scene_usda=contents.scene_usda,
    )


def _canonical_pair(project: Path) -> tuple[bytes, bytes]:
    return (project.joinpath("cell.yaml").read_bytes(), project.joinpath("scene.usda").read_bytes())


def test_canvas_layers_search_highlight_and_layout_use_dto_identity(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = ConnectionAuthoringService(SCHEMAS)
    endpoint = "robot-001:tool_flange"
    layout = ConnectionLayoutMetadata(
        entries=(ConnectionLayoutEntry(endpoint_id=endpoint, x=77.0, y=88.0),),
        selected_endpoint_id=endpoint,
    )

    result = service.ValidateCellConnections(
        project,
        _contents(project),
        query="robot-001 tool_flange",
        selected_endpoint_id=endpoint,
        layout=layout,
    )

    assert result.validation == ()
    assert result.canvas is not None
    assert [layer.kind for layer in result.canvas.layers] == [
        "mechanical",
        "software",
        "industrial_io",
        "safety",
    ]
    assert result.canvas.layers[-1].label == "MODELED SAFETY (NON-EXECUTABLE)"
    assert [port.endpoint_id for port in result.canvas.palette_ports] == [endpoint]
    assert endpoint in result.canvas.highlighted_endpoint_ids
    assert result.canvas.layout.position_for(endpoint) == (77.0, 88.0)
    assert endpoint not in {edge_id for edge_id, _ in result.canvas.layout.routes}
    assert (
        deterministic_connection_id(
            "software", "laser-001", "cycle_state", "camera-001", "process_state"
        )
        == "software-laser-001-cycle_state-camera-001-process_state"
    )
    assert all(edge.edge_id == edge.connection_id for edge in result.edges)

    aliases_changed = _contents(project).cell_yaml.replace("alias: robot", "alias: renamed-robot")
    renamed = service.ValidateCellConnections(
        project, ProjectContents(aliases_changed, _contents(project).scene_usda)
    )
    assert renamed.canvas is not None
    assert any(port.endpoint_id == endpoint for port in renamed.canvas.ports)


def test_optional_safety_marker_is_not_materialized_on_existing_connection_rows() -> None:
    service = SchemaAuthoringService(SCHEMAS)
    form = service.BuildSchemaForm(
        SCHEMAS / "cell.schema.json",
        source=PEN_PROJECT / "cell.yaml",
        schema_kind="cell",
    )

    assert all("modeled_only" not in item for item in form.values["connections"])
    candidate = service.PreviewFormEdit(form, {"/cell/name": "Round-trip cell"})
    assert candidate.can_save
    assert all("modeled_only" not in item for item in candidate.canonical_value["connections"])


def test_preview_stage_save_remove_and_reopen_preserve_mechanical_pair(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = ConnectionAuthoringService(SCHEMAS)
    original = _detached_gripper(_contents(project))
    before = _canonical_pair(project)

    preview = service.PreviewCellConnection(
        project,
        original,
        kind="mechanical",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
    )

    assert preview.validation == ()
    assert preview.contents is None
    assert preview.connection_preview is not None
    assert preview.connection_preview.no_write is True
    assert preview.connection_preview.edge_id == deterministic_connection_id(
        "mechanical", "robot-001", "tool_flange", "gripper-001", "robot_mount"
    )
    assert preview.connection_preview.proposed_target_prim == "/World/Robot/Gripper"
    assert preview.connection_preview.source_frame == "tool_flange"
    assert preview.connection_preview.target_frame == "robot_mount"
    assert len(preview.connection_preview.candidate_cell_sha256) == 64
    assert len(preview.connection_preview.candidate_scene_sha256) == 64
    assert _canonical_pair(project) == before

    staged = service.StageCellConnection(
        project,
        original,
        kind="mechanical",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
    )
    assert staged.contents is not None
    assert (
        preview.connection_preview.candidate_cell_sha256
        == hashlib.sha256(staged.contents.cell_yaml.encode("utf-8")).hexdigest()
    )
    assert (
        preview.connection_preview.candidate_scene_sha256
        == hashlib.sha256(staged.contents.scene_usda.encode("utf-8")).hexdigest()
    )
    staged_cell = yaml.safe_load(staged.contents.cell_yaml)
    assert (
        next(item for item in staged_cell["components"] if item["id"] == "gripper-001")["usd_prim"]
        == "/World/Robot/Gripper"
    )
    assert staged.contents.scene_usda.count('cellforge:instanceId = "gripper-001"') == 1

    backend = ProjectCommandService(SCHEMAS)
    saved = backend.save(project, staged.contents)
    assert saved.project is not None and saved.validation == ()
    reopened = backend.inspect(project)
    assert reopened.contents is not None and reopened.validation == ()
    reopened_cell = yaml.safe_load(reopened.contents.cell_yaml)
    edge_id = deterministic_connection_id(
        "mechanical", "robot-001", "tool_flange", "gripper-001", "robot_mount"
    )
    assert any(item["id"] == edge_id for item in reopened_cell["connections"])
    assert (
        next(item for item in reopened_cell["components"] if item["id"] == "gripper-001")[
            "usd_prim"
        ]
        == "/World/Robot/Gripper"
    )
    assert f'cellforge:mechanicalConnection = "{edge_id}"' in reopened.contents.scene_usda
    assert "matrix4d xformOp:transform" in reopened.contents.scene_usda

    removed = service.RemoveCellConnection(project, reopened.contents, connection_id=edge_id)
    assert removed.validation == ()
    assert removed.contents is not None
    removed_cell = yaml.safe_load(removed.contents.cell_yaml)
    assert all(item["id"] != edge_id for item in removed_cell["connections"])
    assert (
        next(item for item in removed_cell["components"] if item["id"] == "gripper-001")["usd_prim"]
        == "/World/Gripper"
    )
    assert "cellforge:mechanicalConnection" not in removed.contents.scene_usda


def test_logical_io_and_safety_layers_have_distinct_persistence_semantics(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = ConnectionAuthoringService(SCHEMAS)
    original = _without_connections(_contents(project), "safety-laser-permission")

    software = service.StageCellConnection(
        project,
        original,
        kind="software",
        from_component="laser-001",
        from_port="cycle_state",
        to_component="camera-001",
        to_port="process_state",
    )
    assert software.contents is not None and software.edge is not None
    assert software.contents.scene_usda == original.scene_usda

    industrial_io = service.StageCellConnection(
        project,
        software.contents,
        kind="industrial_io",
        from_component="fixture-001",
        from_port="seated",
        to_component="laser-001",
        to_port="cycle_start",
    )
    assert industrial_io.contents is not None and industrial_io.edge is not None
    assert industrial_io.contents.scene_usda == original.scene_usda

    safety = service.StageCellConnection(
        project,
        industrial_io.contents,
        kind="safety",
        from_component="safety-status-001",
        from_port="laser_emission_permitted",
        to_component="laser-001",
        to_port="laser_emission_permitted",
    )
    assert safety.contents is not None and safety.edge is not None
    assert safety.edge.modeled_only is True and safety.edge.executable is False
    assert safety.connection_preview is not None
    assert safety.connection_preview.modeled_only is True
    assert safety.connection_preview.executable is False
    assert safety.contents.scene_usda == original.scene_usda
    persisted = yaml.safe_load(safety.contents.cell_yaml)
    safety_record = next(
        item for item in persisted["connections"] if item["id"] == safety.connection_id
    )
    assert safety_record["kind"] == "safety"
    assert safety_record["modeled_only"] is True
    assert safety_record["config"]["implementation"] == "external_rated_hardware"

    canvas = service.ValidateCellConnections(project, safety.contents).canvas
    assert canvas is not None
    assert canvas.layers[-1].modeled_only is True
    assert all(not edge.executable for edge in canvas.layers[-1].edges)
    removed = service.RemoveCellConnection(
        project, safety.contents, connection_id=safety.connection_id or ""
    )
    assert removed.contents is not None
    assert [item.code for item in removed.warnings] == ["studio.safety-edge-removal-review"]


def test_invalid_direction_capability_duplicate_and_spatial_inputs_fail_closed(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    service = ConnectionAuthoringService(SCHEMAS)
    original = _contents(project)

    missing = service.StageCellConnection(
        project,
        original,
        kind="software",
        from_component="not-an-instance",
        from_port="cycle_state",
        to_component="camera-001",
        to_port="process_state",
    )
    assert missing.contents is None
    assert "resolver.connection-component-missing" in {item.code for item in missing.validation}

    wrong_direction = service.StageCellConnection(
        project,
        original,
        kind="industrial_io",
        from_component="laser-001",
        from_port="cycle_start",
        to_component="fixture-001",
        to_port="seated",
    )
    assert wrong_direction.contents is None
    assert "resolver.port-direction-incompatible" in {
        item.code for item in wrong_direction.validation
    }

    wrong_type = service.StageCellConnection(
        project,
        original,
        kind="software",
        from_component="laser-001",
        from_port="cycle_state",
        to_component="camera-001",
        to_port="locate",
    )
    assert wrong_type.contents is None
    assert "resolver.port-type-incompatible" in {item.code for item in wrong_type.validation}

    duplicate = service.StageCellConnection(
        project,
        original,
        kind="safety",
        connection_id="safety-robot-permission",
        from_component="safety-status-001",
        from_port="safe_motion_permitted",
        to_component="robot-001",
        to_port="safe_motion_permitted",
    )
    assert duplicate.contents is None
    assert "resolver.duplicate-connection-id" in {item.code for item in duplicate.validation}

    manifest_path = project / "components" / "laser" / "component.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    cycle_state = next(
        item for item in manifest["ports"]["software"] if item["id"] == "cycle_state"
    )
    cycle_state["metadata"] = {"capability": "missing.capability"}
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n"
    )
    unavailable = service.StageCellConnection(
        project,
        original,
        kind="software",
        from_component="laser-001",
        from_port="cycle_state",
        to_component="camera-001",
        to_port="process_state",
    )
    assert unavailable.contents is None
    assert [item.code for item in unavailable.validation] == ["studio.capability-unavailable"]

    robot_path = project / "components" / "robot" / "component.yaml"
    robot = yaml.safe_load(robot_path.read_text(encoding="utf-8"))
    robot["ports"]["mechanical"][0]["metadata"]["snap_transform"] = [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
    ]
    robot_path.write_text(yaml.safe_dump(robot, sort_keys=False), encoding="utf-8", newline="\n")
    singular = service.PreviewCellConnection(
        project,
        _detached_gripper(original),
        kind="mechanical",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
    )
    assert singular.contents is None
    assert singular.validation, singular
    assert singular.validation[0].code == "studio.mechanical-snap-transform-invalid"


def test_application_preview_stage_undo_redo_remove_and_save_failure_are_transactional(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    application = StudioApplication(ProjectCommandService(SCHEMAS))
    opened = application.open_project(project)
    assert opened.project is not None
    before = _canonical_pair(project)

    previewed = application.preview_cell_connection(
        "software",
        "laser-001",
        "cycle_state",
        "camera-001",
        "process_state",
    )
    assert previewed.connection_preview is not None
    assert previewed.dirty is False
    assert _canonical_pair(project) == before

    staged = application.stage_cell_connection(
        "software",
        "laser-001",
        "cycle_state",
        "camera-001",
        "process_state",
    )
    assert staged.dirty is True
    assert staged.project is not None and staged.project.connection_count == 4
    assert len(staged.connection_edges) == 4
    edge_id = staged.connection_edges[-1].edge_id
    assert application.undo().project is not None
    assert edge_id not in {edge.edge_id for edge in application.snapshot.connection_edges}
    assert application.redo().project is not None
    assert edge_id in {edge.edge_id for edge in application.snapshot.connection_edges}
    removed = application.remove_cell_connection(edge_id)
    assert edge_id not in {edge.edge_id for edge in removed.connection_edges}
    assert application.undo().connection_edges[-1].edge_id == edge_id

    service = ConnectionAuthoringService(SCHEMAS)
    detached = _detached_gripper(_contents(project))
    staged_mechanical = service.StageCellConnection(
        project,
        detached,
        kind="mechanical",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
    )
    assert staged_mechanical.contents is not None
    pair_before_failed_save = _canonical_pair(project)
    hash_before_failed_save = tuple(
        hashlib.sha256(item).hexdigest() for item in pair_before_failed_save
    )
    calls = 0

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replacement failure")
        Path(source).replace(target)

    with pytest.raises(ProjectSaveError):
        ProjectCommandService(SCHEMAS, replace_file=fail_second_replace).save(
            project, staged_mechanical.contents
        )
    assert _canonical_pair(project) == pair_before_failed_save
    hash_after_failed_save = tuple(
        hashlib.sha256(item).hexdigest() for item in _canonical_pair(project)
    )
    assert hash_after_failed_save == hash_before_failed_save
