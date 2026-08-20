"""Contract-driven deterministic L0 executor for the reusable tray-kitting example.

The executor is engineering test infrastructure, not a runtime supervisor.  It resolves every
operation from a behavior-tree port declared by a component manifest and then calls the existing
Task 009 generic mock adapters.  It intentionally models sequencing, adapter outcomes, and
recovery only; it does not model geometry, contact, perception, production, or functional safety.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, NoReturn, cast
from uuid import NAMESPACE_URL, uuid5
from xml.etree import ElementTree

import yaml
from cellforge_device_sdk.models import CapabilityCommand, CommandResult
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from cellforge_mock_adapters.core import MockDeviceAdapter
from cellforge_mock_adapters.devices import build_device_mock
from cellforge_mock_adapters.headless import (
    NodeStatus,
    ScenarioDefinition,
    ScenarioError,
    ScenarioResult,
    TraceEvent,
)
from cellforge_mock_adapters.scenarios import parse_device_scenario

KITTING_CELL_ID = "6e3f8f7c-7aa9-4b72-b72d-9c6a7f6f0c31"
_INSTANCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_PORT_VERSION = re.compile(r"\.v[0-9]+$")
_ALLOWED_LEAVES = {
    "ValidateFrozenJob",
    "CheckSafetyHealthy",
    "CheckRequiredDevicesReady",
    "ClampKitTray",
    "LocateObject",
    "PickObject",
    "PlaceObject",
    "InspectObject",
    "VerifyKitTray",
    "ReleaseKitTray",
    "RecordKittingResult",
}
_REQUIRED_COMPONENTS = {
    "robot-001",
    "gripper-001",
    "camera-001",
    "kit-fixture-001",
    "source-carrier-001",
    "safety-status-001",
}


def _fail(where: str, message: str) -> NoReturn:
    raise ScenarioError(f"{where}: {message}")


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(where, "expected an object")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(where, "expected a non-blank string")
    return value.strip()


def _load_yaml(path: Path, where: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        _fail(where, f"cannot load YAML: {error}")
    return _mapping(value, where)


def _load_json(path: Path, where: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(where, f"cannot load JSON: {error}")
    return _mapping(value, where)


def _validate_json_schema(document: dict[str, Any], schema_path: Path, where: str) -> None:
    try:
        schema = _load_json(schema_path, f"{where}.schema")
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda error: (tuple(str(item) for item in error.absolute_path), error.message),
        )
    except SchemaError as error:
        _fail(str(schema_path), f"invalid Draft 2020-12 schema: {error.message}")
    if errors:
        first = errors[0]
        pointer = "/".join(str(item) for item in first.absolute_path)
        _fail(where, f"schema validation failed at '/{pointer}': {first.message}")


@dataclass(frozen=True, slots=True)
class ComponentBinding:
    """The manifest-resolved contract surface of one cell component instance."""

    instance_id: str
    component_id: str
    version: str
    usd_prim: str
    config: dict[str, Any]
    frames: frozenset[str]
    ports: dict[str, tuple[str, str]]
    capabilities: frozenset[str]
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class KittingProject:
    """Validated canonical kitting inputs used by the L0 executor and evidence writer."""

    root: Path
    cell_id: str
    tree_path: Path
    recipe_path: Path
    scene_path: Path
    components: dict[str, ComponentBinding]
    capability_documents: tuple[Path, ...]
    fault_catalogs: tuple[Path, ...]

    def resolve_port(self, component_id: str, port_id: str) -> tuple[str, str]:
        try:
            binding = self.components[component_id]
        except KeyError:
            _fail("behavior_tree", f"unknown component instance '{component_id}'")
        try:
            return binding.ports[port_id]
        except KeyError:
            _fail(
                "behavior_tree",
                f"component '{component_id}' does not declare software port '{port_id}'",
            )

    def has_frame(self, frame_id: str) -> bool:
        return any(frame_id in binding.frames for binding in self.components.values())


def _contract_from_port_type(value: Any, where: str) -> str:
    port_type = _text(value, where)
    contract = _PORT_VERSION.sub("", port_type)
    if contract == port_type:
        _fail(where, "software port type must end in a version such as '.v1'")
    return contract


def _manifest_documents(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    manifests: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted((root / "components").rglob("component.yaml")):
        document = _load_yaml(path, str(path))
        component = _mapping(document.get("component"), f"{path}.component")
        component_id = _text(component.get("id"), f"{path}.component.id")
        if component_id in manifests:
            _fail(str(path), f"duplicate component manifest for '{component_id}'")
        manifests[component_id] = (path, document)
    return manifests


def _capability_documents(root: Path) -> dict[tuple[str, str], Path]:
    documents: dict[tuple[str, str], Path] = {}
    schema_path = root.parent.parent / "schemas" / "capability-contract.schema.json"
    for path in sorted((root / "capabilities").glob("*.json")):
        document = _load_json(path, str(path))
        _validate_json_schema(document, schema_path, str(path))
        contract = _text(document.get("contract"), f"{path}.contract")
        version = _text(document.get("version"), f"{path}.version")
        key = (contract, version)
        if key in documents:
            _fail(str(path), f"duplicate capability contract '{contract}/{version}'")
        documents[key] = path
    return documents


def _fault_catalog_documents(root: Path) -> tuple[Path, ...]:
    schema_path = root.parent.parent / "schemas" / "fault-catalog.schema.json"
    paths = tuple(sorted((root / "fault_catalogs").glob("*.json")))
    if not paths:
        _fail(str(root / "fault_catalogs"), "no fault catalog documents found")
    for path in paths:
        document = _load_json(path, str(path))
        _validate_json_schema(document, schema_path, str(path))
    return paths


def _validate_tree(tree_path: Path, root: ElementTree.Element, project: KittingProject) -> None:
    def resolve(value: str, where: str) -> None:
        if value.startswith("{") and value.endswith("}"):
            return
        if not value.strip():
            _fail(where, "must be non-blank")

    def port(
        element: ElementTree.Element, component_key: str, port_key: str, expected: str
    ) -> None:
        component = _text(element.attrib.get(component_key), f"{tree_path}.{component_key}")
        port_id = _text(element.attrib.get(port_key), f"{tree_path}.{port_key}")
        contract, _endpoint = project.resolve_port(component, port_id)
        if contract != expected:
            _fail(
                str(tree_path),
                f"{component}.{port_id} resolves to '{contract}', expected '{expected}'",
            )

    def visit(element: ElementTree.Element) -> None:
        if element.tag == "Sequence":
            if not len(element):
                _fail(str(tree_path), "Sequence must contain at least one child")
            for child in element:
                visit(child)
            return
        if element.tag == "RetryUntilSuccessful":
            if len(element) != 1:
                _fail(str(tree_path), "RetryUntilSuccessful must contain one child")
            try:
                attempts = int(element.attrib.get("num_attempts", ""))
            except ValueError as error:
                raise ScenarioError(f"{tree_path}: retry count must be an integer") from error
            if attempts < 1:
                _fail(str(tree_path), "retry count must be positive")
            visit(element[0])
            return
        if element.tag not in _ALLOWED_LEAVES:
            _fail(str(tree_path), f"unsupported kitting node '{element.tag}'")
        for name, value in element.attrib.items():
            resolve(value, f"{tree_path}.{element.tag}.{name}")
        if element.tag == "LocateObject":
            port(element, "component", "port", "vision.locate_object")
            if not project.has_frame(_text(element.attrib.get("source_frame"), "source_frame")):
                _fail(str(tree_path), "LocateObject references an undeclared source frame")
        elif element.tag == "PickObject":
            port(element, "robot_component", "robot_port", "robot_motion.execute_trajectory")
            port(element, "gripper_component", "gripper_port", "gripper.close")
        elif element.tag == "PlaceObject":
            port(element, "robot_component", "robot_port", "robot_motion.execute_trajectory")
            port(element, "gripper_component", "gripper_port", "gripper.open")
            if not project.has_frame(
                _text(element.attrib.get("destination_frame"), "destination_frame")
            ):
                _fail(str(tree_path), "PlaceObject references an undeclared destination frame")
        elif element.tag == "InspectObject":
            port(element, "component", "port", "vision.inspect_object")
        elif element.tag == "ClampKitTray":
            port(element, "component", "port", "fixture.clamp")
        elif element.tag == "VerifyKitTray":
            port(element, "component", "port", "fixture.verify_seated")
        elif element.tag == "ReleaseKitTray":
            port(element, "component", "port", "fixture.release")

    visit(root)


def load_kitting_project(project_root: str | Path) -> KittingProject:
    """Validate and load the complete kitting graph, manifests, scene, tree, and recipe."""

    root = Path(project_root).resolve()
    cell_path = root / "cell.yaml"
    cell = _load_yaml(cell_path, str(cell_path))
    if cell.get("schema_version") != "0.1.0":
        _fail(str(cell_path), "schema_version must be '0.1.0'")
    cell_identity = _mapping(cell.get("cell"), f"{cell_path}.cell")
    cell_id = _text(cell_identity.get("id"), f"{cell_path}.cell.id")
    if cell_id != KITTING_CELL_ID:
        _fail(f"{cell_path}.cell.id", f"must be the canonical kitting ID '{KITTING_CELL_ID}'")
    scene = _mapping(cell.get("scene"), f"{cell_path}.scene")
    scene_path = (root / _text(scene.get("usd"), f"{cell_path}.scene.usd")).resolve()
    if root not in scene_path.parents or not scene_path.is_file():
        _fail(str(scene_path), "canonical scene must be an existing project-local file")
    try:
        scene_text = scene_path.read_text(encoding="utf-8")
    except OSError as error:
        _fail(str(scene_path), f"cannot read canonical scene: {error}")
    if 'def Xform "World"' not in scene_text:
        _fail(str(scene_path), "canonical scene must declare the /World prim")

    manifest_documents = _manifest_documents(root)
    capability_documents = _capability_documents(root)
    fault_catalogs = _fault_catalog_documents(root)
    raw_components = cell.get("components")
    if not isinstance(raw_components, list):
        _fail(f"{cell_path}.components", "expected a list")
    bindings: dict[str, ComponentBinding] = {}
    scene_instance_ids = re.findall(r'cellforge:instanceId\s*=\s*"([^"]+)"', scene_text)
    for index, raw in enumerate(raw_components):
        where = f"{cell_path}.components[{index}]"
        instance = _mapping(raw, where)
        instance_id = _text(instance.get("id"), f"{where}.id")
        if not _INSTANCE_ID.fullmatch(instance_id):
            _fail(f"{where}.id", "invalid component instance ID")
        if instance_id in bindings:
            _fail(f"{where}.id", f"duplicate component instance '{instance_id}'")
        component_id = _text(instance.get("component"), f"{where}.component")
        version = _text(instance.get("version"), f"{where}.version")
        manifest_path, manifest = manifest_documents.get(component_id, (Path(), {}))
        if not manifest_path:
            _fail(f"{where}.component", f"manifest not found for '{component_id}'")
        manifest_identity = _mapping(manifest.get("component"), f"{manifest_path}.component")
        if manifest_identity.get("version") != version:
            _fail(f"{where}.version", "does not match the component manifest version")
        config = _mapping(instance.get("config"), f"{where}.config")
        config_schema_value = manifest.get("config_schema")
        if config_schema_value is None:
            _fail(str(manifest_path), "component manifest must declare config_schema")
        config_schema = (
            manifest_path.parent / _text(config_schema_value, "config_schema")
        ).resolve()
        if root not in config_schema.parents or not config_schema.is_file():
            _fail(str(config_schema), "component config schema must be project-local")
        _validate_json_schema(config, config_schema, f"{where}.config")
        assets = _mapping(manifest.get("assets"), f"{manifest_path}.assets")
        for asset_name in ("visual_usd", "collision_usd"):
            asset = (manifest_path.parent / _text(assets.get(asset_name), asset_name)).resolve()
            if root not in asset.parents or not asset.is_file():
                _fail(str(asset), "component asset must be an existing project-local file")
        frames_raw = manifest.get("frames")
        if not isinstance(frames_raw, list):
            _fail(str(manifest_path), "frames must be a list")
        frames = frozenset(
            _text(_mapping(frame, "frame").get("id"), f"{manifest_path}.frames.id")
            for frame in frames_raw
        )
        ports_root = _mapping(manifest.get("ports"), f"{manifest_path}.ports")
        software_raw = ports_root.get("software")
        if not isinstance(software_raw, list):
            _fail(str(manifest_path), "ports.software must be a list")
        capabilities_raw = manifest.get("capabilities")
        if not isinstance(capabilities_raw, list):
            _fail(str(manifest_path), "capabilities must be a list")
        capability_map: dict[str, dict[str, Any]] = {}
        for capability_raw in capabilities_raw:
            capability = _mapping(capability_raw, f"{manifest_path}.capabilities")
            contract = _text(capability.get("contract"), "capability.contract")
            capability_map[contract] = capability
            definition = _text(capability.get("definition"), "capability.definition")
            expected = f"cellforge://capabilities/{contract}/{capability.get('version')}"
            if definition != expected:
                _fail(str(manifest_path), f"capability definition does not match '{expected}'")
            version_value = _text(capability.get("version"), "capability.version")
            if (contract, version_value) not in capability_documents:
                _fail(str(manifest_path), f"capability contract document missing for '{contract}'")
        ports: dict[str, tuple[str, str]] = {}
        for software in software_raw:
            port = _mapping(software, f"{manifest_path}.ports.software")
            port_id = _text(port.get("id"), "software port.id")
            contract = _contract_from_port_type(port.get("type"), f"{manifest_path}.{port_id}.type")
            endpoint = _text(
                capability_map.get(contract, {}).get("endpoint"), f"{port_id}.endpoint"
            )
            if port_id in ports:
                _fail(str(manifest_path), f"duplicate software port '{port_id}'")
            ports[port_id] = (contract, endpoint)
        usd_prim = _text(instance.get("usd_prim"), f"{where}.usd_prim")
        leaf = usd_prim.rstrip("/").split("/")[-1]
        if f'def Xform "{leaf}"' not in scene_text:
            _fail(str(scene_path), f"component '{instance_id}' prim '{usd_prim}' is absent")
        if scene_instance_ids.count(instance_id) != 1:
            _fail(
                str(scene_path), f"component '{instance_id}' must have exactly one scene identity"
            )
        bindings[instance_id] = ComponentBinding(
            instance_id=instance_id,
            component_id=component_id,
            version=version,
            usd_prim=usd_prim,
            config=config,
            frames=frames,
            ports=ports,
            capabilities=frozenset(capability_map),
            manifest_path=manifest_path,
        )
    missing_components = _REQUIRED_COMPONENTS - set(bindings)
    if missing_components:
        _fail(str(cell_path), f"missing required kitting components {sorted(missing_components)}")
    if set(scene_instance_ids) != set(bindings):
        _fail(str(scene_path), "scene instance IDs and cell component IDs do not match")

    tasks = cell.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        _fail(str(cell_path), "at least one task is required")
    task = next(
        (item for item in tasks if isinstance(item, dict) and item.get("id") == "tray_kitting"),
        None,
    )
    if not isinstance(task, dict):
        _fail(str(cell_path), "tray_kitting task is not declared")
    tree_path = (root / _text(task.get("behavior_tree"), "task.behavior_tree")).resolve()
    if root not in tree_path.parents or not tree_path.is_file():
        _fail(str(tree_path), "behavior tree must be an existing project-local file")
    recipes = cell.get("recipes")
    if not isinstance(recipes, list) or len(recipes) != 1:
        _fail(str(cell_path), "kitting project must declare exactly one recipe")
    recipe_binding = _mapping(recipes[0], f"{cell_path}.recipes[0]")
    recipe_path = (root / _text(recipe_binding.get("path"), "recipe.path")).resolve()
    if root not in recipe_path.parents or not recipe_path.is_file():
        _fail(str(recipe_path), "recipe must be an existing project-local file")
    recipe = _load_yaml(recipe_path, str(recipe_path))
    recipe_compatibility = _mapping(recipe.get("compatibility"), f"{recipe_path}.compatibility")
    if cell_id not in recipe_compatibility.get("cell_ids", []):
        _fail(str(recipe_path), "recipe is not compatible with the canonical kitting cell")
    declared_capabilities = set().union(
        *(set(binding.capabilities) for binding in bindings.values())
    )
    required_capabilities = set(recipe_compatibility.get("required_capabilities", []))
    required_capabilities.update(task.get("required_capabilities", []))
    missing_capabilities = required_capabilities - declared_capabilities
    if missing_capabilities:
        _fail(str(recipe_path), f"undeclared required capabilities {sorted(missing_capabilities)}")
    try:
        tree_root = ElementTree.parse(tree_path).getroot().find("BehaviorTree")
    except (OSError, ElementTree.ParseError) as error:
        _fail(str(tree_path), f"cannot load behavior tree: {error}")
    if tree_root is None or len(tree_root) != 1:
        _fail(str(tree_path), "expected one BehaviorTree child root")
    project = KittingProject(
        root=root,
        cell_id=cell_id,
        tree_path=tree_path,
        recipe_path=recipe_path,
        scene_path=scene_path,
        components=bindings,
        capability_documents=tuple(sorted(capability_documents.values())),
        fault_catalogs=fault_catalogs,
    )
    _validate_tree(tree_path, tree_root[0], project)
    return project


class KittingHeadlessExecutor:
    """Execute the canonical two-part kitting tree against generic L0 mock adapters."""

    def __init__(self, scenario: ScenarioDefinition, tree_path: Path, project_path: Path) -> None:
        self.scenario = scenario
        self.project = load_kitting_project(project_path)
        if tree_path.resolve() != self.project.tree_path:
            _fail(str(tree_path), "tree is not the canonical kitting task tree")
        self.tree_path = tree_path
        self.trace_id = str(uuid5(NAMESPACE_URL, f"cellforge:kitting:{scenario.seed}:trace"))
        self.events: list[TraceEvent] = []
        self.command_ordinal = 0
        self.job_started = False
        self._applied_faults: set[int] = set()
        self._tree_root = self._load_tree()
        self.blackboard = self._blackboard()
        self.adapters = self._adapters()

    def _blackboard(self) -> dict[str, Any]:
        job = self.scenario.job
        payload = _mapping(job.get("input_payload"), f"{self.scenario.source}.job.input_payload")
        kit_sku = _text(payload.get("kit_sku"), "input_payload.kit_sku")
        parts = payload.get("parts")
        if not isinstance(parts, list) or len(parts) != 2:
            _fail("input_payload.parts", "expected exactly two parts for the canonical kit")
        slots: set[str] = set()
        for index, raw in enumerate(parts):
            part = _mapping(raw, f"input_payload.parts[{index}]")
            _text(part.get("sku"), f"input_payload.parts[{index}].sku")
            slot = _text(part.get("slot"), f"input_payload.parts[{index}].slot")
            if slot in slots:
                _fail(f"input_payload.parts[{index}].slot", "slot assignments must be unique")
            slots.add(slot)
        recipe_version = job.get("recipe_version")
        if isinstance(recipe_version, bool) or not isinstance(recipe_version, int):
            _fail(f"{self.scenario.source}.job.recipe_version", "expected an integer")
        recipe_id = _text(job.get("recipe_id"), f"{self.scenario.source}.job.recipe_id")
        return {
            "job_id": str(uuid5(NAMESPACE_URL, f"cellforge:kitting:{self.scenario.seed}:job")),
            "cell_id": self.project.cell_id,
            "recipe_id": recipe_id,
            "recipe_version": recipe_version,
            "kit_sku": kit_sku,
            "input_payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":")),
            "execution_mode": "simulation",
            "cell_ready": bool(self.scenario.initial_state.get("safety_healthy", True)),
        }

    @staticmethod
    def _operation() -> dict[str, Any]:
        return {"duration_seconds": 0.001}

    def _adapters(self) -> dict[str, MockDeviceAdapter]:
        initial = self.scenario.initial_state
        documents: dict[str, dict[str, Any]] = {
            "robot": {
                "component_instance_id": "robot-001",
                "device_kind": "robot",
                "operations": {"robot_motion.action.execute_trajectory": self._operation()},
            },
            "gripper": {
                "component_instance_id": "gripper-001",
                "device_kind": "gripper",
                "operations": {
                    "gripper.action.open": self._operation(),
                    "gripper.action.close": self._operation(),
                },
                "device": {"jaw_initial": "open"},
            },
            "locator": {
                "component_instance_id": "camera-001",
                "device_kind": "vision_locator",
                "operations": {"vision.action.locate_object": self._operation()},
                "device": {
                    "object_present": bool(initial.get("parts_present", True)),
                    "object_id": "part-001",
                    "confidence": 0.99,
                    "pose": {"x": 0.0, "y": -0.25, "z": 0.83},
                },
            },
            "inspection": {
                "component_instance_id": "camera-001",
                "device_kind": "inspection",
                "operations": {"vision.action.inspect_object": self._operation()},
                "device": {
                    "accepted": bool(initial.get("inspection_passed", True)),
                    "measurements": {
                        "parts_in_slots": 2,
                        "slot_1": True,
                        "slot_2": True,
                    },
                },
            },
            "fixture": {
                "component_instance_id": "kit-fixture-001",
                "device_kind": "fixture",
                "operations": {
                    "fixture.action.clamp": self._operation(),
                    "fixture.action.release": self._operation(),
                    "fixture.action.verify_seated": self._operation(),
                },
                "device": {
                    "seated": bool(initial.get("kit_tray_seated", True)),
                    "clamped_initial": False,
                },
            },
        }
        adapters = {
            role: build_device_mock(parse_device_scenario(document, where=f"{role}_mock"))
            for role, document in documents.items()
        }
        for adapter in adapters.values():
            adapter.mark_ready()
        return adapters

    def _load_tree(self) -> ElementTree.Element:
        try:
            root = ElementTree.parse(self.tree_path).getroot()
        except (OSError, ElementTree.ParseError) as error:
            raise ScenarioError(f"{self.tree_path}: cannot load behavior tree: {error}") from error
        tree = root.find("BehaviorTree")
        if tree is None or len(tree) != 1:
            _fail(str(self.tree_path), "expected one BehaviorTree child root")
        return tree[0]

    def emit(
        self,
        event_type: str,
        *,
        node: str = "",
        component: str = "",
        command_id: str = "",
        result_code: str = "",
        outcome_certain: bool = True,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            TraceEvent(
                sequence=len(self.events) + 1,
                event_type=event_type,
                node=node,
                component_instance_id=component,
                command_id=command_id,
                result_code=result_code,
                outcome_certain=outcome_certain,
                evidence=evidence or {},
            )
        )

    def _resolve(self, value: str) -> Any:
        if value.startswith("{") and value.endswith("}"):
            key = value[1:-1]
            if key not in self.blackboard:
                _fail(str(self.tree_path), f"unresolved blackboard port '{key}'")
            return self.blackboard[key]
        return value

    def _ports(self, element: ElementTree.Element) -> dict[str, Any]:
        output_ports = {"output_pose", "output_object_id", "output"}
        return {
            name: value[1:-1]
            if name in output_ports and value.startswith("{") and value.endswith("}")
            else self._resolve(value)
            for name, value in element.attrib.items()
        }

    def _adapter_for(self, component_id: str, contract: str) -> MockDeviceAdapter:
        if component_id == "robot-001":
            return self.adapters["robot"]
        if component_id == "gripper-001":
            return self.adapters["gripper"]
        if component_id == "kit-fixture-001":
            return self.adapters["fixture"]
        if component_id == "camera-001" and contract == "vision.inspect_object":
            return self.adapters["inspection"]
        if component_id == "camera-001":
            return self.adapters["locator"]
        _fail("behavior_tree", f"no L0 adapter is selected for component '{component_id}'")

    def _apply_scheduled_fault(self, node: str) -> None:
        for index, raw in enumerate(self.scenario.faults):
            if index in self._applied_faults or raw.get("at") != f"before:{node}":
                continue
            target = _text(raw.get("target"), f"{self.scenario.source}.faults[{index}].target")
            fault = _text(raw.get("fault"), f"{self.scenario.source}.faults[{index}].fault")
            adapter = next(
                (
                    item
                    for item in self.adapters.values()
                    if item.scenario.component_instance_id == target
                ),
                None,
            )
            if adapter is None:
                _fail(f"{self.scenario.source}.faults[{index}]", f"unknown target '{target}'")
            try:
                adapter.inject_next_fault(fault)
            except ValueError as error:
                raise ScenarioError(
                    f"{self.scenario.source}.faults[{index}].fault: {error}"
                ) from error
            self._applied_faults.add(index)
            self.emit(
                "fault.injected",
                node=node,
                component=target,
                result_code=fault,
                evidence={"fault": fault, "recovery": raw.get("parameters", {}).get("recovery")},
            )

    async def command(
        self,
        node: str,
        component_id: str,
        port_id: str,
        payload: dict[str, Any],
    ) -> CommandResult:
        contract, endpoint = self.project.resolve_port(component_id, port_id)
        adapter = self._adapter_for(component_id, contract)
        capability = f"{contract.split('.', 1)[0]}.action.{endpoint}"
        self.command_ordinal += 1
        command_id = str(
            uuid5(
                NAMESPACE_URL,
                f"cellforge:kitting:{self.scenario.seed}:{self.command_ordinal}:{node}:{capability}",
            )
        )
        self.emit(
            "device.command.requested",
            node=node,
            component=component_id,
            command_id=command_id,
            evidence={"capability": contract, "port": port_id},
        )
        result = await adapter.execute(
            CapabilityCommand(
                command_id=command_id,
                trace_id=self.trace_id,
                capability=capability,
                input_payload_json=json.dumps(payload, sort_keys=True),
                timeout=timedelta(seconds=1),
            )
        )
        self.emit(
            result.result_code,
            node=node,
            component=component_id,
            command_id=command_id,
            result_code=result.result_code,
            outcome_certain=result.outcome_certain,
        )
        return result

    def _cancel_before(self, node: str) -> bool:
        return any(
            item.get("at") == f"before:{node}" and item.get("fault") == "operator_cancelled"
            for item in self.scenario.faults
        )

    async def _leaf(self, element: ElementTree.Element) -> NodeStatus:
        node = element.tag
        if self._cancel_before(node):
            self.emit("operator.cancelled", node=node)
            return NodeStatus.CANCELLED
        self._apply_scheduled_fault(node)
        self.emit("behavior_tree.node.entered", node=node)
        handler = getattr(self, f"node_{node}", None)
        if handler is None:
            _fail(str(self.tree_path), f"unsupported kitting node '{node}'")
        ports = self._ports(element)
        typed_handler = cast(Callable[[dict[str, Any]], Awaitable[NodeStatus]], handler)
        status = await typed_handler(ports)
        self.emit(
            "behavior_tree.node.completed",
            node=node,
            result_code=status.value,
            evidence={"status": status.value},
        )
        return status

    async def _execute_element(self, element: ElementTree.Element) -> NodeStatus:
        if element.tag == "Sequence":
            for child in element:
                status = await self._execute_element(child)
                if status is not NodeStatus.SUCCESS:
                    return status
            return NodeStatus.SUCCESS
        if element.tag == "RetryUntilSuccessful":
            attempts = int(element.attrib["num_attempts"])
            failed_once = False
            for attempt in range(attempts):
                status = await self._execute_element(element[0])
                if status is NodeStatus.SUCCESS:
                    if failed_once:
                        self.emit(
                            "fault.recovered",
                            node=element[0].tag,
                            evidence={"attempt": attempt + 1},
                        )
                    return status
                if status in {
                    NodeStatus.CANCELLED,
                    NodeStatus.OUTCOME_UNKNOWN,
                    NodeStatus.REJECTED,
                }:
                    return status
                failed_once = True
                if attempt + 1 < attempts:
                    for raw_fault in self.scenario.faults:
                        if (
                            raw_fault.get("at") == f"before:{element[0].tag}"
                            and isinstance(raw_fault.get("parameters"), dict)
                            and raw_fault["parameters"].get("recovery") == "retry"
                        ):
                            target = raw_fault.get("target")
                            for adapter in self.adapters.values():
                                if adapter.scenario.component_instance_id == target:
                                    adapter.mark_ready()
                                    self.emit(
                                        "recovery.adapter_ready",
                                        node=element[0].tag,
                                        component=str(target),
                                    )
                    self.emit(
                        "recovery.retry.requested",
                        node=element[0].tag,
                        evidence={"attempt": attempt + 1, "max_attempts": attempts},
                    )
            return NodeStatus.FAILURE
        return await self._leaf(element)

    async def node_ValidateFrozenJob(self, ports: dict[str, Any]) -> NodeStatus:
        required = (
            "job_id",
            "cell_id",
            "recipe_id",
            "recipe_version",
            "input_payload_json",
            "execution_mode",
        )
        return (
            NodeStatus.SUCCESS
            if all(ports.get(name) not in {None, ""} for name in required)
            else NodeStatus.REJECTED
        )

    async def node_CheckSafetyHealthy(self, ports: dict[str, Any]) -> NodeStatus:
        if not bool(ports.get("healthy")):
            self.emit("safety.unhealthy", node="CheckSafetyHealthy")
            return NodeStatus.REJECTED
        return NodeStatus.SUCCESS

    async def node_CheckRequiredDevicesReady(self, ports: dict[str, Any]) -> NodeStatus:
        if not bool(ports.get("ready")):
            self.emit("devices.not_ready", node="CheckRequiredDevicesReady")
            return NodeStatus.REJECTED
        self.job_started = True
        self.emit("job.started", node="CheckRequiredDevicesReady")
        return NodeStatus.SUCCESS

    async def node_ClampKitTray(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command("ClampKitTray", str(ports["component"]), str(ports["port"]), {})
        return NodeStatus.SUCCESS if result.success else NodeStatus.FAILURE

    async def node_LocateObject(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "LocateObject",
            str(ports["component"]),
            str(ports["port"]),
            {"object_type": ports["object_type"], "source_frame": ports["source_frame"]},
        )
        if not result.success:
            return NodeStatus.FAILURE
        index = int(ports["part_index"])
        pose = {"x": 0.2 + index * 0.1, "y": -0.25, "z": 0.83, "qx": 0, "qy": 0, "qz": 0, "qw": 1}
        self.blackboard[str(ports["output_pose"])] = pose
        self.blackboard[str(ports["output_object_id"])] = f"part-{index + 1:03}"
        self.emit(
            "part.located",
            node="LocateObject",
            component=str(ports["component"]),
            evidence={"part_index": index, "source_frame": ports["source_frame"]},
        )
        return NodeStatus.SUCCESS

    async def node_PickObject(self, ports: dict[str, Any]) -> NodeStatus:
        pose = ports.get("pose")
        if not isinstance(pose, dict):
            return NodeStatus.FAILURE
        motion = await self.command(
            "PickObject",
            str(ports["robot_component"]),
            str(ports["robot_port"]),
            {"trajectory": {"waypoints": [{"target_pose": pose, "operation": "pick"}]}},
        )
        if not motion.success:
            return NodeStatus.FAILURE
        grip = await self.command(
            "PickObject", str(ports["gripper_component"]), str(ports["gripper_port"]), {}
        )
        if grip.success:
            self.emit("part.picked", node="PickObject", evidence={"object_id": ports["object_id"]})
        return NodeStatus.SUCCESS if grip.success else NodeStatus.FAILURE

    async def node_PlaceObject(self, ports: dict[str, Any]) -> NodeStatus:
        motion = await self.command(
            "PlaceObject",
            str(ports["robot_component"]),
            str(ports["robot_port"]),
            {
                "trajectory": {
                    "waypoints": [
                        {"target_frame": ports["destination_frame"], "operation": "place"}
                    ]
                }
            },
        )
        if not motion.success:
            return NodeStatus.FAILURE
        grip = await self.command(
            "PlaceObject", str(ports["gripper_component"]), str(ports["gripper_port"]), {}
        )
        if grip.success:
            self.emit(
                "part.placed",
                node="PlaceObject",
                evidence={
                    "object_id": ports["object_id"],
                    "destination": ports["destination_frame"],
                },
            )
        return NodeStatus.SUCCESS if grip.success else NodeStatus.FAILURE

    async def node_InspectObject(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "InspectObject",
            str(ports["component"]),
            str(ports["port"]),
            {"inspection_profile": ports["profile"], "expected": json.loads(ports["expected"])},
        )
        if not result.success:
            return NodeStatus.FAILURE
        output = json.loads(result.output_payload_json)
        self.blackboard[str(ports["output"])] = output
        accepted = bool(output.get("accepted"))
        self.emit(
            "inspection.accepted" if accepted else "inspection.rejected", node="InspectObject"
        )
        return NodeStatus.SUCCESS if accepted else NodeStatus.FAILURE

    async def node_VerifyKitTray(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "VerifyKitTray", str(ports["component"]), str(ports["port"]), {}
        )
        return NodeStatus.SUCCESS if result.success else NodeStatus.FAILURE

    async def node_ReleaseKitTray(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "ReleaseKitTray", str(ports["component"]), str(ports["port"]), {}
        )
        return NodeStatus.SUCCESS if result.success else NodeStatus.FAILURE

    async def node_RecordKittingResult(self, ports: dict[str, Any]) -> NodeStatus:
        self.emit("kitting.result.recorded", node="RecordKittingResult")
        return NodeStatus.SUCCESS

    async def execute(self) -> ScenarioResult:
        self.emit("job.accepted", evidence={"trace_id": self.trace_id, "seed": self.scenario.seed})
        try:
            status = await asyncio.wait_for(
                self._execute_element(self._tree_root), timeout=self.scenario.timeout_seconds
            )
        except TimeoutError:
            status = NodeStatus.FAILURE
            self.emit("scenario.timeout")
        if status is NodeStatus.SUCCESS:
            final_status = "SUCCESS"
            self.emit("job.completed")
        elif status is NodeStatus.CANCELLED:
            final_status = "CANCELLED"
            self.emit("job.cancelled")
        elif status is NodeStatus.REJECTED:
            final_status = "REJECTED"
            self.emit("job.rejected")
        else:
            final_status = "RECOVERABLE_FAULT"
            self.emit("job.failed")
        event_types = [event.event_type for event in self.events]
        failures: list[str] = []
        if final_status != self.scenario.expected_status:
            failures.append(
                f"expected final status {self.scenario.expected_status}, got {final_status}"
            )
        for required in self.scenario.required_events:
            if required not in event_types:
                failures.append(f"required event missing: {required}")
        for forbidden in self.scenario.forbidden_events:
            if forbidden in event_types:
                failures.append(f"forbidden event present: {forbidden}")
        return ScenarioResult(
            scenario_id=self.scenario.scenario_id,
            name=self.scenario.name,
            seed=self.scenario.seed,
            final_status=final_status,
            passed=not failures,
            failures=tuple(failures),
            trace=tuple(self.events),
            fidelity=(
                "L0 contract mock: reusable kitting sequencing and adapter outcomes only; no "
                "geometry, kinematics, contact, rendered perception, hardware, process-quality, "
                "or functional-safety evidence."
            ),
        )


async def run_kitting_scenario(
    scenario: ScenarioDefinition, tree_path: Path, project_path: Path
) -> ScenarioResult:
    """Execute one validated kitting scenario through the shared L0 adapter contracts."""

    return await KittingHeadlessExecutor(scenario, tree_path, project_path).execute()
