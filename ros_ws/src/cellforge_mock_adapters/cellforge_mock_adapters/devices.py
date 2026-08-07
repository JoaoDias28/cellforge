"""The six L0 contract mock devices and their generic contract-suite factories.

Each mock owns only device-specific payload validation, deterministic output data, and declared
fault-catalog behavior; lifecycle, timing, cancellation, timeout, and state publication come from
``core.MockDeviceAdapter`` and the Task 008 SDK. The ``sdk.test.execute`` capability and
``sdk.test.injected_fault`` code are an explicit, documented test hook used solely by the generic
adapter contract suite.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cellforge_device_sdk.contract import ContractAdapterFactory, ContractScenario
from cellforge_device_sdk.models import (
    CapabilityCommand,
    CommandResult,
    DeviceOperationFault,
    DeviceStateSnapshot,
    Fault,
)

from cellforge_mock_adapters.core import MockDeviceAdapter, success_result
from cellforge_mock_adapters.scenarios import (
    DEVICE_CAPABILITIES,
    TEST_HOOK_CAPABILITY,
    TEST_HOOK_FAULT,
    DeviceKind,
    DeviceScenario,
    FixtureData,
    GripperData,
    InspectionData,
    ProcessData,
    ScenarioConfigError,
    VisionData,
    parse_device_scenario,
)


def _invalid(message: str) -> Fault:
    return Fault(code="sdk.command.invalid_input", message=message)


def _require_text(payload: dict[str, Any], key: str) -> str | Fault:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return _invalid(f"'{key}' must be a non-blank string.")
    return value


class MockRobotMotionAdapter(MockDeviceAdapter):
    """L0 mock for ``robot_motion.execute_trajectory``."""

    def __init__(
        self,
        scenario: DeviceScenario,
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
    ) -> None:
        if scenario.device_kind is not DeviceKind.ROBOT:
            raise ScenarioConfigError("robot mock requires a 'robot' device scenario")
        super().__init__(scenario, state_sink=state_sink)

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        if capability == TEST_HOOK_CAPABILITY:
            return None
        trajectory = payload.get("trajectory")
        if not isinstance(trajectory, dict):
            return _invalid("'trajectory' must be an object with a non-empty 'waypoints' list.")
        waypoints = trajectory.get("waypoints")
        if (
            not isinstance(waypoints, list)
            or not waypoints
            or not all(isinstance(point, dict) for point in waypoints)
        ):
            return _invalid("'trajectory.waypoints' must be a non-empty list of pose objects.")
        return None

    def complete_operation(
        self, command: CapabilityCommand, payload: dict[str, Any]
    ) -> CommandResult:
        waypoints = payload.get("trajectory", {}).get("waypoints", [])
        return success_result(
            command,
            {
                "executed_waypoints": len(waypoints),
                "final_waypoint": waypoints[-1] if waypoints else {},
                "stopped_at": "target",
            },
        )


class MockGripperAdapter(MockDeviceAdapter):
    """L0 mock for ``gripper.open`` and ``gripper.close`` with a virtual jaw state."""

    def __init__(
        self,
        scenario: DeviceScenario,
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
    ) -> None:
        if scenario.device_kind is not DeviceKind.GRIPPER:
            raise ScenarioConfigError("gripper mock requires a 'gripper' device scenario")
        super().__init__(scenario, state_sink=state_sink)
        data = scenario.device
        assert isinstance(data, GripperData)
        self._jaw = data.jaw_initial

    def complete_operation(
        self, command: CapabilityCommand, payload: dict[str, Any]
    ) -> CommandResult:
        if command.capability.endswith(".open"):
            self._jaw = "open"
        elif command.capability.endswith(".close"):
            self._jaw = "closed"
        return success_result(command, {"jaw_state": self._jaw})


class MockFixtureAdapter(MockDeviceAdapter):
    """L0 mock for ``fixture.clamp``, ``fixture.release``, and ``fixture.verify_seated``."""

    def __init__(
        self,
        scenario: DeviceScenario,
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
    ) -> None:
        if scenario.device_kind is not DeviceKind.FIXTURE:
            raise ScenarioConfigError("fixture mock requires a 'fixture' device scenario")
        super().__init__(scenario, state_sink=state_sink)
        data = scenario.device
        assert isinstance(data, FixtureData)
        self._fixture = data
        self._clamped = data.clamped_initial

    def complete_operation(
        self, command: CapabilityCommand, payload: dict[str, Any]
    ) -> CommandResult:
        if command.capability.endswith(".clamp"):
            self._clamped = True
        elif command.capability.endswith(".release"):
            self._clamped = False
        elif command.capability.endswith(".verify_seated") and not self._fixture.seated:
            raise DeviceOperationFault(
                Fault(
                    code="fixture.sensor.seating_failed",
                    message="Product seating verification failed in the mock fixture.",
                )
            )
        return success_result(command, {"clamped": self._clamped, "seated": self._fixture.seated})


class MockVisionLocatorAdapter(MockDeviceAdapter):
    """L0 mock for ``vision.locate_object`` with a deterministic pose estimate."""

    def __init__(
        self,
        scenario: DeviceScenario,
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
    ) -> None:
        if scenario.device_kind is not DeviceKind.VISION_LOCATOR:
            raise ScenarioConfigError(
                "vision locator mock requires a 'vision_locator' device scenario"
            )
        super().__init__(scenario, state_sink=state_sink)
        data = scenario.device
        assert isinstance(data, VisionData)
        self._vision = data

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        if capability == TEST_HOOK_CAPABILITY:
            return None
        object_type = _require_text(payload, "object_type")
        if isinstance(object_type, Fault):
            return object_type
        profile = payload.get("profile_id")
        if profile is not None and not isinstance(profile, str):
            return _invalid("'profile_id' must be a string when provided.")
        region = payload.get("region_of_interest")
        if region is not None and not isinstance(region, dict):
            return _invalid("'region_of_interest' must be an object when provided.")
        return None

    def complete_operation(
        self, command: CapabilityCommand, payload: dict[str, Any]
    ) -> CommandResult:
        if not self._vision.object_present:
            raise DeviceOperationFault(
                Fault(
                    code="vision.object.not_found",
                    message="Mock vision locator found no object in the region of interest.",
                )
            )
        if not self._vision.within_correction_limit:
            raise DeviceOperationFault(
                Fault(
                    code="vision.pose.correction_limit",
                    message="Mock pose estimate exceeds the configured correction limit.",
                )
            )
        estimate = {
            "object_id": self._vision.object_id,
            "confidence": self._vision.confidence,
            "pose": self._vision.pose.as_dict(),
            "source_frame": f"{self.scenario.component_instance_id}/optical",
            "metadata": {
                "object_type": payload.get("object_type", ""),
                "profile_id": payload.get("profile_id", ""),
            },
        }
        return success_result(command, {"estimates": [estimate]})


class MockProcessMachineAdapter(MockDeviceAdapter):
    """L0 two-stage mock for ``process.select_program`` and ``process.execute_cycle``."""

    def __init__(
        self,
        scenario: DeviceScenario,
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
    ) -> None:
        if scenario.device_kind is not DeviceKind.PROCESS_MACHINE:
            raise ScenarioConfigError(
                "process machine mock requires a 'process_machine' device scenario"
            )
        super().__init__(scenario, state_sink=state_sink)
        data = scenario.device
        assert isinstance(data, ProcessData)
        self._process = data
        self._prepared_program: str | None = None

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        if capability == TEST_HOOK_CAPABILITY:
            return None
        program_id = _require_text(payload, "program_id")
        if isinstance(program_id, Fault):
            return program_id
        if "execute_cycle" in capability:
            if self._prepared_program is None:
                return _invalid("No program is prepared; run 'process.select_program' first.")
            if program_id != self._prepared_program:
                return _invalid(
                    f"Requested program '{program_id}' does not match the prepared "
                    f"program '{self._prepared_program}'."
                )
        variable_data = payload.get("variable_data")
        if variable_data is not None and not isinstance(variable_data, dict):
            return _invalid("'variable_data' must be an object when provided.")
        return None

    def complete_operation(
        self, command: CapabilityCommand, payload: dict[str, Any]
    ) -> CommandResult:
        program_id = payload.get("program_id", "")
        if command.capability.endswith(".select_program"):
            if program_id not in self._process.known_programs:
                raise DeviceOperationFault(
                    Fault(
                        code="laser.program.not_found",
                        message=f"Program '{program_id}' is not known to the mock process machine.",
                    )
                )
            self._prepared_program = program_id
            return success_result(command, {"selected_program": program_id, "prepared": True})
        if not self._process.interlock_permitted:
            raise DeviceOperationFault(
                Fault(
                    code="laser.process.interlock_not_ready",
                    message="Mock process interlock status is not permitting a cycle.",
                )
            )
        return success_result(
            command,
            {
                "program_id": program_id,
                "cycle": "completed",
                "verification_passed": self._process.verification_passed,
                "process_data": {
                    "variable_data": payload.get("variable_data", {}),
                    "recipe_id": payload.get("recipe_id", ""),
                    "recipe_version": payload.get("recipe_version", 0),
                },
            },
        )


class MockInspectionAdapter(MockDeviceAdapter):
    """L0 mock for ``vision.inspect_object`` with deterministic measurements."""

    def __init__(
        self,
        scenario: DeviceScenario,
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
    ) -> None:
        if scenario.device_kind is not DeviceKind.INSPECTION:
            raise ScenarioConfigError("inspection mock requires an 'inspection' device scenario")
        super().__init__(scenario, state_sink=state_sink)
        data = scenario.device
        assert isinstance(data, InspectionData)
        self._inspection = data

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        if capability == TEST_HOOK_CAPABILITY:
            return None
        profile = _require_text(payload, "inspection_profile")
        if isinstance(profile, Fault):
            return profile
        expected = payload.get("expected")
        if expected is not None and not isinstance(expected, dict):
            return _invalid("'expected' must be an object when provided.")
        return None

    def complete_operation(
        self, command: CapabilityCommand, payload: dict[str, Any]
    ) -> CommandResult:
        return success_result(
            command,
            {
                "accepted": self._inspection.accepted,
                "measurements": self._inspection.measurements,
                "evidence_uri": "",
            },
        )


_MOCK_CLASSES: dict[DeviceKind, type[MockDeviceAdapter]] = {
    DeviceKind.ROBOT: MockRobotMotionAdapter,
    DeviceKind.GRIPPER: MockGripperAdapter,
    DeviceKind.FIXTURE: MockFixtureAdapter,
    DeviceKind.VISION_LOCATOR: MockVisionLocatorAdapter,
    DeviceKind.PROCESS_MACHINE: MockProcessMachineAdapter,
    DeviceKind.INSPECTION: MockInspectionAdapter,
}


def build_device_mock(
    scenario: DeviceScenario,
    *,
    state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
) -> MockDeviceAdapter:
    """Build the mock adapter implementation for a validated device scenario."""

    return _MOCK_CLASSES[scenario.device_kind](scenario, state_sink=state_sink)


def contract_scenario_config(kind: DeviceKind, scenario: ContractScenario) -> DeviceScenario:
    """Map one generic contract scenario onto a validated mock device configuration."""

    operations: dict[str, dict[str, Any]] = {
        capability: {"duration_seconds": 0.005} for capability in sorted(DEVICE_CAPABILITIES[kind])
    }
    restart = "ready"
    if scenario is ContractScenario.INVALID_INPUT:
        pass  # The test-hook capability stays unconfigured, so input validation rejects it.
    elif scenario in {ContractScenario.CANCELLATION, ContractScenario.TIMEOUT}:
        operations[TEST_HOOK_CAPABILITY] = {"duration_seconds": 5.0}
    elif scenario is ContractScenario.FAULT:
        operations[TEST_HOOK_CAPABILITY] = {"duration_seconds": 0.005, "fault": TEST_HOOK_FAULT}
    else:
        operations[TEST_HOOK_CAPABILITY] = {"duration_seconds": 0.005}
        if scenario is ContractScenario.RESTART_UNKNOWN:
            restart = "uncertain"
    device: dict[str, Any] = {}
    if kind is DeviceKind.PROCESS_MACHINE:
        device = {"known_programs": ["MOCK-PROGRAM-01"]}
    return parse_device_scenario(
        {
            "component_instance_id": f"mock-{kind.value.replace('_', '-')}-contract",
            "device_kind": kind.value,
            "restart": restart,
            "operations": operations,
            "device": device,
        }
    )


def make_contract_factory(kind: DeviceKind) -> ContractAdapterFactory:
    """Build a generic contract-suite factory for one mock device kind."""

    def factory(scenario: ContractScenario) -> MockDeviceAdapter:
        return build_device_mock(contract_scenario_config(kind, scenario))

    return factory
