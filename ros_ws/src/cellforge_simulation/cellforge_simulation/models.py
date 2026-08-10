"""Strict, ROS-free simulation scenario and registration models."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, NoReturn

import yaml

SCHEMA_VERSION = "0.1.0"
_INSTANCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_]*(?:[.]?[a-z][a-z0-9_]*)+$")
_ALLOWED_TOP_LEVEL = {
    "schema_version",
    "scenario",
    "simulation",
    "job",
    "initial_state",
    "randomization",
    "faults",
    "assertions",
}


class ScenarioValidationError(ValueError):
    """A stable scenario or adapter-registration validation failure."""


class FidelityLevel(IntEnum):
    """Declared simulation fidelity, ordered from contract-only to perception."""

    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3

    @classmethod
    def parse(cls, value: object, where: str) -> FidelityLevel:
        if not isinstance(value, str):
            raise ScenarioValidationError(f"{where}: expected one of L0, L1, L2, L3")
        try:
            return cls[value.upper()]
        except KeyError as error:
            raise ScenarioValidationError(
                f"{where}: unsupported fidelity '{value}'; expected one of L0, L1, L2, L3"
            ) from error

    def label(self) -> str:
        return self.name


class SimulationState(StrEnum):
    STOPPED = "STOPPED"
    CONFIGURED = "CONFIGURED"
    PAUSED = "PAUSED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class UniformDistribution:
    minimum: float
    maximum: float


@dataclass(frozen=True, slots=True)
class FaultDefinition:
    at: str
    target: str
    fault: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ScenarioAssertions:
    final_status: str
    required_events: tuple[str, ...]
    forbidden_events: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    scenario_id: str
    name: str
    seed: int
    timeout_seconds: float
    requested_fidelity: FidelityLevel
    initial_state: dict[str, Any]
    randomization: dict[str, UniformDistribution]
    faults: tuple[FaultDefinition, ...]
    assertions: ScenarioAssertions
    source: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class AdapterRegistration:
    component_instance_id: str
    capabilities: tuple[str, ...]
    fidelity: FidelityLevel
    endpoint: str
    fault_codes: tuple[str, ...]

    @classmethod
    def create(
        cls,
        component_instance_id: str,
        capabilities: tuple[str, ...] | list[str],
        fidelity: FidelityLevel | str,
        endpoint: str,
        fault_codes: tuple[str, ...] | list[str] = (),
    ) -> AdapterRegistration:
        instance_id = component_instance_id.strip()
        if not _INSTANCE_ID.fullmatch(instance_id):
            raise ScenarioValidationError(
                "adapter.component_instance_id: expected a stable lowercase instance ID"
            )
        normalized = tuple(sorted(set(capability.strip() for capability in capabilities)))
        if not normalized or any(not _CAPABILITY_ID.fullmatch(item) for item in normalized):
            raise ScenarioValidationError(
                "adapter.capabilities: expected one or more canonical capability IDs"
            )
        endpoint_value = endpoint.strip()
        if not endpoint_value.startswith("/") or " " in endpoint_value:
            raise ScenarioValidationError("adapter.endpoint: expected an absolute ROS 2 name")
        parsed_fidelity = (
            fidelity
            if isinstance(fidelity, FidelityLevel)
            else FidelityLevel.parse(fidelity, "adapter.fidelity")
        )
        normalized_faults = tuple(sorted(set(item.strip() for item in fault_codes)))
        if any(not item or " " in item for item in normalized_faults):
            raise ScenarioValidationError(
                "adapter.fault_codes: expected stable non-blank codes without spaces"
            )
        return cls(instance_id, normalized, parsed_fidelity, endpoint_value, normalized_faults)


@dataclass(frozen=True, slots=True)
class CanonicalProject:
    root: str
    cell_id: str
    cell_path: str
    cell_sha256: str
    scene_path: str
    scene_sha256: str
    required_adapter_ids: tuple[str, ...]


def _fail(where: str, message: str) -> NoReturn:
    raise ScenarioValidationError(f"{where}: {message}")


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(where, "expected an object")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(where, "expected a non-blank string")
    return value.strip()


def _string_list(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        _fail(where, "expected a list of non-blank strings")
    return tuple(item.strip() for item in value)


def parse_scenario(document: Any, *, source: str, source_sha256: str) -> ScenarioDefinition:
    root = _mapping(document, source)
    unknown = sorted(set(root) - _ALLOWED_TOP_LEVEL)
    if unknown:
        _fail(source, f"unknown top-level keys {unknown}")
    if root.get("schema_version") != SCHEMA_VERSION:
        _fail(source, f"schema_version must be '{SCHEMA_VERSION}'")

    identity = _mapping(root.get("scenario"), f"{source}.scenario")
    seed = identity.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        _fail(f"{source}.scenario.seed", "expected a non-negative integer")
    timeout = identity.get("timeout_seconds", 60)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0:
        _fail(f"{source}.scenario.timeout_seconds", "expected a positive number")

    simulation = root.get("simulation", {})
    simulation = _mapping(simulation, f"{source}.simulation")
    unknown_simulation = sorted(set(simulation) - {"requested_fidelity"})
    if unknown_simulation:
        _fail(f"{source}.simulation", f"unknown keys {unknown_simulation}")
    requested_fidelity = FidelityLevel.parse(
        simulation.get("requested_fidelity", "L0"), f"{source}.simulation.requested_fidelity"
    )

    initial_state = _mapping(root.get("initial_state"), f"{source}.initial_state")
    randomization_raw = _mapping(root.get("randomization", {}), f"{source}.randomization")
    randomization: dict[str, UniformDistribution] = {}
    for key in sorted(randomization_raw):
        if not isinstance(key, str) or not key.strip():
            _fail(f"{source}.randomization", "keys must be non-blank strings")
        value = _mapping(randomization_raw[key], f"{source}.randomization.{key}")
        if set(value) != {"distribution", "min", "max"} or value.get("distribution") != "uniform":
            _fail(
                f"{source}.randomization.{key}",
                "expected exactly distribution: uniform, min, and max",
            )
        minimum = value["min"]
        maximum = value["max"]
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int | float)
            or not isinstance(maximum, int | float)
            or float(minimum) > float(maximum)
        ):
            _fail(f"{source}.randomization.{key}", "expected numeric min <= max")
        randomization[key] = UniformDistribution(float(minimum), float(maximum))

    faults_raw = root.get("faults", [])
    if not isinstance(faults_raw, list):
        _fail(f"{source}.faults", "expected a list")
    faults: list[FaultDefinition] = []
    for index, raw in enumerate(faults_raw):
        where = f"{source}.faults[{index}]"
        item = _mapping(raw, where)
        if set(item) != {"at", "target", "fault", "parameters"}:
            _fail(where, "expected exactly at, target, fault, and parameters")
        target = _text(item.get("target"), f"{where}.target")
        if not _INSTANCE_ID.fullmatch(target):
            _fail(f"{where}.target", "expected a stable lowercase instance ID")
        faults.append(
            FaultDefinition(
                at=_text(item.get("at"), f"{where}.at"),
                target=target,
                fault=_text(item.get("fault"), f"{where}.fault"),
                parameters=_mapping(item.get("parameters"), f"{where}.parameters"),
            )
        )

    assertions_raw = _mapping(root.get("assertions"), f"{source}.assertions")
    assertions = ScenarioAssertions(
        final_status=_text(assertions_raw.get("final_status"), f"{source}.assertions.final_status"),
        required_events=_string_list(
            assertions_raw.get("required_events", []),
            f"{source}.assertions.required_events",
        ),
        forbidden_events=_string_list(
            assertions_raw.get("forbidden_events", []),
            f"{source}.assertions.forbidden_events",
        ),
    )
    return ScenarioDefinition(
        scenario_id=_text(identity.get("id"), f"{source}.scenario.id"),
        name=_text(identity.get("name"), f"{source}.scenario.name"),
        seed=seed,
        timeout_seconds=float(timeout),
        requested_fidelity=requested_fidelity,
        initial_state=dict(initial_state),
        randomization=randomization,
        faults=tuple(faults),
        assertions=assertions,
        source=source,
        source_sha256=source_sha256,
    )


def load_scenario(path: Path) -> ScenarioDefinition:
    try:
        source_bytes = path.read_bytes()
        document = yaml.safe_load(source_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ScenarioValidationError(f"{path}: cannot load scenario: {error}") from error
    return parse_scenario(
        document,
        source=str(path),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )


def load_canonical_project(project_root: Path, scenario_path: Path) -> CanonicalProject:
    """Resolve scenario/control inputs from canonical cell.yaml and its referenced USD scene."""

    root = project_root.resolve()
    cell_path = root / "cell.yaml"
    try:
        cell_bytes = cell_path.read_bytes()
        document = yaml.safe_load(cell_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ScenarioValidationError(
            f"{cell_path}: cannot load canonical cell graph: {error}"
        ) from error
    cell = _mapping(document, str(cell_path))
    identity = _mapping(cell.get("cell"), f"{cell_path}.cell")
    scene = _mapping(cell.get("scene"), f"{cell_path}.scene")
    scene_value = _text(scene.get("usd"), f"{cell_path}.scene.usd")
    scene_path = (root / scene_value).resolve()
    if root not in scene_path.parents:
        _fail(f"{cell_path}.scene.usd", "scene must remain inside the project")
    try:
        scene_bytes = scene_path.read_bytes()
    except OSError as error:
        raise ScenarioValidationError(
            f"{scene_path}: cannot load canonical USD scene: {error}"
        ) from error

    selected_scenario = scenario_path.resolve()
    if root not in selected_scenario.parents:
        _fail(str(selected_scenario), "scenario must remain inside the project")
    declared_scenarios = cell.get("scenarios", [])
    if not isinstance(declared_scenarios, list) or not all(
        isinstance(item, str) for item in declared_scenarios
    ):
        _fail(f"{cell_path}.scenarios", "expected a list of project-relative paths")
    declared_paths = {(root / item).resolve() for item in declared_scenarios}
    if selected_scenario not in declared_paths:
        _fail(str(selected_scenario), "scenario is not declared by canonical cell.yaml")

    components = cell.get("components")
    if not isinstance(components, list):
        _fail(f"{cell_path}.components", "expected a list")
    required: list[str] = []
    for index, raw in enumerate(components):
        component = _mapping(raw, f"{cell_path}.components[{index}]")
        instance_id = _text(component.get("id"), f"{cell_path}.components[{index}].id")
        config = _mapping(component.get("config", {}), f"{cell_path}.components[{index}].config")
        if config.get("modeled_only") is True:
            continue
        if not _INSTANCE_ID.fullmatch(instance_id):
            _fail(f"{cell_path}.components[{index}].id", "invalid component instance ID")
        required.append(instance_id)
    if not required:
        _fail(f"{cell_path}.components", "no executable simulation adapter instances found")
    if len(required) != len(set(required)):
        _fail(f"{cell_path}.components", "duplicate component instance IDs")
    return CanonicalProject(
        root=str(root),
        cell_id=_text(identity.get("id"), f"{cell_path}.cell.id"),
        cell_path=str(cell_path),
        cell_sha256=hashlib.sha256(cell_bytes).hexdigest(),
        scene_path=str(scene_path),
        scene_sha256=hashlib.sha256(scene_bytes).hexdigest(),
        required_adapter_ids=tuple(sorted(required)),
    )
