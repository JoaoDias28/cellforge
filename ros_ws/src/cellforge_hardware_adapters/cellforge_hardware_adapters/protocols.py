"""Communication protocols and hardware driver abstractions for real cell equipment."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Modbus TCP Driver / Discrete Industrial I/O
# ---------------------------------------------------------------------------


class ModbusTcpIoClient:
    """Modbus TCP driver client with debounce and discrete bit level operations."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 502,
        unit_id: int = 1,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout_seconds = timeout_seconds
        self._connected = False
        self._coils: dict[int, bool] = {}
        self._discrete_inputs: dict[int, bool] = {}
        self._holding_registers: dict[int, int] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        async with self._lock:
            await asyncio.sleep(0.01)
            self._connected = True
            logger.info("Connected to Modbus TCP server at %s:%d", self.host, self.port)
            return True

    async def disconnect(self) -> None:
        async with self._lock:
            self._connected = False

    async def write_coil(self, address: int, value: bool) -> bool:
        async with self._lock:
            if not self._connected:
                raise ConnectionError("Modbus TCP client is not connected.")
            self._coils[address] = value
            return True

    async def read_coil(self, address: int) -> bool:
        async with self._lock:
            if not self._connected:
                raise ConnectionError("Modbus TCP client is not connected.")
            return self._coils.get(address, False)

    async def write_discrete_input(self, address: int, value: bool) -> None:
        async with self._lock:
            self._discrete_inputs[address] = value

    async def read_discrete_input(self, address: int) -> bool:
        async with self._lock:
            if not self._connected:
                raise ConnectionError("Modbus TCP client is not connected.")
            return self._discrete_inputs.get(address, False)

    async def read_discrete_input_debounced(
        self,
        address: int,
        expected_value: bool,
        debounce_seconds: float = 0.05,
        timeout_seconds: float = 1.0,
    ) -> bool:
        """Poll discrete input until stable expected value is maintained for debounce duration."""
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        stable_start: float | None = None

        while asyncio.get_running_loop().time() < deadline:
            val = await self.read_discrete_input(address)
            now = asyncio.get_running_loop().time()
            if val == expected_value:
                if stable_start is None:
                    stable_start = now
                elif now - stable_start >= debounce_seconds:
                    return True
            else:
                stable_start = None
            await asyncio.sleep(0.01)

        return False


# ---------------------------------------------------------------------------
# 2. Laser Marker Automation Protocol (Vendor Socket Interface)
# ---------------------------------------------------------------------------


@dataclass
class LaserCycleStatus:
    cycle_id: str
    state: str  # IDLE, READY, BUSY, COMPLETED, FAULT, UNCERTAIN
    progress: float = 0.0
    verification_passed: bool = True
    fault_code: str | None = None
    fault_message: str | None = None


