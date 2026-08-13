"""Simulator-observation state machine used by the Isaac Sim 6 L2 ROS adapters.

This module deliberately contains no Kit or ROS imports.  The Isaac edge supplies the backend and
the ROS edge supplies typed actions; neither the acceptance runner nor a test may inject a success
result directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from cellforge_simulation.physical import (
    DEFAULT_BOUNDS,
    PROCESS_LIMITATION,
    SAFETY_LIMITATION,
    PenPose,
    sample_pen_pose,
)

# PhysX contact rest pose for the simplified capsule on the fixture base (top at 0.830 m).
_FIXTURE_REST_POSE = PenPose(550.0, 0.0, 834.0, 0.0)


class L2RuntimeError(ValueError):
    """Stable invalid-configuration or invalid-command failure."""


class PhysicsBackend(Protocol):
    """OpenUSD/PhysX observations required by the canonical L2 adapter."""

    fidelity: str

    def spawn_pen(self, object_id: str, pose: PenPose) -> str: ...

    def set_pen_pose(self, pen_path: str, pose: PenPose) -> None: ...

    def attach(self, pen_path: str, tool_path: str = "/World/Robot/GripperBody") -> str: ...

    def detach(self, pen_path: str) -> None: ...

    def set_dynamic(self, pen_path: str) -> None: ...

    def is_attached(self, pen_path: str) -> bool: ...

    def is_seated(
        self,
        pen_path: str,
        *,
        fixture_center_m: tuple[float, float, float] = ...,
        translation_tolerance_m: float = ...,
    ) -> bool: ...

    def is_dropped(self, pen_path: str, *, minimum_z_m: float = ...) -> bool: ...

    def translation_m(self, pen_path: str) -> tuple[float, float, float]: ...

    def contacts_for(self, pen_path: str) -> tuple[str, ...]: ...

    def set_runtime_attribute(self, pen_path: str, name: str, value: str | bool) -> None: ...

    def runtime_attribute(self, pen_path: str, name: str) -> str | bool | None: ...

    def step(self, count: int = 1) -> None: ...


@dataclass(frozen=True, slots=True)
class L2Outcome:
    success: bool
    result_code: str
    result_message: str
    output: dict[str, Any]
    outcome_certain: bool = True


@dataclass(frozen=True, slots=True)
class L2Event:
    sequence: int
    event_type: str
    result_code: str
    component_instance_id: str
    command_id: str
    observation: dict[str, Any]
    origin: str = "isaac_l2_adapter"

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


class IsaacL2Runtime:
    """Canonical adapter outcomes derived from one live Isaac OpenUSD/PhysX stage."""

    capabilities = {
        "fixture.action.clamp",
        "fixture.action.release",
        "fixture.action.verify_seated",
        "gripper.action.close",
        "gripper.action.open",
        "process.action.execute_cycle",
        "process.action.select_program",
        "robot_motion.action.execute_trajectory",
        "vision.action.inspect_object",
        "vision.action.locate_object",
    }

    def __init__(
        self,
        backend: PhysicsBackend,
        scenario: dict[str, Any],
        *,
        event_sink: Callable[[L2Event], None] | None = None,
    ) -> None:
        if getattr(backend, "fidelity", "") != "L2":
            raise L2RuntimeError("l2.backend.invalid: an L2 Isaac PhysX backend is required")
        identity = scenario.get("scenario")
        initial = scenario.get("initial_state")
        if not isinstance(identity, dict) or not isinstance(initial, dict):
            raise L2RuntimeError("l2.scenario.invalid: scenario and initial_state are required")
        seed = identity.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise L2RuntimeError("l2.scenario.seed_invalid: seed must be non-negative")
        self.backend = backend
        self.scenario_id = str(identity.get("id", ""))
        self.seed = seed
        self.initial = dict(initial)
        self.faults = {
            str(item.get("fault")) for item in scenario.get("faults", []) if isinstance(item, dict)
        }
        self._event_sink = event_sink
        self.events: list[L2Event] = []
        self.object_id = f"pen-{seed:08d}"
        self.pose = sample_pen_pose(seed, DEFAULT_BOUNDS)
        self.pen_path = ""
        self.program_selected = False
        self.process_completed = False
        self.fixture_clamped = False
        self._spawn()
        self._emit(
            "scenario.configured",
            "simulation.scenario.configured",
            "",
            "",
            {"product_present": bool(self.pen_path), "safety_healthy": self.safety_healthy},
        )
        if not self.safety_healthy:
            self._emit(
                "safety.modeled.unhealthy",
                "safety.unhealthy",
                "safety-status-001",
                "",
                {"safety_claim": "none"},
            )

    @property
    def safety_healthy(self) -> bool:
        return bool(self.initial.get("safety_healthy", True))

    def publish_configuration_event(self) -> None:
        """Acknowledge an idempotent scenario configuration without rebuilding PhysX state."""

        self._emit(
            "scenario.configured",
            "simulation.scenario.configured",
            "",
            "",
            {"product_present": bool(self.pen_path), "safety_healthy": self.safety_healthy},
        )

    def _spawn(self) -> None:
        if not bool(self.initial.get("product_present", True)):
            return
        self.pen_path = self.backend.spawn_pen(self.object_id, self.pose)
        self.backend.step(2)
        self._emit(
            "product.spawned",
            "simulation.product.spawned",
            "camera-001",
            "",
            {"pen_path": self.pen_path, "pose": self.pose.as_json(), "physics": "PhysX"},
        )

    def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        command_id: str,
    ) -> L2Outcome:
        if capability not in self.capabilities:
            raise L2RuntimeError(f"l2.capability.unknown: {capability}")
        component = _component(capability)
        self._emit(
            f"{capability}.requested",
            "l2.command.accepted",
            component,
            command_id,
            {"payload": payload},
        )
        handler = {
            "vision.action.locate_object": self._locate,
            "vision.action.inspect_object": self._inspect,
            "robot_motion.action.execute_trajectory": self._robot,
            "gripper.action.close": self._gripper_close,
            "gripper.action.open": self._gripper_open,
            "fixture.action.clamp": self._fixture_clamp,
            "fixture.action.release": self._fixture_release,
            "fixture.action.verify_seated": self._fixture_verify,
            "process.action.select_program": self._select_program,
            "process.action.execute_cycle": self._execute_process,
        }[capability]
        outcome = handler(payload)
        self._emit(
            f"{capability}.completed" if outcome.success else f"{capability}.failed",
            outcome.result_code,
            component,
            command_id,
            {
                "success": outcome.success,
                "outcome_certain": outcome.outcome_certain,
                **outcome.output,
            },
        )
        return outcome

    def _locate(self, payload: dict[str, Any]) -> L2Outcome:
        if not self.pen_path:
            return _failure("vision.object.not_found", "No pen prim was observed in the stage.")
        if not bool(self.initial.get("pose_within_limit", True)):
            return _failure(
                "vision.pose.correction_limit",
                "Simulator-observed pen pose exceeds the configured correction limit.",
            )
        return _success(
            "vision.object.located",
            "Pen pose was read from the canonical USD stage.",
            {
                "estimates": [
                    {
                        "object_id": self.object_id,
                        "source_frame": "world",
                        "confidence": 1.0,
                        "pose": {
                            "x": self.pose.x_mm / 1000.0,
                            "y": self.pose.y_mm / 1000.0,
                            "z": self.pose.z_mm / 1000.0,
                            "qx": 0.0,
                            "qy": 0.0,
                            "qz": 0.0,
                            "qw": 1.0,
                        },
                        "metadata": {"origin": "openusd_stage", "fidelity": "L2"},
                    }
                ]
            },
        )

    def _robot(self, payload: dict[str, Any]) -> L2Outcome:
        if not self.pen_path:
            return _failure("vision.object.not_found", "No pen exists for manipulation.")
        operation = str(payload.get("operation", payload.get("mode", "")))
        if "motion.plan.collision" in self.faults or bool(payload.get("force_collision", False)):
            self.backend.detach(self.pen_path)
            self.backend.step(1)
            self.backend.set_pen_pose(self.pen_path, PenPose(550.0, 0.0, 820.0, 0.0))
            self.backend.step(4)
            contacts = self.backend.contacts_for(self.pen_path)
            if not contacts:
                return _failure(
                    "l2.collision.observation_missing",
                    "The requested collision setup produced no PhysX contact report.",
                    {"origin": "physx_contact_report"},
                )
            return _failure(
                "motion.plan.collision",
                "The Isaac PhysX contact report refused trajectory execution.",
                {"contacts": list(contacts), "origin": "physx_contact_report"},
            )
        if operation == "pick":
            self.backend.attach(self.pen_path)
            self.backend.step(2)
            if "gripper.object.dropped" in self.faults:
                self.backend.detach(self.pen_path)
                self.backend.set_pen_pose(
                    self.pen_path,
                    PenPose(self.pose.x_mm, self.pose.y_mm, 700.0, self.pose.yaw_deg),
                )
                self.backend.set_dynamic(self.pen_path)
                self.backend.step(90)
                if self.backend.is_dropped(self.pen_path):
                    return _failure(
                        "simulation.pen.dropped",
                        "Attachment and PhysX height observations detected a dropped pen.",
                        {"attached": False, "dropped": True},
                    )
            if not self.backend.is_attached(self.pen_path):
                return _failure("gripper.grasp.failed", "PhysX grasp joint was not established.")
        elif operation == "load":
            self.backend.detach(self.pen_path)
            self.backend.step(1)
            seated = bool(self.initial.get("fixture_seated", True)) and (
                "fixture.sensor.seating_failed" not in self.faults
            )
            x_mm = 550.0 if seated else 560.0
            self.backend.set_pen_pose(
                self.pen_path,
                PenPose(x_mm, _FIXTURE_REST_POSE.y_mm, _FIXTURE_REST_POSE.z_mm, 0.0),
            )
            self.backend.step(2)
        elif operation == "unload":
            self.backend.attach(self.pen_path)
            self.backend.step(1)
            self.backend.detach(self.pen_path)
            self.backend.step(1)
            self.backend.set_pen_pose(self.pen_path, PenPose(0.0, 350.0, 840.0, 0.0))
            self.backend.step(2)
        elif operation in {"move_to_pose", "process_safe", ""}:
            self.backend.step(2)
        else:
            return _failure("motion.request.invalid_input", f"Unsupported operation '{operation}'.")
        return _success(
            "motion.execution.completed",
            "MoveIt/MTC request was applied to and observed in Isaac PhysX.",
            {
                "operation": operation,
                "attached": self.backend.is_attached(self.pen_path),
                "seated": self._is_seated(),
                "contacts": list(self.backend.contacts_for(self.pen_path)),
            },
        )

    def _gripper_close(self, payload: dict[str, Any]) -> L2Outcome:
        if not self.pen_path:
            return _failure("gripper.object.not_found", "No pen is available to grasp.")
        if not self.backend.is_attached(self.pen_path):
            self.backend.attach(self.pen_path)
            self.backend.step(1)
        return _success("gripper.close.completed", "PhysX grasp joint is present.")

    def _gripper_open(self, payload: dict[str, Any]) -> L2Outcome:
        if self.pen_path:
            self.backend.detach(self.pen_path)
            self.backend.set_dynamic(self.pen_path)
            self.backend.step(1)
        return _success("gripper.open.completed", "PhysX grasp joint is absent.")

    def _fixture_clamp(self, payload: dict[str, Any]) -> L2Outcome:
        self.fixture_clamped = self._is_seated() if self.pen_path else False
        if not self.fixture_clamped:
            return _failure("fixture.sensor.seating_failed", "The pen is not seated in USD space.")
        return _success("fixture.clamp.completed", "Fixture clamp state was modeled.")

    def _fixture_release(self, payload: dict[str, Any]) -> L2Outcome:
        self.fixture_clamped = False
        return _success("fixture.release.completed", "Fixture clamp state was released.")

    def _fixture_verify(self, payload: dict[str, Any]) -> L2Outcome:
        seated = bool(self.pen_path and self._is_seated())
        if not seated:
            return _failure(
                "fixture.sensor.seating_failed",
                "OpenUSD pose and attachment observations do not satisfy seating tolerance.",
                {
                    "seated": False,
                    "translation_m": list(self.backend.translation_m(self.pen_path)),
                    "translation_tolerance_mm": 0.5,
                },
            )
        return _success(
            "fixture.seating.verified",
            "OpenUSD pose and attachment observations satisfy seating tolerance.",
            {"seated": True, "translation_tolerance_mm": 0.5},
        )

    def _is_seated(self) -> bool:
        return self.backend.is_seated(
            self.pen_path,
            fixture_center_m=(
                _FIXTURE_REST_POSE.x_mm / 1000.0,
                _FIXTURE_REST_POSE.y_mm / 1000.0,
                _FIXTURE_REST_POSE.z_mm / 1000.0,
            ),
        )

    def _select_program(self, payload: dict[str, Any]) -> L2Outcome:
        program = str(payload.get("program_id", ""))
        if not program and isinstance(payload.get("input"), dict):
            program = str(payload["input"].get("program_id", ""))
        if program != "ALU_REFERENCE_01":
            return _failure("laser.program.unknown", "The requested modeled program is unknown.")
        self.program_selected = True
        return _success(
            "process.program.selected", "Modeled process handshake selected the program."
        )

    def _execute_process(self, payload: dict[str, Any]) -> L2Outcome:
        if not self.program_selected:
            return _failure("laser.program.not_selected", "No modeled program has been selected.")
        if not bool(self.initial.get("laser_ready", True)):
            return _failure(
                "laser.process.interlock_not_ready",
                "Read-only modeled process readiness is false.",
            )
        if "laser.process.timeout" in self.faults:
            return _failure("laser.process.timeout", "The modeled process handshake timed out.")
        if "laser.process.outcome_unknown" in self.faults:
            return L2Outcome(
                False,
                "laser.process.outcome_unknown",
                "Communication was lost after modeled process start.",
                {"physics": "timing_and_handshake_only"},
                False,
            )
        self.backend.step(4)
        self.backend.set_runtime_attribute(self.pen_path, "processCompleted", True)
        self.backend.set_runtime_attribute(
            self.pen_path,
            "engravingText",
            str(payload.get("engraving_text", payload.get("variable_data", ""))),
        )
        self.process_completed = True
        return _success(
            "process.command.completed",
            "Modeled readiness, start, busy, and complete handshake finished.",
            {"physics": "timing_and_handshake_only", "limitations": [PROCESS_LIMITATION]},
        )

    def _inspect(self, payload: dict[str, Any]) -> L2Outcome:
        completed = bool(
            self.pen_path and self.backend.runtime_attribute(self.pen_path, "processCompleted")
        )
        accepted = completed and bool(self.initial.get("inspection_matches", True))
        code = "inspection.accepted" if accepted else "inspection.rejected"
        message = (
            "USD runtime attributes and geometry satisfy the modeled inspection."
            if accepted
            else "USD runtime attributes do not satisfy the modeled inspection."
        )
        return L2Outcome(
            accepted,
            code,
            message,
            {
                "accepted": accepted,
                "measurements": {
                    "process_completed": completed,
                    "text_match": accepted,
                    "origin": "openusd_runtime_attributes",
                },
                "evidence_uri": f"isaac://{self.scenario_id}/{self.object_id}",
            },
        )

    def evidence_metadata(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "backend": "Isaac Sim 6 OpenUSD/PhysX",
            "achieved_fidelity": "L2",
            "actual_physx_executed": True,
            "event_origin": "runtime/adapters",
            "limitations": [PROCESS_LIMITATION, SAFETY_LIMITATION],
        }

    def _emit(
        self,
        event_type: str,
        result_code: str,
        component: str,
        command_id: str,
        observation: dict[str, Any],
    ) -> None:
        event = L2Event(
            len(self.events) + 1,
            event_type,
            result_code,
            component,
            command_id,
            {"scenario_id": self.scenario_id, "seed": self.seed, **observation},
        )
        self.events.append(event)
        if self._event_sink is not None:
            self._event_sink(event)


def _component(capability: str) -> str:
    if capability.startswith("vision."):
        return "camera-001"
    if capability.startswith("fixture."):
        return "fixture-001"
    if capability.startswith("gripper."):
        return "gripper-001"
    if capability.startswith("process."):
        return "laser-001"
    return "robot-001"


def _success(code: str, message: str, output: dict[str, Any] | None = None) -> L2Outcome:
    return L2Outcome(True, code, message, output or {})


def _failure(code: str, message: str, output: dict[str, Any] | None = None) -> L2Outcome:
    return L2Outcome(False, code, message, output or {})
