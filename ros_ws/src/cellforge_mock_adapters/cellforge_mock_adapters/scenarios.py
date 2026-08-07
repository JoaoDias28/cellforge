"""Strict scenario configuration parsing for the L0 contract mock adapters.

A scenario document is JSON so the ROS node edge needs no extra dependencies. Every value is
validated eagerly: unknown keys, unknown capabilities, non-positive durations, and fault codes
outside the device catalog are configuration errors, never silent no-ops.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn

TEST_HOOK_CAPABILITY = "sdk.test.execute"
TEST_HOOK_FAULT = "sdk.test.injected_fault"

SCENARIO_SCHEMA_VERSION = "0.1.0"
INSTANCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
NODE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_OPERATION_DURATION_SECONDS = 600.0


class DeviceKind(StrEnum):
    """The six L0 mock device families required by the reference cell."""

    ROBOT = "robot"
    GRIPPER = "gripper"
    FIXTURE = "fixture"
    VISION_LOCATOR = "vision_locator"
    PROCESS_MACHINE = "process_machine"
    INSPECTION = "inspection"


DEVICE_CAPABILITIES: dict[DeviceKind, frozenset[str]] = {
    DeviceKind.ROBOT: frozenset({"robot_motion.action.execute_trajectory"}),
    DeviceKind.GRIPPER: frozenset({"gripper.action.open", "gripper.action.close"}),
    DeviceKind.FIXTURE: frozenset(
        {"fixture.action.clamp", "fixture.action.release", "fixture.action.verify_seated"}
    ),
    DeviceKind.VISION_LOCATOR: frozenset({"vision.action.locate_object"}),
    DeviceKind.PROCESS_MACHINE: frozenset(
        {"process.action.select_program", "process.action.execute_cycle"}
    ),
    DeviceKind.INSPECTION: frozenset({"vision.action.inspect_object"}),
}

DEVICE_FAULT_CATALOGS: dict[DeviceKind, frozenset[str]] = {
    DeviceKind.ROBOT: frozenset(
        {
            "robot.motion.planning_failed",
            "robot.motion.execution_failed",
            "robot.motion.protective_stop",
            "robot.communication.lost",
        }
    ),
    DeviceKind.GRIPPER: frozenset(
        {
            "gripper.motion.open_failed",
            "gripper.motion.close_failed",
            "gripper.object.dropped",
        }
    ),
    DeviceKind.FIXTURE: frozenset(
        {
            "fixture.motion.clamp_failed",
            "fixture.motion.release_failed",
            "fixture.sensor.seating_failed",
        }
    ),
    DeviceKind.VISION_LOCATOR: frozenset(
        {
            "camera.communication.unavailable",
            "camera.image.stale",
            "vision.object.not_found",
            "vision.pose.correction_limit",
        }
    ),
    DeviceKind.PROCESS_MACHINE: frozenset(
        {
            "laser.communication.timeout",
            "laser.program.not_found",
            "laser.process.interlock_not_ready",
            "laser.process.timeout",
            "laser.process.outcome_unknown",
        }
    ),
    DeviceKind.INSPECTION: frozenset(
        {
            "camera.communication.unavailable",
            "camera.image.stale",
            "vision.inspection.measurement_invalid",
        }
    ),
}

# Catalog codes that report an explicitly uncertain outcome instead of a certain device fault.
UNCERTAIN_FAULT_CODES: frozenset[str] = frozenset({"laser.process.outcome_unknown"})


class ScenarioConfigError(ValueError):
    """Raised when a mock scenario document fails strict validation."""


@dataclass(frozen=True, slots=True)
class OperationBehavior:
    """Configured timing and optional injected fault for one capability operation."""

    capability: str
    duration_seconds: float
    fault: str | None = None


@dataclass(frozen=True, slots=True)
class RobotData:
    """The robot mock needs no extra deterministic data."""


@dataclass(frozen=True, slots=True)
class GripperData:
    jaw_initial: str = "open"


@dataclass(frozen=True, slots=True)
class FixtureData:
    seated: bool = True
    clamped_initial: bool = False


@dataclass(frozen=True, slots=True)
class PoseData:
    """Deterministic pose reported by the vision locator mock."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0

    def as_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "qx": self.qx,
            "qy": self.qy,
            "qz": self.qz,
            "qw": self.qw,
        }


@dataclass(frozen=True, slots=True)
class VisionData:
    object_present: bool = True
    within_correction_limit: bool = True
    object_id: str = "pen-001"
    confidence: float = 0.99
    pose: PoseData = field(default_factory=PoseData)


@dataclass(frozen=True, slots=True)
class ProcessData:
    known_programs: tuple[str, ...] = ()
    interlock_permitted: bool = True
    verification_passed: bool = True


@dataclass(frozen=True, slots=True)
class InspectionData:
    accepted: bool = True
    measurements: dict[str, Any] = field(
        default_factory=lambda: {"contrast": 0.9, "text_match": True}
    )