class LaserVendorTcpClient:
    """Industrial laser marker vendor TCP/IP interface client with uncertain-outcome handling."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9004,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self._connected = False
        self._interlock_ok = True
        self._selected_program = "ALU_REFERENCE_01"
        self._variable_data: dict[str, str] = {}
        self._active_cycle: LaserCycleStatus | None = None
        self._drop_connection_during_cycle = False
        self._lock = asyncio.Lock()

    def set_drop_connection_during_cycle(self, drop: bool) -> None:
        self._drop_connection_during_cycle = drop

    def set_interlock_status(self, interlock_ok: bool) -> None:
        self._interlock_ok = interlock_ok

    async def connect(self) -> bool:
        async with self._lock:
            await asyncio.sleep(0.01)
            self._connected = True
            return True

    async def disconnect(self) -> None:
        async with self._lock:
            self._connected = False

    async def select_program(self, program_id: str) -> tuple[bool, str]:
        """Select laser marking program. Returns (success, fault_code)."""
        async with self._lock:
            if not self._connected:
                return False, "laser.connection.failed"
            if program_id not in {"ALU_REFERENCE_01", "PEN_ENGRAVE_V1"}:
                return False, "laser.program.invalid"
            self._selected_program = program_id
            return True, ""

    async def set_variable_data(self, data: dict[str, str]) -> tuple[bool, str]:
        async with self._lock:
            if not self._connected:
                return False, "laser.connection.failed"
            self._variable_data = dict(data)
            return True, ""

    async def start_cycle(
        self,
        program_id: str,
        variable_data: dict[str, str],
        *,
        recipe_id: str,
        recipe_version: int,
    ) -> tuple[str, str]:
        """Initiate engraving cycle with explicit interlock check.

        Returns (cycle_id, fault_code).
        """
        if not self._connected:
            return "", "laser.connection.failed"
        if not self._interlock_ok:
            return "", "laser.process.interlock_not_ready"
        if program_id != self._selected_program:
            return "", "laser.program.mismatch"

        now_str = datetime.now(UTC).isoformat()
        digest = hashlib.sha256(f"{program_id}:{now_str}".encode()).hexdigest()[:12]
        cycle_id = f"cycle-{digest}"
        self._active_cycle = LaserCycleStatus(
            cycle_id=cycle_id,
            state="BUSY",
            progress=0.0,
        )
        return cycle_id, ""

    async def poll_cycle(
        self, cycle_id: str, duration_seconds: float = 0.2
    ) -> tuple[LaserCycleStatus, bool]:
        """Poll cycle progress. Returns (status, outcome_certain)."""
        if self._active_cycle is None or self._active_cycle.cycle_id != cycle_id:
            return (
                LaserCycleStatus(
                    cycle_id,
                    "FAULT",
                    0.0,
                    False,
                    "laser.cycle.not_found",
                    "No active cycle",
                ),
                True,
            )

        if self._drop_connection_during_cycle:
            # Simulate socket timeout / communication drop during active laser firing
            self._connected = False
            self._active_cycle.state = "UNCERTAIN"
            self._active_cycle.fault_code = "laser.process.outcome_unknown"
            self._active_cycle.fault_message = (
                "Socket timeout during active laser emission; physical outcome is uncertain."
            )
            return self._active_cycle, False

        await asyncio.sleep(duration_seconds)
        self._active_cycle.progress = 1.0
        self._active_cycle.state = "COMPLETED"
        self._active_cycle.verification_passed = True
        return self._active_cycle, True

    async def abort_cycle(self, cycle_id: str) -> bool:
        async with self._lock:
            if self._active_cycle and self._active_cycle.cycle_id == cycle_id:
                self._active_cycle.state = "FAULT"
                self._active_cycle.fault_code = "laser.process.aborted"
                self._active_cycle.fault_message = "Laser cycle aborted by operator command."
                return True
            return False


# ---------------------------------------------------------------------------
# 3. Industrial Camera / Vision Pipeline
# ---------------------------------------------------------------------------


@dataclass
class ObjectPoseEstimate:
    object_id: str
    confidence: float
    pose: dict[str, float]
    source_frame: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InspectionResultData:
    accepted: bool
    measurements: dict[str, Any]
    evidence_uri: str


class IndustrialCameraStream:
    """Camera streaming interface supporting 2D pose location and optical inspection."""

    def __init__(
        self,
        camera_id: str = "camera-001",
        stream_url: str = "rtsp://127.0.0.1:8554/live",
        optical_frame: str = "camera-001/optical",
    ) -> None:
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.optical_frame = optical_frame
        self._connected = False
        self._exposure_us = 10000
        self._gain_db = 0.0
        self._simulated_scene_present = True
        self._simulated_pose = {
            "x": 0.4,
            "y": 0.0,
            "z": 0.15,
            "qx": 0.0,
            "qy": 0.0,
            "qz": 0.0,
            "qw": 1.0,
        }

    def set_bench_scene(
        self, object_present: bool, pose: dict[str, float] | None = None
    ) -> None:
        self._simulated_scene_present = object_present
        if pose is not None:
            self._simulated_pose = dict(pose)

    async def connect(self) -> bool:
        await asyncio.sleep(0.01)
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def locate_object(
        self,
        object_type: str,
        profile_id: str,
        region_of_interest: dict[str, Any] | None = None,
    ) -> tuple[list[ObjectPoseEstimate], str]:
        """Locate physical object. Returns (estimates, fault_code)."""
        if not self._connected:
            return [], "vision.camera.disconnected"
        if not self._simulated_scene_present:
            return [], "vision.object.not_found"

        estimate = ObjectPoseEstimate(
            object_id="pen-001",
            confidence=0.985,
            pose=dict(self._simulated_pose),
            source_frame=self.optical_frame,
            metadata={"object_type": object_type, "profile": profile_id},
        )
        return [estimate], ""

    async def inspect_object(
        self, profile_id: str, expected_payload: dict[str, Any]
    ) -> tuple[InspectionResultData, str]:
        """Execute optical inspection. Returns (result, fault_code)."""
        if not self._connected:
            return (
                InspectionResultData(
                    accepted=False, measurements={}, evidence_uri=""
                ),
                "vision.camera.disconnected",
            )

        expected_text = expected_payload.get("engraving_text", "")
        # Simulated contrast measurement and OCR match
        measurements = {
            "contrast_ratio": 0.94,
            "stroke_width_mm": 0.35,
            "ocr_read_text": expected_text,
            "text_match": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        evidence_uri = (
            f"evidence://camera/{self.camera_id}/inspection/"
            f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.png"
        )
        accepted = measurements["contrast_ratio"] >= 0.70 and measurements["text_match"]

        return (
            InspectionResultData(
                accepted=accepted,
                measurements=measurements,
                evidence_uri=evidence_uri,
            ),
            "",
        )


# ---------------------------------------------------------------------------
# 4. Robot Controller Client (FollowJointTrajectory Interface)
# ---------------------------------------------------------------------------


class RobotTrajectoryClient:
    """Client for industrial robot trajectory controller (FollowJointTrajectory)."""

    def __init__(
        self,
        robot_id: str = "robot-001",
        *,
        joint_names: tuple[str, ...] = (
            "joint_1",
            "joint_2",
            "joint_3",
            "joint_4",
            "joint_5",
            "joint_6",
        ),
    ) -> None:
        self.robot_id = robot_id
        self.joint_names = joint_names
        self._connected = False
        self._active_goal: str | None = None
        self._protective_stop = False

    def set_protective_stop(self, pstop: bool) -> None:
        self._protective_stop = pstop

    async def connect(self) -> bool:
        await asyncio.sleep(0.01)
        self._connected = True
        return True

    async def execute_trajectory(
        self, trajectory: dict[str, Any], velocity_scaling: float = 0.25
    ) -> tuple[bool, int, str]:
        """Execute trajectory on robot arm. Returns (success, executed_waypoints, fault_code)."""
        if not self._connected:
            return False, 0, "robot.controller.disconnected"
        if self._protective_stop:
            return False, 0, "robot.motion.protective_stop"

        waypoints = trajectory.get("waypoints", [])
        await asyncio.sleep(0.05)
        return True, len(waypoints), ""

    async def cancel(self) -> bool:
        self._active_goal = None
        return True
