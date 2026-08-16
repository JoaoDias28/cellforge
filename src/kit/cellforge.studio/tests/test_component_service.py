"""Deterministic Task 016 component browser and placement tests."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

import yaml

from cellforge.studio.application import ComponentFilters, ProjectContents
from cellforge.studio.component_service import ComponentPlacementService
from cellforge.studio.project_service import ProjectCommandService

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PEN_PROJECT = REPOSITORY_ROOT / "examples" / "pen_engraving"
SCHEMAS = REPOSITORY_ROOT / "schemas"
PLACED_ID = "component-12345678123456781234567812345678"


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


def _service() -> ComponentPlacementService:
    return ComponentPlacementService(
        SCHEMAS, new_uuid=lambda: UUID("12345678-1234-5678-1234-567812345678")
    )


def _contents(project: Path) -> ProjectContents:
    return ProjectContents(
        cell_yaml=(project / "cell.yaml").read_text(encoding="utf-8"),
        scene_usda=(project / "scene.usda").read_text(encoding="utf-8"),
    )


def test_browser_filters_and_production_compatibility_are_deterministic(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = _service()

    all_components = service.browse(project)
    robots = service.browse(project, ComponentFilters(kind="robot"))
    capability = service.browse(project, ComponentFilters(capability="fixture.verify_seated"))
    support = service.browse(project, ComponentFilters(support_level="simulated"))
    fidelity = service.browse(project, ComponentFilters(simulation_level="L0"))
    l2_fidelity = service.browse(project, ComponentFilters(simulation_level="L2"))

    assert len(all_components.components) == 6
    assert [item.component for item in robots.components] == ["generic.six_axis_robot.reference"]
    assert [item.kind for item in capability.components] == ["fixture"]
    assert len(support.components) == 6
    assert len(fidelity.components) == 6
    assert len(l2_fidelity.components) == 6
    robot = robots.components[0]
    assert robot.compatible_modes == ("simulation",)
    assert any("not production-qualified" in warning for warning in robot.warnings)
    assert any("no production adapter" in warning for warning in robot.warnings)
    assert all_components == service.browse(project)


def test_invalid_browser_filter_is_a_structured_finding(tmp_path: Path) -> None:
    result = _service().browse(_project_copy(tmp_path), ComponentFilters(simulation_level="L9"))

    assert result.components == ()
    assert [item.code for item in result.validation] == ["studio.component-filter-invalid"]


def test_place_creates_linked_yaml_and_usd_records_and_persists_variants(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    manifest_path = project / "components" / "fixture" / "component.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["variants"] = {"jaw": ["narrow", "wide"]}
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n"
    )
    service = _service()

    result = service.place(
        project,
        _contents(project),
        component="generic.pen_fixture.reference",
        version="0.1.0",
        alias="second_fixture",
        variants={"jaw": "wide"},
    )

    assert result.validation == ()
    assert result.instance_id == PLACED_ID
    assert result.contents is not None
    cell = yaml.safe_load(result.contents.cell_yaml)
    placed = next(item for item in cell["components"] if item["id"] == PLACED_ID)
    assert placed["alias"] == "second_fixture"
    assert placed["variants"] == {"jaw": "wide"}
    assert placed["usd_prim"] == "/World/Component_1234567812345678"
    assert f'cellforge:instanceId = "{PLACED_ID}"' in result.contents.scene_usda
    assert "@components/fixture/assets/fixture_visual.usd@" in result.contents.scene_usda


def test_place_rejects_invalid_alias_variant_missing_package_and_bad_scene(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    service = _service()
    original = _contents(project)
    manifest_path = project / "components" / "fixture" / "component.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["variants"] = {"jaw": ["narrow", "wide"]}
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n"
    )

    invalid_alias = service.place(
        project,
        original,
        component="generic.pen_fixture.reference",
        version="0.1.0",
        alias="Not Valid",
        variants={"jaw": "narrow"},
    )
    missing = service.place(
        project,
        original,
        component="missing.component.type",
        version="0.1.0",
        alias="missing",
        variants={},
    )
    invalid_variant = service.place(
        project,
        original,
        component="generic.pen_fixture.reference",
        version="0.1.0",
        alias="wrong_variant",
        variants={"jaw": "oversized"},
    )
    bad_scene = service.place(
        project,
        ProjectContents(
            cell_yaml=original.cell_yaml,
            scene_usda=original.scene_usda.replace('def Xform "World"', 'def Xform "Other"'),
        ),
        component="generic.pen_fixture.reference",
        version="0.1.0",
        alias="third_fixture",
        variants={"jaw": "wide"},
    )

    assert [item.code for item in invalid_alias.validation] == ["studio.component-instance-invalid"]
    assert [item.code for item in missing.validation] == ["studio.component-not-found"]
    assert [item.code for item in invalid_variant.validation] == [
        "studio.component-variant-invalid"
    ]
    assert [item.code for item in bad_scene.validation] == ["studio.scene-root-not-editable"]
    assert original == _contents(project)


def test_missing_visual_asset_fails_without_partial_buffer_change(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    original = _contents(project)
    (project / "components" / "fixture" / "assets" / "fixture_visual.usd").unlink()

    result = _service().place(
        project,
        original,
        component="generic.pen_fixture.reference",
        version="0.1.0",
        alias="asset_failure",
        variants={},
    )

    assert result.contents is None
    assert [item.code for item in result.validation] == ["studio.component-asset-missing"]
    assert original == _contents(project)


def test_remove_connected_instance_requires_explicit_resolution_and_cascades(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    service = _service()
    original = _contents(project)

    blocked = service.remove(project, original, instance_id="laser-001", remove_connections=False)
    removed = service.remove(project, original, instance_id="laser-001", remove_connections=True)

    assert [item.code for item in blocked.validation] == [
        "studio.component-removal-connections-require-resolution"
    ]
    assert blocked.contents is None
    assert removed.contents is not None
    assert removed.removed_connections == ("safety-laser-permission",)
    cell = yaml.safe_load(removed.contents.cell_yaml)
    assert "laser-001" not in {item["id"] for item in cell["components"]}
    assert "safety-laser-permission" not in {item["id"] for item in cell["connections"]}
    assert 'def Xform "Laser"' not in removed.contents.scene_usda


def test_placement_round_trip_uses_task_015_transactional_save(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    placement = _service()
    backend = ProjectCommandService(SCHEMAS, component_service=placement)
    opened = backend.inspect(project)
    assert opened.contents is not None
    changed = backend.place_component(
        project,
        opened.contents,
        component="generic.pen_fixture.reference",
        version="0.1.0",
        alias="saved_fixture",
        variants={},
    )
    assert changed.contents is not None

    saved = backend.save(project, changed.contents)

    assert saved.project is not None
    assert saved.project.component_count == 7
    reopened = backend.inspect(project)
    assert reopened.project is not None
    assert reopened.validation == ()
    assert PLACED_ID in (project / "cell.yaml").read_text(encoding="utf-8")
    assert PLACED_ID in (project / "scene.usda").read_text(encoding="utf-8")