DeviceData = RobotData | GripperData | FixtureData | VisionData | ProcessData | InspectionData


@dataclass(frozen=True, slots=True)
class DeviceScenario:
    """One fully validated mock device configuration."""

    device_kind: DeviceKind
    component_instance_id: str
    operations: dict[str, OperationBehavior]
    restart: str = "ready"
    device: DeviceData = field(default_factory=RobotData)


def _fail(where: str, message: str) -> NoReturn:
    raise ScenarioConfigError(f"{where}: {message}")


def _check_keys(data: dict[str, Any], allowed: set[str], required: set[str], where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail(where, f"unknown configuration keys {unknown}")
    missing = sorted(required - set(data))
    if missing:
        _fail(where, f"missing required configuration keys {missing}")


def _as_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        _fail(where, f"expected a boolean, got {type(value).__name__}")
    return value


def _as_number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        _fail(where, f"expected a number, got {type(value).__name__}")
    return float(value)


def _as_text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(where, "expected a non-blank string")
    return value


def _parse_operations(kind: DeviceKind, raw: Any, where: str) -> dict[str, OperationBehavior]:
    if not isinstance(raw, dict):
        _fail(where, f"'operations' must be an object, got {type(raw).__name__}")
    allowed_capabilities = DEVICE_CAPABILITIES[kind] | {TEST_HOOK_CAPABILITY}
    catalog = DEVICE_FAULT_CATALOGS[kind] | {TEST_HOOK_FAULT}
    behaviors: dict[str, OperationBehavior] = {}
    for capability, spec in raw.items():
        entry = f"{where}.operations.{capability}"
        if capability not in allowed_capabilities:
            _fail(
                entry,
                f"capability is not declared for device kind '{kind}'; "
                f"supported: {sorted(allowed_capabilities)}",
            )
        if not isinstance(spec, dict):
            _fail(entry, f"operation behavior must be an object, got {type(spec).__name__}")
        _check_keys(spec, {"duration_seconds", "fault"}, {"duration_seconds"}, entry)
        duration = _as_number(spec["duration_seconds"], f"{entry}.duration_seconds")
        if duration <= 0.0 or duration > MAX_OPERATION_DURATION_SECONDS:
            _fail(
                f"{entry}.duration_seconds",
                f"must be in (0, {MAX_OPERATION_DURATION_SECONDS}], got {duration}",
            )
        fault = spec.get("fault")
        if fault is not None:
            if not isinstance(fault, str):
                _fail(f"{entry}.fault", f"fault code must be a string, got {type(fault).__name__}")
            if fault not in catalog:
                _fail(
                    f"{entry}.fault",
                    f"fault code '{fault}' is not in the '{kind}' catalog; "
                    f"supported: {sorted(catalog)}",
                )
        behaviors[capability] = OperationBehavior(
            capability=capability, duration_seconds=duration, fault=fault
        )
    return behaviors


def _parse_pose(raw: Any, where: str) -> PoseData:
    if not isinstance(raw, dict):
        _fail(where, f"'pose' must be an object, got {type(raw).__name__}")
    fields = {"x", "y", "z", "qx", "qy", "qz", "qw"}
    _check_keys(raw, fields, set(), where)
    values = {name: _as_number(raw[name], f"{where}.{name}") for name in raw}
    return PoseData(**values)


def _parse_device_data(kind: DeviceKind, raw: Any, where: str) -> DeviceData:
    if raw is None:
        if kind is DeviceKind.PROCESS_MACHINE:
            return ProcessData()
        if kind is DeviceKind.GRIPPER:
            return GripperData()
        if kind is DeviceKind.FIXTURE:
            return FixtureData()
        if kind is DeviceKind.VISION_LOCATOR:
            return VisionData()
        if kind is DeviceKind.INSPECTION:
            return InspectionData()
        return RobotData()
    if not isinstance(raw, dict):
        _fail(where, f"'device' must be an object, got {type(raw).__name__}")
    section = f"{where}.device"
    if kind is DeviceKind.ROBOT:
        _check_keys(raw, set(), set(), section)
        return RobotData()
    if kind is DeviceKind.GRIPPER:
        _check_keys(raw, {"jaw_initial"}, set(), section)
        jaw = raw.get("jaw_initial", "open")
        if jaw not in {"open", "closed"}:
            _fail(f"{section}.jaw_initial", f"must be 'open' or 'closed', got '{jaw}'")
        return GripperData(jaw_initial=jaw)
    if kind is DeviceKind.FIXTURE:
        _check_keys(raw, {"seated", "clamped_initial"}, set(), section)
        return FixtureData(
            seated=_as_bool(raw.get("seated", True), f"{section}.seated"),
            clamped_initial=_as_bool(
                raw.get("clamped_initial", False), f"{section}.clamped_initial"
            ),
        )
    if kind is DeviceKind.VISION_LOCATOR:
        _check_keys(
            raw,
            {"object_present", "within_correction_limit", "object_id", "confidence", "pose"},
            set(),
            section,
        )
        confidence = _as_number(raw.get("confidence", 0.99), f"{section}.confidence")
        if not 0.0 < confidence <= 1.0:
            _fail(f"{section}.confidence", f"must be in (0, 1], got {confidence}")
        return VisionData(
            object_present=_as_bool(raw.get("object_present", True), f"{section}.object_present"),
            within_correction_limit=_as_bool(
                raw.get("within_correction_limit", True), f"{section}.within_correction_limit"
            ),
            object_id=_as_text(raw.get("object_id", "pen-001"), f"{section}.object_id"),
            confidence=confidence,
            pose=_parse_pose(raw.get("pose", {}), section),
        )
    if kind is DeviceKind.PROCESS_MACHINE:
        _check_keys(
            raw,
            {"known_programs", "interlock_permitted", "verification_passed"},
            set(),
            section,
        )
        programs_raw = raw.get("known_programs", [])
        if not isinstance(programs_raw, list) or not all(
            isinstance(item, str) and item.strip() for item in programs_raw
        ):
            _fail(f"{section}.known_programs", "must be a list of non-blank strings")
        return ProcessData(
            known_programs=tuple(programs_raw),
            interlock_permitted=_as_bool(
                raw.get("interlock_permitted", True), f"{section}.interlock_permitted"
            ),
            verification_passed=_as_bool(
                raw.get("verification_passed", True), f"{section}.verification_passed"
            ),
        )
    _check_keys(raw, {"accepted", "measurements"}, set(), section)
    measurements = raw.get("measurements", {"contrast": 0.9, "text_match": True})
    if not isinstance(measurements, dict):
        _fail(
            f"{section}.measurements",
            f"must be an object, got {type(measurements).__name__}",
        )
    try:
        json.dumps(measurements)
    except (TypeError, ValueError) as error:
        _fail(f"{section}.measurements", f"must be JSON-serializable: {error}")
    return InspectionData(
        accepted=_as_bool(raw.get("accepted", True), f"{section}.accepted"),
        measurements=dict(measurements),
    )


def parse_device_scenario(data: dict[str, Any], *, where: str = "scenario") -> DeviceScenario:
    """Parse and strictly validate one device scenario mapping."""

    if not isinstance(data, dict):
        _fail(where, f"device scenario must be an object, got {type(data).__name__}")
    _check_keys(
        data,
        {"component_instance_id", "device_kind", "restart", "operations", "device"},
        {"component_instance_id", "device_kind", "operations"},
        where,
    )
    instance_id = _as_text(data["component_instance_id"], f"{where}.component_instance_id")
    if not INSTANCE_ID_PATTERN.fullmatch(instance_id):
        _fail(
            f"{where}.component_instance_id",
            f"must match {INSTANCE_ID_PATTERN.pattern}, got '{instance_id}'",
        )
    kind_raw = data["device_kind"]
    try:
        kind = DeviceKind(kind_raw)
    except ValueError:
        _fail(
            f"{where}.device_kind",
            f"must be one of {[item.value for item in DeviceKind]}, got '{kind_raw}'",
        )
    restart = data.get("restart", "ready")
    if restart not in {"ready", "uncertain"}:
        _fail(f"{where}.restart", f"must be 'ready' or 'uncertain', got '{restart}'")
    return DeviceScenario(
        device_kind=kind,
        component_instance_id=instance_id,
        operations=_parse_operations(kind, data["operations"], where),
        restart=restart,
        device=_parse_device_data(kind, data.get("device"), where),
    )


def parse_scenario_document(text: str) -> dict[str, DeviceScenario]:
    """Parse a complete mock-cell scenario document keyed by ROS node name."""

    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as error:
        raise ScenarioConfigError(f"scenario document is not valid JSON: {error}") from error
    if not isinstance(decoded, dict):
        _fail("document", f"must be an object, got {type(decoded).__name__}")
    _check_keys(decoded, {"schema_version", "nodes"}, {"schema_version", "nodes"}, "document")
    version = decoded["schema_version"]
    if version != SCENARIO_SCHEMA_VERSION:
        _fail(
            "document.schema_version",
            f"must be '{SCENARIO_SCHEMA_VERSION}', got '{version}'",
        )
    nodes = decoded["nodes"]
    if not isinstance(nodes, dict) or not nodes:
        _fail("document.nodes", "must be an object declaring at least one node")
    scenarios: dict[str, DeviceScenario] = {}
    for node_name, node_data in nodes.items():
        if not isinstance(node_name, str) or not NODE_NAME_PATTERN.fullmatch(node_name):
            _fail(
                "document.nodes",
                f"node name '{node_name}' must match {NODE_NAME_PATTERN.pattern}",
            )
        scenarios[node_name] = parse_device_scenario(node_data, where=f"nodes.{node_name}")
    return scenarios


def load_scenario_file(path: Path) -> dict[str, DeviceScenario]:
    """Load and validate a mock-cell scenario document from disk."""

    return parse_scenario_document(path.read_text(encoding="utf-8"))
