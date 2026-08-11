"""Deterministic pen-cycle model shared by CPU checks and the Isaac Sim adapter.

This module models state transitions, bounds, and evidence.  It does not claim to execute PhysX;
the Isaac edge in :mod:`pen_physics_backend` owns that integration.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from cellforge_simulation.models import FidelityLevel, ScenarioDefinition

DROP_FAULT = "simulation.pen.dropped"
SEATING_FAULT = "fixture.sensor.seating_failed"
COLLISION_FAULT = "motion.plan.collision"
PROCESS_LIMITATION = (
    "Laser readiness, handshake, and cycle timing are modeled; beam/material interaction, heat, "
    "plume, optics, engraving contrast, text fidelity, and mark quality are not modeled or "
    "qualified."
)
SAFETY_LIMITATION = (
    "Simulation status and refusal are ordinary engineering controls, not functional-safety "
    "enforcement. Independent rated hardware remains authoritative."
)


class PhysicalSimulationError(ValueError):
    """Invalid physical-simulation configuration or command."""


class PenState(StrEnum):
    IN_CARRIER = "IN_CARRIER"
    ATTACHED = "ATTACHED"
    SEATED = "SEATED"
    PROCESSED = "PROCESSED"
    UNLOADED = "UNLOADED"
    DROPPED = "DROPPED"
    FAULT = "FAULT"


@dataclass(frozen=True, slots=True)
class SpawnBounds:
    """Explicit uniform randomization bounds in millimetres and degrees."""

    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float
    yaw_min_deg: float
    yaw_max_deg: float

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(not isinstance(value, int | float) for value in values.values()):
            raise PhysicalSimulationError("physical.bounds.invalid: all bounds must be numeric")
        if self.x_min_mm > self.x_max_mm:
            raise PhysicalSimulationError("physical.bounds.invalid: x_min_mm exceeds x_max_mm")
        if self.y_min_mm > self.y_max_mm:
            raise PhysicalSimulationError("physical.bounds.invalid: y_min_mm exceeds y_max_mm")
        if self.yaw_min_deg > self.yaw_max_deg:
            raise PhysicalSimulationError(
                "physical.bounds.invalid: yaw_min_deg exceeds yaw_max_deg"
            )
        if max(abs(self.x_min_mm), abs(self.x_max_mm), abs(self.y_min_mm), abs(self.y_max_mm)) > 10:
            raise PhysicalSimulationError("physical.bounds.unbounded: position limit exceeds 10 mm")
        if max(abs(self.yaw_min_deg), abs(self.yaw_max_deg)) > 15:
            raise PhysicalSimulationError("physical.bounds.unbounded: yaw limit exceeds 15 degrees")


@dataclass(frozen=True, slots=True)
class PenPose:
    x_mm: float
    y_mm: float
    z_mm: float
    yaw_deg: float

    def as_json(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MotionCommand:
    """Planner-neutral Task 019 request projection, not a planner implementation."""

    endpoint: str
    operation: str
    object_id: str
    tool_frame: str
    named_safe_pose: str
    plan_only: bool

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CycleEvent:
    sequence: int
    event_type: str
    result_code: str = ""
    payload: dict[str, Any] | None = None

    def as_json(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "result_code": self.result_code,
        }
        if self.payload is not None:
            value["payload"] = self.payload
        return value


@dataclass(frozen=True, slots=True)
class CycleResult:
    seed: int
    passed: bool
    final_state: PenState
    fault_code: str
    sampled_pose: PenPose
    events: tuple[CycleEvent, ...]
    motion_commands: tuple[MotionCommand, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "passed": self.passed,
            "final_state": self.final_state.value,
            "fault_code": self.fault_code,
            "sampled_pose": self.sampled_pose.as_json(),
            "events": [event.as_json() for event in self.events],
            "motion_commands": [command.as_json() for command in self.motion_commands],
        }


DEFAULT_BOUNDS = SpawnBounds(-1.0, 1.0, -1.0, 1.0, -3.0, 3.0)


def sample_pen_pose(seed: int, bounds: SpawnBounds = DEFAULT_BOUNDS) -> PenPose:
    """Sample a pose without touching process-global random state."""

    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise PhysicalSimulationError("physical.seed.invalid: seed must be a non-negative integer")
    generator = random.Random(seed)
    return PenPose(
        x_mm=round(generator.uniform(bounds.x_min_mm, bounds.x_max_mm), 6),
        y_mm=round(generator.uniform(bounds.y_min_mm, bounds.y_max_mm), 6),
        z_mm=32.0,
        yaw_deg=round(generator.uniform(bounds.yaw_min_deg, bounds.yaw_max_deg), 6),
    )


class PenCycle:
    """Deterministic nominal/fault cycle with explicit behavior-tree and MTC boundaries."""

    def __init__(
        self,
        seed: int,
        *,
        bounds: SpawnBounds = DEFAULT_BOUNDS,
        product_present: bool = True,
        drop_after_pick: bool = False,
        fail_seating: bool = False,
        collision_stage: str = "",
    ) -> None:
        if collision_stage not in {"", "pick", "load", "process_safe", "unload"}:
            raise PhysicalSimulationError(
                "physical.collision_stage.invalid: expected pick, load, process_safe, or unload"
            )
        self.seed = seed
        self.pose = sample_pen_pose(seed, bounds)
        self.product_present = product_present
        self.drop_after_pick = drop_after_pick
        self.fail_seating = fail_seating
        self.collision_stage = collision_stage
        self.state = PenState.IN_CARRIER
        self._events: list[CycleEvent] = []
        self._commands: list[MotionCommand] = []

    def _emit(
        self, event_type: str, result_code: str = "", payload: dict[str, Any] | None = None
    ) -> None:
        self._events.append(CycleEvent(len(self._events) + 1, event_type, result_code, payload))

    def _motion(self, operation: str, named_safe_pose: str) -> bool:
        endpoint = (
            "/skills/move_to_pose"
            if operation == "process_safe"
            else "/skills/execute_manipulation"
        )
        self._commands.append(
            MotionCommand(
                endpoint=endpoint,
                operation=operation,
                object_id=f"pen-{self.seed:08d}",
                tool_frame="gripper_tcp",
                named_safe_pose=named_safe_pose,
                plan_only=False,
            )
        )
        self._emit(
            "motion.requested",
            payload={"operation": operation, "named_safe_pose": named_safe_pose},
        )
        if self.collision_stage == operation:
            self.state = PenState.FAULT
            self._emit("motion.failed", COLLISION_FAULT, {"stage": operation})
            return False
        self._emit("motion.completed", payload={"operation": operation})
        return True

    def _result(self, passed: bool, fault_code: str = "") -> CycleResult:
        return CycleResult(
            seed=self.seed,
            passed=passed,
            final_state=self.state,
            fault_code=fault_code,
            sampled_pose=self.pose,
            events=tuple(self._events),
            motion_commands=tuple(self._commands),
        )

    def run(self) -> CycleResult:
        self._emit(
            "product.spawned",
            payload={"object_id": f"pen-{self.seed:08d}", "pose": self.pose.as_json()},
        )
        if not self.product_present:
            self.state = PenState.FAULT
            self._emit("vision.object_absent", "vision.object.not_found")
            return self._result(False, "vision.object.not_found")

        if not self._motion("pick", "load_safe"):
            return self._result(False, COLLISION_FAULT)
        self.state = PenState.ATTACHED
        self._emit("grasp.attached", payload={"tool_frame": "gripper_tcp"})
        if self.drop_after_pick:
            self.state = PenState.DROPPED
            self._emit("grasp.detached", DROP_FAULT)
            self._emit("product.dropped", DROP_FAULT, {"detection": "attachment_and_height"})
            return self._result(False, DROP_FAULT)

        if not self._motion("load", "load_safe"):
            return self._result(False, COLLISION_FAULT)
        self._emit("grasp.detached", payload={"destination": "fixture-001"})
        if self.fail_seating:
            self.state = PenState.FAULT
            self._emit("fixture.seating.false", SEATING_FAULT)
            return self._result(False, SEATING_FAULT)
        self.state = PenState.SEATED
        self._emit(
            "fixture.seating.true",
            payload={"translation_tolerance_mm": 0.5, "angular_tolerance_deg": 1.0},
        )
        self._emit("fixture.clamped")

        if not self._motion("process_safe", "process_safe"):
            return self._result(False, COLLISION_FAULT)
        self._emit("process.program.selected")
        self._emit("process.command.completed", payload={"physics": "timing_and_handshake_only"})
        self.state = PenState.PROCESSED

        self._emit("fixture.released")
        if not self._motion("unload", "unload_safe"):
            return self._result(False, COLLISION_FAULT)
        self._emit("grasp.attached", payload={"source": "fixture-001"})
        self._emit("grasp.detached", payload={"destination": "output"})
        self.state = PenState.UNLOADED
        self._emit("cycle.completed")
        return self._result(True)


def cycle_from_scenario(scenario: ScenarioDefinition) -> PenCycle:
    """Construct the physical cycle from a strict canonical Task 018 scenario."""

    if scenario.requested_fidelity < FidelityLevel.L2:
        raise PhysicalSimulationError(
            "physical.scenario.fidelity_too_low: Task 020 scenarios must request L2 or L3"
        )

    def limits(name: str, default_minimum: float, default_maximum: float) -> tuple[float, float]:
        distribution = scenario.randomization.get(name)
        if distribution is None:
            return default_minimum, default_maximum
        return distribution.minimum, distribution.maximum

    x_limits = limits("product_x_mm", -1.0, 1.0)
    y_limits = limits("product_y_mm", -1.0, 1.0)
    yaw_limits = limits("product_yaw_deg", -3.0, 3.0)
    drop_after_pick = any(
        fault.at == "after_pick"
        and fault.target == "gripper-001"
        and fault.fault == "gripper.object.dropped"
        for fault in scenario.faults
    )
    fail_seating = any(
        fault.at == "after_load" and fault.target == "fixture-001" and fault.fault == SEATING_FAULT
        for fault in scenario.faults
    )
    product_present = scenario.initial_state.get("product_present", True)
    if not isinstance(product_present, bool):
        raise PhysicalSimulationError(
            "physical.scenario.product_present: expected a boolean initial state"
        )
    return PenCycle(
        scenario.seed,
        bounds=SpawnBounds(
            x_limits[0], x_limits[1], y_limits[0], y_limits[1], yaw_limits[0], yaw_limits[1]
        ),
        product_present=product_present,
        drop_after_pick=drop_after_pick,
        fail_seating=fail_seating,
    )


def build_seed_report(
    seed_count: int = 100, *, first_seed: int = 0, bounds: SpawnBounds = DEFAULT_BOUNDS
) -> dict[str, Any]:
    if (
        isinstance(seed_count, bool)
        or not isinstance(seed_count, int)
        or not 1 <= seed_count <= 10000
    ):
        raise PhysicalSimulationError("physical.report.invalid_count: seeds must be in [1, 10000]")
    if isinstance(first_seed, bool) or not isinstance(first_seed, int) or first_seed < 0:
        raise PhysicalSimulationError(
            "physical.report.invalid_seed: first seed must be non-negative"
        )
    runs = [
        PenCycle(seed, bounds=bounds).run() for seed in range(first_seed, first_seed + seed_count)
    ]
    failures = [result.seed for result in runs if not result.passed]
    return {
        "schema_version": "0.1.0",
        "kind": "cellforge.pen_physical_seed_report",
        "generator": "cellforge_simulation.physical.v1",
        "backend": "deterministic_physical_contract_model",
        "requested_fidelity": "L2",
        "achieved_fidelity": "CPU_MODEL_ONLY",
        "actual_physx_executed": False,
        "seed_range": {"first": first_seed, "count": seed_count},
        "bounds": asdict(bounds),
        "summary": {"passed": seed_count - len(failures), "failed": len(failures)},
        "failed_seeds": failures,
        "runs": [result.as_json() for result in runs],
        "limitations": [PROCESS_LIMITATION, SAFETY_LIMITATION],
    }


def write_seed_report(path: Path, report: dict[str, Any]) -> None:
    """Write stable report JSON; callers choose a generated-output location."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
