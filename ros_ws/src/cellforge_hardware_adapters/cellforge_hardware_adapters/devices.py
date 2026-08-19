"""Physical hardware device adapters implementing canonical capability contracts."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from cellforge_device_sdk.adapter import (
    BaseDeviceAdapter,
    CancellationDisposition,
    OperationContext,
)
from cellforge_device_sdk.contract import ContractAdapterFactory, ContractScenario
from cellforge_device_sdk.models import (
    CapabilityCommand,
    CommandResult,
    DeviceOperationFault,
    DeviceState,
    DeviceStateSnapshot,
    Fault,
    RestartReconciliation,
)
from cellforge_device_sdk.state import CanonicalStatePublisher

from cellforge_hardware_adapters.protocols import (
    IndustrialCameraStream,
    LaserVendorTcpClient,
    ModbusTcpIoClient,
    RobotTrajectoryClient,
)

logger = logging.getLogger(__name__)

TEST_HOOK_CAPABILITY = "sdk.test.execute"
TEST_HOOK_FAULT = "sdk.test.injected_fault"


class HardwareDeviceKind(StrEnum):
    ROBOT = "robot"
    GRIPPER = "gripper"
    FIXTURE = "fixture"
    CAMERA = "camera"
    LASER = "laser"
    SAFETY_STATUS = "safety_status"


def _invalid(message: str) -> Fault:
    return Fault(code="sdk.command.invalid_input", message=message)


def _require_text(payload: dict[str, Any], key: str) -> str | Fault:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return _invalid(f"'{key}' must be a non-blank string.")
    return value


def success_result(command: CapabilityCommand, payload: dict[str, Any]) -> CommandResult:
    return CommandResult(
        command_id=command.command_id,
        trace_id=command.trace_id,
        success=True,
        result_code=f"{command.capability}.success",
        result_message=f"Hardware operation '{command.capability}' succeeded.",
        output_payload_json=json.dumps(payload, sort_keys=True),
        outcome_certain=True,
    )


# ---------------------------------------------------------------------------
# Base Physical Adapter
# ---------------------------------------------------------------------------


class BaseHardwareAdapter(BaseDeviceAdapter):
    """Base class for all real/physical hardware adapters."""

    def __init__(
        self,
        component_instance_id: str,
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
        restart_uncertain: bool = False,
        enable_test_hook: bool = True,
        test_hook_duration: float = 0.005,
    ) -> None:
        publisher = CanonicalStatePublisher(component_instance_id, state_sink)
        super().__init__(component_instance_id, state_publisher=publisher)
        self.operation_started = asyncio.Event()
        self.restart_uncertain = restart_uncertain
        self.enable_test_hook = enable_test_hook
        self.test_hook_duration = test_hook_duration
        self._injected_fault: str | None = None

    def inject_next_fault(self, fault_code: str) -> None:
        self._injected_fault = fault_code

    def validate_command(self, command: CapabilityCommand) -> Fault | None:
        if command.capability == TEST_HOOK_CAPABILITY:
            if not self.enable_test_hook:
                return Fault(
                    code="sdk.command.invalid_input",
                    message="Capability 'sdk.test.execute' is not configured for this device.",
                )
            return None
        try:
            payload = json.loads(command.input_payload_json) if command.input_payload_json else {}
        except json.JSONDecodeError:
            return _invalid("Invalid JSON payload.")
        return self.validate_payload(command.capability, payload)

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        return None

    async def execute_operation(self, context: OperationContext) -> CommandResult:
        self.operation_started.set()
        command = context.command

        if self._injected_fault is not None:
            code = self._injected_fault
            self._injected_fault = None
            raise DeviceOperationFault(Fault(code=code, message=f"Hardware fault injected: {code}"))

        if command.capability == TEST_HOOK_CAPABILITY:
            await asyncio.sleep(self.test_hook_duration)
            return success_result(command, {"test": "ok"})

        payload = json.loads(command.input_payload_json) if command.input_payload_json else {}
        return await self.complete_hardware_operation(command, payload, context)

    async def complete_hardware_operation(
        self, command: CapabilityCommand, payload: dict[str, Any], context: OperationContext
    ) -> CommandResult:
        raise NotImplementedError

    async def request_cancellation(self, context: OperationContext) -> CancellationDisposition:
        return CancellationDisposition(
            outcome_certain=True,
            message="Hardware operation cancelled.",
        )

    async def read_restart_reconciliation(self) -> RestartReconciliation:
        if self.restart_uncertain:
            return RestartReconciliation(
                state=DeviceState.UNKNOWN,
                ready=False,
                outcome_certain=False,
                details={
                    "source": "hardware",
                    "reason": "hardware_restart_requires_reconciliation",
                },
            )
        return RestartReconciliation(
            state=DeviceState.READY,
            ready=True,
            outcome_certain=True,
            details={"source": "hardware", "reason": "hardware_ready"},
        )


# ---------------------------------------------------------------------------
# 1. Robot Motion Hardware Adapter
# ---------------------------------------------------------------------------


class RobotHardwareAdapter(BaseHardwareAdapter):
    """Production hardware adapter for industrial 6-axis robot motion."""

    def __init__(
        self,
        component_instance_id: str = "robot-001",
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
        restart_uncertain: bool = False,
        enable_test_hook: bool = True,
        test_hook_duration: float = 0.005,
        client: RobotTrajectoryClient | None = None,
    ) -> None:
        super().__init__(
            component_instance_id,
            state_sink=state_sink,
            restart_uncertain=restart_uncertain,
            enable_test_hook=enable_test_hook,
            test_hook_duration=test_hook_duration,
        )
        self.client = client or RobotTrajectoryClient(robot_id=component_instance_id)

    async def connect_hardware(self) -> bool:
        ok = await self.client.connect()
        if ok:
            self.mark_ready()
        return ok

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        if capability == TEST_HOOK_CAPABILITY:
            return None
        trajectory = payload.get("trajectory")
        if not isinstance(trajectory, dict):
            return _invalid("'trajectory' must be an object containing waypoints.")
        waypoints = trajectory.get("waypoints")
        if not isinstance(waypoints, list) or not waypoints:
            return _invalid("'trajectory.waypoints' must be a non-empty list of waypoints.")
        return None

    async def complete_hardware_operation(
        self, command: CapabilityCommand, payload: dict[str, Any], context: OperationContext
    ) -> CommandResult:
        trajectory = payload.get("trajectory", {})
        scaling = float(payload.get("velocity_scaling", 0.25))

        success, executed, fault_code = await self.client.execute_trajectory(
            trajectory, velocity_scaling=scaling
        )
        if not success:
            raise DeviceOperationFault(
                Fault(
                    code=fault_code or "robot.motion.execution_failed",
                    message=f"Robot trajectory execution failed with code {fault_code}",
                )
            )

        waypoints = trajectory.get("waypoints", [])
        return success_result(
            command,
            {
                "executed_waypoints": executed,
                "final_waypoint": waypoints[-1] if waypoints else {},
                "stopped_at": "target",
            },
        )

    async def request_cancellation(self, context: OperationContext) -> CancellationDisposition:
        await self.client.cancel()
        return CancellationDisposition(
            outcome_certain=True,
            message="Robot motion trajectory stopped on controller.",
        )


# ---------------------------------------------------------------------------
# 2. Gripper Hardware Adapter
# ---------------------------------------------------------------------------


class GripperHardwareAdapter(BaseHardwareAdapter):
    """Production hardware adapter for parallel pneumatic/electric gripper."""

    def __init__(
        self,
        component_instance_id: str = "gripper-001",
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
        restart_uncertain: bool = False,
        enable_test_hook: bool = True,
        test_hook_duration: float = 0.005,
        io_client: ModbusTcpIoClient | None = None,
        open_coil: int = 0,
        close_coil: int = 1,
        part_grip_input: int = 0,
    ) -> None:
        super().__init__(
            component_instance_id,
            state_sink=state_sink,
            restart_uncertain=restart_uncertain,
            enable_test_hook=enable_test_hook,
            test_hook_duration=test_hook_duration,
        )
        self.io_client = io_client or ModbusTcpIoClient()
        self.open_coil = open_coil
        self.close_coil = close_coil
        self.part_grip_input = part_grip_input
        self._jaw_state = "open"
        self._simulate_grip_loss = False

    def set_simulate_grip_loss(self, loss: bool) -> None:
        self._simulate_grip_loss = loss

    async def connect_hardware(self) -> bool:
        ok = await self.io_client.connect()
        if ok:
            self.mark_ready()
        return ok

    async def complete_hardware_operation(
        self, command: CapabilityCommand, payload: dict[str, Any], context: OperationContext
    ) -> CommandResult:
        if command.capability.endswith(".open"):
            await self.io_client.write_coil(self.close_coil, False)
            await self.io_client.write_coil(self.open_coil, True)
            await asyncio.sleep(0.05)
            self._jaw_state = "open"
            return success_result(command, {"jaw_state": "open", "part_grasped": False})

        if command.capability.endswith(".close"):
            await self.io_client.write_coil(self.open_coil, False)
            await self.io_client.write_coil(self.close_coil, True)
            await asyncio.sleep(0.05)
            if self._simulate_grip_loss:
                self._jaw_state = "closed"
                raise DeviceOperationFault(
                    Fault(
                        code="gripper.sensor.grip_failed",
                        message="Part grip detection sensor did not confirm grip on close.",
                    )
                )
            self._jaw_state = "closed"
            return success_result(command, {"jaw_state": "closed", "part_grasped": True})

        return success_result(command, {"jaw_state": self._jaw_state})


# ---------------------------------------------------------------------------
# 3. Fixture Hardware Adapter (Clamp, Release, Seating Sensor)
# ---------------------------------------------------------------------------


class FixtureHardwareAdapter(BaseHardwareAdapter):
    """Production hardware adapter for pneumatic clamping fixture with seating sensor."""

    def __init__(
        self,
        component_instance_id: str = "fixture-001",
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
        restart_uncertain: bool = False,
        enable_test_hook: bool = True,
        test_hook_duration: float = 0.005,
        io_client: ModbusTcpIoClient | None = None,
        clamp_coil: int = 2,
        seating_sensor_input: int = 1,
    ) -> None:
        super().__init__(
            component_instance_id,
            state_sink=state_sink,
            restart_uncertain=restart_uncertain,
            enable_test_hook=enable_test_hook,
            test_hook_duration=test_hook_duration,
        )
        self.io_client = io_client or ModbusTcpIoClient()
        self.clamp_coil = clamp_coil
        self.seating_sensor_input = seating_sensor_input
        self._clamped = False
        self._seating_ok = True

    def set_seating_sensor_state(self, ok: bool) -> None:
        self._seating_ok = ok
        asyncio.create_task(self.io_client.write_discrete_input(self.seating_sensor_input, ok))

    async def connect_hardware(self) -> bool:
        ok = await self.io_client.connect()
        if ok:
            await self.io_client.write_discrete_input(self.seating_sensor_input, self._seating_ok)
            self.mark_ready()
        return ok

    async def complete_hardware_operation(
        self, command: CapabilityCommand, payload: dict[str, Any], context: OperationContext
    ) -> CommandResult:
        if command.capability.endswith(".clamp"):
            await self.io_client.write_coil(self.clamp_coil, True)
            await asyncio.sleep(0.05)
            self._clamped = True
            return success_result(command, {"clamped": True, "seated": self._seating_ok})

        if command.capability.endswith(".release"):
            await self.io_client.write_coil(self.clamp_coil, False)
            await asyncio.sleep(0.05)
            self._clamped = False
            return success_result(command, {"clamped": False, "seated": self._seating_ok})

        if command.capability.endswith(".verify_seated"):
            seated = await self.io_client.read_discrete_input_debounced(
                self.seating_sensor_input,
                expected_value=True,
                debounce_seconds=0.02,
                timeout_seconds=0.5,
            )
            if not seated:
                raise DeviceOperationFault(
                    Fault(
                        code="fixture.sensor.seating_failed",
                        message="Physical proximity sensor failed to detect seated part.",
                    )
                )
            return success_result(command, {"clamped": self._clamped, "seated": True})

        return success_result(command, {"clamped": self._clamped, "seated": self._seating_ok})


# ---------------------------------------------------------------------------
# 4. Camera / Vision Hardware Adapter
# ---------------------------------------------------------------------------


class CameraVisionHardwareAdapter(BaseHardwareAdapter):
    """Production hardware adapter for industrial 2D camera & vision processing."""

    def __init__(
        self,
        component_instance_id: str = "camera-001",
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
        restart_uncertain: bool = False,
        enable_test_hook: bool = True,
        test_hook_duration: float = 0.005,
        stream: IndustrialCameraStream | None = None,
    ) -> None:
        super().__init__(
            component_instance_id,
            state_sink=state_sink,
            restart_uncertain=restart_uncertain,
            enable_test_hook=enable_test_hook,
            test_hook_duration=test_hook_duration,
        )
        self.stream = stream or IndustrialCameraStream(camera_id=component_instance_id)

    async def connect_hardware(self) -> bool:
        ok = await self.stream.connect()
        if ok:
            self.mark_ready()
        return ok

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        if capability == TEST_HOOK_CAPABILITY:
            return None
        if "locate_object" in capability:
            object_type = _require_text(payload, "object_type")
            if isinstance(object_type, Fault):
                return object_type
        if "inspect_object" in capability:
            profile = _require_text(payload, "inspection_profile")
            if isinstance(profile, Fault):
                return profile
        return None

    async def complete_hardware_operation(
        self, command: CapabilityCommand, payload: dict[str, Any], context: OperationContext
    ) -> CommandResult:
        if "locate_object" in command.capability:
            object_type = payload.get("object_type", "pen")
            profile_id = payload.get("profile_id", "pen_reference")
            roi = payload.get("region_of_interest")

            estimates, fault_code = await self.stream.locate_object(object_type, profile_id, roi)
            if fault_code or not estimates:
                raise DeviceOperationFault(
                    Fault(
                        code=fault_code or "vision.object.not_found",
                        message=f"Vision object location failed: {fault_code}",
                    )
                )

            serialized_estimates = [
                {
                    "object_id": est.object_id,
                    "confidence": est.confidence,
                    "pose": est.pose,
                    "source_frame": est.source_frame,
                    "metadata": est.metadata,
                }
                for est in estimates
            ]
            return success_result(command, {"estimates": serialized_estimates})

        if "inspect_object" in command.capability:
            profile_id = payload.get("inspection_profile", "contrast_and_text_match")
            expected = payload.get("expected", {})

            result, fault_code = await self.stream.inspect_object(profile_id, expected)
            if fault_code:
                raise DeviceOperationFault(
                    Fault(
                        code=fault_code,
                        message=f"Vision inspection failed: {fault_code}",
                    )
                )

            return success_result(
                command,
                {
                    "accepted": result.accepted,
                    "measurements": result.measurements,
                    "evidence_uri": result.evidence_uri,
                },
            )

        return success_result(command, {})


# ---------------------------------------------------------------------------
# 5. Laser Marker Hardware Adapter (with Explicit Uncertain Outcome)
# ---------------------------------------------------------------------------


class LaserHardwareAdapter(BaseHardwareAdapter):
    """Production hardware adapter for industrial laser marker with uncertain-outcome handling."""

    def __init__(
        self,
        component_instance_id: str = "laser-001",
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
        restart_uncertain: bool = False,
        enable_test_hook: bool = True,
        test_hook_duration: float = 0.005,
        client: LaserVendorTcpClient | None = None,
    ) -> None:
        super().__init__(
            component_instance_id,
            state_sink=state_sink,
            restart_uncertain=restart_uncertain,
            enable_test_hook=enable_test_hook,
            test_hook_duration=test_hook_duration,
        )
        self.client = client or LaserVendorTcpClient()

    async def connect_hardware(self) -> bool:
        ok = await self.client.connect()
        if ok:
            self.mark_ready()
        return ok

    def validate_payload(self, capability: str, payload: dict[str, Any]) -> Fault | None:
        if capability == TEST_HOOK_CAPABILITY:
            return None
        program_id = _require_text(payload, "program_id")
        if isinstance(program_id, Fault):
            return program_id
        return None

    async def complete_hardware_operation(
        self, command: CapabilityCommand, payload: dict[str, Any], context: OperationContext
    ) -> CommandResult:
        program_id = payload.get("program_id", "")
        variable_data = payload.get("variable_data", {})

        if command.capability.endswith(".select_program"):
            ok, fault_code = await self.client.select_program(program_id)
            if not ok:
                raise DeviceOperationFault(
                    Fault(
                        code=fault_code or "laser.program.not_found",
                        message=f"Failed to select laser program '{program_id}'",
                    )
                )
            await self.client.set_variable_data(variable_data)
            return success_result(command, {"selected_program": program_id, "prepared": True})

        if command.capability.endswith(".execute_cycle"):
            recipe_id = payload.get("recipe_id", "")
            recipe_version = int(payload.get("recipe_version", 1))

            cycle_id, fault_code = await self.client.start_cycle(
                program_id, variable_data, recipe_id=recipe_id, recipe_version=recipe_version
            )
            if fault_code:
                raise DeviceOperationFault(
                    Fault(
                        code=fault_code,
                        message=f"Failed to start laser cycle: {fault_code}",
                    )
                )

            status, outcome_certain = await self.client.poll_cycle(cycle_id, duration_seconds=0.1)

            if not outcome_certain or status.state == "UNCERTAIN":
                return CommandResult(
                    command_id=command.command_id,
                    trace_id=command.trace_id,
                    success=False,
                    result_code="laser.process.outcome_unknown",
                    result_message=(
                        status.fault_message
                        or "Communication lost during laser emission; outcome unknown."
                    ),
                    output_payload_json="{}",
                    outcome_certain=False,
                )

            if status.state == "FAULT":
                raise DeviceOperationFault(
                    Fault(
                        code=status.fault_code or "laser.hardware.fault",
                        message=status.fault_message or "Laser cycle failed.",
                    )
                )

            return success_result(
                command,
                {
                    "program_id": program_id,
                    "cycle": "completed",
                    "cycle_id": cycle_id,
                    "verification_passed": status.verification_passed,
                    "process_data": {
                        "variable_data": variable_data,
                        "recipe_id": recipe_id,
                        "recipe_version": recipe_version,
                    },
                },
            )

        return success_result(command, {})


# ---------------------------------------------------------------------------
# 6. Hardware Safety Status Adapter (Read-Only)
# ---------------------------------------------------------------------------


class HardwareSafetyStatusAdapter(BaseHardwareAdapter):
    """Read-only hardware interface for external rated safety system status (ADR 0007)."""

    def __init__(
        self,
        component_instance_id: str = "safety-status-001",
        *,
        state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
        restart_uncertain: bool = False,
        enable_test_hook: bool = True,
        test_hook_duration: float = 0.005,
        healthy: bool = True,
    ) -> None:
        super().__init__(
            component_instance_id,
            state_sink=state_sink,
            restart_uncertain=restart_uncertain,
            enable_test_hook=enable_test_hook,
            test_hook_duration=test_hook_duration,
        )
        self.healthy = healthy

    def set_safety_health(self, healthy: bool) -> None:
        self.healthy = healthy
        if not healthy:
            self.state_publisher.transition(
                DeviceState.FAULT,
                fault=Fault(
                    code="safety.status.unhealthy",
                    message="Independent rated safety hardware reports unhealthy state.",
                ),
            )
        else:
            self.mark_ready()


# ---------------------------------------------------------------------------
# Generic Contract-Suite Factory for Hardware Adapters
# ---------------------------------------------------------------------------


_HARDWARE_CLASSES: dict[HardwareDeviceKind, type[BaseHardwareAdapter]] = {
    HardwareDeviceKind.ROBOT: RobotHardwareAdapter,
    HardwareDeviceKind.GRIPPER: GripperHardwareAdapter,
    HardwareDeviceKind.FIXTURE: FixtureHardwareAdapter,
    HardwareDeviceKind.CAMERA: CameraVisionHardwareAdapter,
    HardwareDeviceKind.LASER: LaserHardwareAdapter,
    HardwareDeviceKind.SAFETY_STATUS: HardwareSafetyStatusAdapter,
}


def build_hardware_adapter(
    kind: HardwareDeviceKind,
    component_instance_id: str,
    *,
    state_sink: Callable[[DeviceStateSnapshot], None] | None = None,
    restart_uncertain: bool = False,
    enable_test_hook: bool = True,
    test_hook_duration: float = 0.005,
) -> BaseHardwareAdapter:
    adapter_cls = _HARDWARE_CLASSES[kind]
    return adapter_cls(
        component_instance_id,
        state_sink=state_sink,
        restart_uncertain=restart_uncertain,
        enable_test_hook=enable_test_hook,
        test_hook_duration=test_hook_duration,
    )


def make_hardware_contract_factory(kind: HardwareDeviceKind) -> ContractAdapterFactory:
    """Build a generic contract-suite factory for a hardware device adapter."""

    def factory(scenario: ContractScenario) -> BaseHardwareAdapter:
        instance_id = f"hw-{kind.value.replace('_', '-')}-contract"
        restart_uncertain = scenario is ContractScenario.RESTART_UNKNOWN
        enable_test_hook = scenario is not ContractScenario.INVALID_INPUT
        test_hook_duration = (
            5.0 if scenario in {ContractScenario.CANCELLATION, ContractScenario.TIMEOUT} else 0.005
        )

        adapter = build_hardware_adapter(
            kind,
            instance_id,
            restart_uncertain=restart_uncertain,
            enable_test_hook=enable_test_hook,
            test_hook_duration=test_hook_duration,
        )

        if scenario is ContractScenario.FAULT:
            adapter.inject_next_fault(TEST_HOOK_FAULT)

        return adapter

    return factory
