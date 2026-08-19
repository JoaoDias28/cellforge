"""Contract tests for the filesystem registry and pure cell resolver."""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from cellforge_domain import (
    AdapterMode,
    CellProject,
    ComponentInstance,
    ExecutionMode,
    FilesystemComponentRegistry,
    PortDirection,
    SchemaRegistry,
    load_document,
    resolve_cell,
    to_canonical_json,
)

REPOSITORY_ROOT = Path(__file__).parents[4]
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "pen_engraving"
COMPONENT_ROOT = EXAMPLE_ROOT / "components"
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas"


@pytest.fixture
def schema_registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(SCHEMA_ROOT)


@pytest.fixture
def component_registry(schema_registry: SchemaRegistry) -> FilesystemComponentRegistry:
    return FilesystemComponentRegistry.from_directory(
        COMPONENT_ROOT,
        schema_registry=schema_registry,
    )


@pytest.fixture
def cell(schema_registry: SchemaRegistry) -> CellProject:
    return load_document(
        EXAMPLE_ROOT / "cell.yaml",
        CellProject,
        schema_registry=schema_registry,
    )


def _codes(report: Any) -> set[str]:
    return {finding.code for finding in report.findings}


def _copy_component(
    source_name: str,
    destination: Path,
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    source = COMPONENT_ROOT / source_name
    shutil.copytree(source, destination)
    if mutate is None:
        return
    manifest_path = destination / "component.yaml"
    manifest = cast(
        dict[str, Any],
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")),
    )
    mutate(manifest)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def test_pen_example_resolves_capabilities_and_graph_in_simulation(
    cell: CellProject,
    component_registry: FilesystemComponentRegistry,
) -> None:
    report = resolve_cell(cell, component_registry, ExecutionMode.SIMULATION)

    assert report.valid
    assert report.findings == ()
    assert len(component_registry.components) == 6
    assert len(report.components) == 6
    assert len(report.connections) == 3
    assert len(report.capabilities) == 10
    assert {binding.version for binding in report.capabilities} == {"1.0.0"}
    assert len(report.graph.nodes) == 7
    assert len(report.graph.edges) == 13
    assert {link.kind.value for link in report.connections} == {"mechanical", "safety"}


def test_resolution_is_deterministic_for_reordered_equivalent_input(
    cell: CellProject,
    component_registry: FilesystemComponentRegistry,
) -> None:
    first = resolve_cell(cell, component_registry, ExecutionMode.SIMULATION)
    reordered = cell.model_copy(deep=True)
    reordered.components = tuple(reversed(reordered.components))
    reordered.connections = tuple(reversed(reordered.connections))
    reordered.tasks[0].required_capabilities = tuple(
        reversed(reordered.tasks[0].required_capabilities)
    )

    second = resolve_cell(reordered, component_registry, ExecutionMode.SIMULATION)

    assert to_canonical_json(first) == to_canonical_json(second)


def test_registry_reports_invalid_manifest_and_duplicate_exact_version(
    tmp_path: Path,
    schema_registry: SchemaRegistry,
) -> None:
    registry_root = tmp_path / "components"
    _copy_component("robot", registry_root / "a_robot")
    _copy_component("robot", registry_root / "b_robot")
    invalid_path = registry_root / "invalid" / "component.yaml"
    invalid_path.parent.mkdir(parents=True)
    invalid_path.write_text("schema_version: 0.1.0\n", encoding="utf-8")

    registry = FilesystemComponentRegistry.from_directory(
        registry_root,
        schema_registry=schema_registry,
    )

    assert len(registry.components) == 1
    assert registry.components[0].package_path == "a_robot"
    assert {finding.code for finding in registry.findings} == {
        "registry.duplicate-component-version",
        "registry.manifest-invalid",
    }


def test_registry_missing_root_is_a_stable_failure(tmp_path: Path) -> None:
    registry = FilesystemComponentRegistry.from_directory(tmp_path / "missing")

    assert not registry.components
    assert [finding.code for finding in registry.findings] == ["registry.root-not-found"]


def test_exact_component_version_conflict_and_missing_type_are_distinct(
    cell: CellProject,
    component_registry: FilesystemComponentRegistry,
) -> None:
    changed = cell.model_copy(deep=True)
    changed.components[0].version = "9.0.0"
    changed.components[3].component = "missing.camera.reference"

    report = resolve_cell(changed, component_registry, ExecutionMode.SIMULATION)

    assert not report.valid
    assert "resolver.component-version-conflict" in _codes(report)
    assert "resolver.component-missing" in _codes(report)


def test_missing_connection_port_has_stable_code(
    cell: CellProject,
    component_registry: FilesystemComponentRegistry,
) -> None:
    changed = cell.model_copy(deep=True)
    changed.connections[0].to.port = "missing_mount"

    report = resolve_cell(changed, component_registry, ExecutionMode.SIMULATION)

    assert not report.valid
    assert "resolver.port-missing" in _codes(report)


def test_incompatible_mechanical_ports_and_directions_are_rejected(
    cell: CellProject,
    component_registry: FilesystemComponentRegistry,
) -> None:
    robot = component_registry.get("generic.six_axis_robot.reference", "0.1.0")
    gripper = component_registry.get("generic.parallel_gripper.pen", "0.1.0")
    assert robot is not None
    assert gripper is not None
    robot.manifest.ports.mechanical[0].direction = PortDirection.INPUT
    gripper.manifest.ports.mechanical[0].type = "incompatible_mount"

    report = resolve_cell(cell, component_registry, ExecutionMode.SIMULATION)

    assert not report.valid
    assert "resolver.port-direction-incompatible" in _codes(report)
    assert "resolver.mechanical-port-incompatible" in _codes(report)


def test_production_rejects_simulated_only_components(
    cell: CellProject,
    tmp_path: Path,
    schema_registry: SchemaRegistry,
) -> None:
    registry_root = tmp_path / "components"
    for name in ["robot", "gripper", "laser", "camera", "fixture", "safety_status"]:

        def _make_simulated(manifest: dict[str, Any]) -> None:
            manifest["support"]["level"] = "simulated"
            if "adapters" in manifest:
                manifest["adapters"]["hardware"] = None
            for cap in manifest.get("capabilities", []):
                cap["modes"] = ["simulation"]

        _copy_component(name, registry_root / name, mutate=_make_simulated)

    component_registry = FilesystemComponentRegistry.from_directory(
        registry_root,
        schema_registry=schema_registry,
    )
    report = resolve_cell(cell, component_registry, ExecutionMode.PRODUCTION)

    assert not report.valid
    assert "resolver.support-level-unsupported" in _codes(report)
    assert "resolver.adapter-missing" in _codes(report)
    assert "resolver.capability-mode-unsupported" in _codes(report)


def test_explicit_hardware_adapter_selection_is_invalid_in_simulation(
    cell: CellProject,
    component_registry: FilesystemComponentRegistry,
) -> None:
    changed = cell.model_copy(deep=True)
    changed.components[0].adapter_mode = AdapterMode.HARDWARE

    report = resolve_cell(changed, component_registry, ExecutionMode.SIMULATION)

    assert not report.valid
    assert "resolver.adapter-mode-incompatible" in _codes(report)


def test_missing_and_mode_unsupported_capabilities_have_stable_codes(
    cell: CellProject,
    component_registry: FilesystemComponentRegistry,
) -> None:
    changed = cell.model_copy(deep=True)
    changed.tasks[0].required_capabilities = (
        *changed.tasks[0].required_capabilities,
        "vision.measure_missing",
    )
    camera = component_registry.get("generic.vision_camera.reference", "0.1.0")
    assert camera is not None
    camera.manifest.capabilities[0].modes = (ExecutionMode.PRODUCTION,)

    report = resolve_cell(changed, component_registry, ExecutionMode.SIMULATION)

    assert not report.valid
    assert "resolver.capability-missing" in _codes(report)
    assert "resolver.capability-mode-unsupported" in _codes(report)


def test_multiple_equal_version_capability_providers_are_ambiguous(
    cell: CellProject,
    component_registry: FilesystemComponentRegistry,
) -> None:
    changed = cell.model_copy(deep=True)
    camera_data = changed.components[3].model_dump(mode="json")
    camera_data.update({"id": "camera-002", "alias": "vision_camera_2"})
    changed.components = (*changed.components, ComponentInstance.model_validate(camera_data))

    report = resolve_cell(changed, component_registry, ExecutionMode.SIMULATION)

    assert not report.valid
    assert "resolver.capability-provider-ambiguous" in _codes(report)


def test_conflicting_capability_versions_are_not_selected(
    tmp_path: Path,
    schema_registry: SchemaRegistry,
    cell: CellProject,
) -> None:
    registry_root = tmp_path / "components"
    for source in sorted(COMPONENT_ROOT.iterdir()):
        if source.is_dir():
            shutil.copytree(source, registry_root / source.name)

    def make_camera_v2(manifest: dict[str, Any]) -> None:
        manifest["component"]["version"] = "2.0.0"
        for capability in manifest["capabilities"]:
            capability["version"] = "2.0.0"
            capability["definition"] = f"cellforge://capabilities/{capability['contract']}/2.0.0"

    _copy_component("camera", registry_root / "camera_v2", make_camera_v2)
    registry = FilesystemComponentRegistry.from_directory(
        registry_root,
        schema_registry=schema_registry,
    )
    changed = cell.model_copy(deep=True)
    camera_data = changed.components[3].model_dump(mode="json")
    camera_data.update(
        {
            "id": "camera-002",
            "alias": "vision_camera_2",
            "version": "2.0.0",
        }
    )
    changed.components = (*changed.components, ComponentInstance.model_validate(camera_data))

    report = resolve_cell(changed, registry, ExecutionMode.SIMULATION)

    assert not report.valid
    assert "resolver.capability-version-conflict" in _codes(report)
