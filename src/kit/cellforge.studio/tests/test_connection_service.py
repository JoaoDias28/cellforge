"""Deterministic Task 017 connection authoring and validation tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from cellforge.studio.application import ProjectContents
from cellforge.studio.connection_service import ConnectionAuthoringService
from cellforge.studio.project_service import ProjectCommandService

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


def _without_connections(contents: ProjectContents, *connection_ids: str) -> ProjectContents:
    cell = yaml.safe_load(contents.cell_yaml)
    cell["connections"] = [
        item for item in cell["connections"] if item["id"] not in set(connection_ids)
    ]
    return ProjectContents(
        cell_yaml=yaml.safe_dump(cell, sort_keys=False), scene_usda=contents.scene_usda
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


def test_port_browser_has_typed_layers_and_distinct_modeled_safety_edges(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)

    result = ConnectionAuthoringService(SCHEMAS).browse(project, _contents(project))

    assert result.validation == ()
    assert {item.kind for item in result.ports} == {
        "mechanical",
        "software",
        "industrial_io",
        "safety",
    }
    safety_ports = [item for item in result.ports if item.kind == "safety"]
    assert safety_ports and all(item.modeled_only for item in safety_ports)
    safety_edges = [item for item in result.edges if item.kind == "safety"]
    assert safety_edges and all(item.modeled_only and not item.executable for item in safety_edges)
    assert "engineering-review metadata only" in result.safety_disclaimer


def test_software_io_and_safety_edges_use_domain_validation_and_expected_semantics(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    service = ConnectionAuthoringService(SCHEMAS)
    original = _without_connections(_contents(project), "safety-laser-permission")

    software = service.connect(
        project,
        original,
        connection_id="software-cycle-state",
        kind="software",
        from_component="laser-001",
        from_port="cycle_state",
        to_component="camera-001",
        to_port="process_state",
    )
    assert software.contents is not None
    assert software.edge is not None and software.edge.executable is True
    assert software.contents.scene_usda == original.scene_usda

    io_edge = service.connect(
        project,
        software.contents,
        connection_id="io-fixture-ready",
        kind="industrial_io",
        from_component="fixture-001",
        from_port="seated",
        to_component="laser-001",
        to_port="cycle_start",
    )
    assert io_edge.contents is not None
    assert io_edge.edge is not None and io_edge.edge.executable is True

    safety = service.connect(
        project,
        io_edge.contents,
        connection_id="safety-laser-permission-new",
        kind="safety",
        from_component="safety-status-001",
        from_port="laser_emission_permitted",
        to_component="laser-001",
        to_port="laser_emission_permitted",
    )
    assert safety.contents is not None
    assert safety.edge is not None
    assert safety.edge.modeled_only is True and safety.edge.executable is False
    cell = yaml.safe_load(safety.contents.cell_yaml)
    persisted = next(
        item for item in cell["connections"] if item["id"] == "safety-laser-permission-new"
    )
    assert persisted["config"] == {
        "modeled_only": True,
        "implementation": "external_rated_hardware",
    }
    assert safety.contents.scene_usda == original.scene_usda


def test_incompatible_or_duplicate_connection_is_rejected_without_mutation(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    service = ConnectionAuthoringService(SCHEMAS)
    original = _contents(project)

    incompatible = service.connect(
        project,
        original,
        connection_id="bad-io",
        kind="industrial_io",
        from_component="fixture-001",
        from_port="seated",
        to_component="robot-001",
        to_port="trajectory",
    )
    duplicate = service.connect(
        project,
        original,
        connection_id="safety-robot-permission",
        kind="safety",
        from_component="safety-status-001",
        from_port="safe_motion_permitted",
        to_component="robot-001",
        to_port="safe_motion_permitted",
    )

    assert incompatible.contents is None
    assert [item.code for item in incompatible.validation] == ["resolver.port-missing"]
    assert duplicate.contents is None
    assert set(item.code for item in duplicate.validation) == {
        "resolver.duplicate-connection-id",
        "resolver.duplicate-connection-endpoints",
    }
    assert original == _contents(project)


def test_browser_surfaces_domain_validation_for_an_invalid_existing_edge(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    original = _contents(project)
    cell = yaml.safe_load(original.cell_yaml)
    cell["connections"].append(
        {
            "id": "invalid-existing-edge",
            "kind": "industrial_io",
            "from": {"component": "fixture-001", "port": "seated"},
            "to": {"component": "robot-001", "port": "trajectory"},
        }
    )
    invalid = ProjectContents(
        cell_yaml=yaml.safe_dump(cell, sort_keys=False), scene_usda=original.scene_usda
    )

    result = ConnectionAuthoringService(SCHEMAS).browse(project, invalid)

    assert "resolver.port-missing" in {item.code for item in result.validation}


def test_mechanical_preview_and_apply_update_graph_and_spatial_scene_coherently(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    original = _detached_gripper(_contents(project))
    service = ConnectionAuthoringService(SCHEMAS)

    preview = service.preview_mechanical(
        project,
        original,
        connection_id="mechanical-new",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
    )
    assert preview.preview is not None
    assert preview.preview.current_target_prim == "/World/Gripper"
    assert preview.preview.snapped_target_prim == "/World/Robot/Gripper"
    assert preview.preview.transform == (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    assert preview.contents is None

    applied = service.connect(
        project,
        original,
        connection_id="mechanical-new",
        kind="mechanical",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
    )
    assert applied.validation == ()
    assert applied.contents is not None
    cell = yaml.safe_load(applied.contents.cell_yaml)
    gripper = next(item for item in cell["components"] if item["id"] == "gripper-001")
    assert gripper["usd_prim"] == "/World/Robot/Gripper"
    assert 'cellforge:mechanicalConnection = "mechanical-new"' in applied.contents.scene_usda
    assert "matrix4d xformOp:transform" in applied.contents.scene_usda
    assert applied.contents.scene_usda.index(
        'def Xform "Gripper"'
    ) < applied.contents.scene_usda.index('def Xform "Laser"')


def test_mechanical_missing_transform_and_scene_edit_failure_are_explicit(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    original = _detached_gripper(_contents(project))
    service = ConnectionAuthoringService(SCHEMAS)
    robot_manifest = project / "components" / "robot" / "component.yaml"
    manifest = yaml.safe_load(robot_manifest.read_text(encoding="utf-8"))
    manifest["ports"]["mechanical"][0].pop("metadata")
    robot_manifest.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n"
    )

    missing_transform = service.preview_mechanical(
        project,
        original,
        connection_id="mechanical-missing-transform",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
    )
    assert [item.code for item in missing_transform.validation] == [
        "studio.mechanical-snap-transform-missing"
    ]

    manifest["ports"]["mechanical"][0]["metadata"] = {
        "snap_transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    }
    robot_manifest.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n"
    )
    broken_scene = ProjectContents(
        cell_yaml=original.cell_yaml,
        scene_usda=original.scene_usda.replace('def Xform "Gripper"', 'def Xform "Missing"'),
    )
    failed = service.connect(
        project,
        broken_scene,
        connection_id="mechanical-scene-failure",
        kind="mechanical",
        from_component="robot-001",
        from_port="tool_flange",
        to_component="gripper-001",
        to_port="robot_mount",
    )
    assert failed.contents is None
    assert [item.code for item in failed.validation] == ["studio.mechanical-snap-failed"]


def test_connection_edit_persists_through_task_015_transactional_save(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    backend = ProjectCommandService(SCHEMAS)
    opened = backend.inspect(project)
    assert opened.contents is not None
    changed = backend.connect_ports(
        project,
        opened.contents,
        connection_id="software-cycle-state",
        kind="software",
        from_component="laser-001",
        from_port="cycle_state",
        to_component="camera-001",
        to_port="process_state",
    )
    assert changed.contents is not None

    saved = backend.save(project, changed.contents)

    assert saved.project is not None and saved.project.connection_count == 4
    reopened = backend.inspect(project)
    assert reopened.project is not None and reopened.validation == ()
    assert "software-cycle-state" in (project / "cell.yaml").read_text(encoding="utf-8")
