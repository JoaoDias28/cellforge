from __future__ import annotations

from typing import Any

import pytest
from cellforge_simulation.l2_runtime import IsaacL2Runtime, L2RuntimeError
from cellforge_simulation.physical import PenPose


class Backend:
    fidelity = "L2"

    def __init__(self) -> None:
        self.pose = PenPose(0.0, 0.0, 32.0, 0.0)
        self.attached = False
        self.attributes: dict[str, str | bool] = {}
        self.contact_paths: tuple[str, ...] = ()
        self.steps = 0

    def spawn_pen(self, object_id: str, pose: PenPose) -> str:
        self.pose = pose
        return f"/World/SpawnedProducts/{object_id}"

    def set_pen_pose(self, pen_path: str, pose: PenPose) -> None:
        self.pose = pose
        if pose.z_mm == 820.0:
            self.contact_paths = ("/World/Fixture/Base",)

    def attach(self, pen_path: str, tool_path: str = "/World/Robot/GripperTcp") -> str:
        self.attached = True
        return "/World/PhysicsJoints/grasp"

    def detach(self, pen_path: str) -> None:
        self.attached = False

    def set_dynamic(self, pen_path: str) -> None:
        pass

    def is_attached(self, pen_path: str) -> bool:
        return self.attached

    def is_seated(self, pen_path: str, **kwargs: Any) -> bool:
        return not self.attached and self.pose == PenPose(550.0, 0.0, 834.0, 0.0)

    def is_dropped(self, pen_path: str, **kwargs: Any) -> bool:
        return not self.attached and self.pose.z_mm < 750.0

    def translation_m(self, pen_path: str) -> tuple[float, float, float]:
        return (self.pose.x_mm / 1000.0, self.pose.y_mm / 1000.0, self.pose.z_mm / 1000.0)

    def contacts_for(self, pen_path: str) -> tuple[str, ...]:
        return self.contact_paths

    def set_runtime_attribute(self, pen_path: str, name: str, value: str | bool) -> None:
        self.attributes[name] = value

    def runtime_attribute(self, pen_path: str, name: str) -> str | bool | None:
        return self.attributes.get(name)

    def step(self, count: int = 1) -> None:
        self.steps += count


def scenario(
    *,
    seed: int = 1001,
    initial: dict[str, Any] | None = None,
    faults: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "scenario": {"id": f"l2-{seed}", "name": "test", "seed": seed},
        "initial_state": {
            "product_present": True,
            "safety_healthy": True,
            "laser_ready": True,
            **(initial or {}),
        },
        "faults": [
            {"at": "test", "target": "robot-001", "fault": fault, "parameters": {}}
            for fault in faults or []
        ],
    }


def execute(runtime: IsaacL2Runtime, capability: str, **payload: Any):
    return runtime.execute(capability, payload, command_id="command-001")


def test_nominal_outcomes_are_derived_from_backend_observations() -> None:
    backend = Backend()
    runtime = IsaacL2Runtime(backend, scenario())

    assert execute(runtime, "vision.action.locate_object").success
    assert execute(runtime, "robot_motion.action.execute_trajectory", operation="pick").success
    assert backend.attached
    assert execute(runtime, "robot_motion.action.execute_trajectory", operation="load").success
    assert execute(runtime, "fixture.action.verify_seated").success
    assert execute(
        runtime, "robot_motion.action.execute_trajectory", operation="process_safe"
    ).success
    assert execute(runtime, "process.action.select_program", program_id="ALU_REFERENCE_01").success
    assert execute(runtime, "process.action.execute_cycle", engraving_text="CELLFORGE").success
    inspection = execute(runtime, "vision.action.inspect_object")
    assert inspection.success
    assert inspection.output["measurements"]["origin"] == "openusd_runtime_attributes"
    assert execute(runtime, "robot_motion.action.execute_trajectory", operation="unload").success
    assert backend.steps > 0
    assert all(event.origin == "isaac_l2_adapter" for event in runtime.events)


@pytest.mark.parametrize(
    ("initial", "faults", "capability", "payload", "expected"),
    [
        (
            {"product_present": False},
            [],
            "vision.action.locate_object",
            {},
            "vision.object.not_found",
        ),
        (
            {"pose_within_limit": False},
            [],
            "vision.action.locate_object",
            {},
            "vision.pose.correction_limit",
        ),
        (
            {},
            ["motion.plan.collision"],
            "robot_motion.action.execute_trajectory",
            {"operation": "pick"},
            "motion.plan.collision",
        ),
    ],
)
def test_simulator_fault_boundaries(
    initial: dict[str, Any],
    faults: list[str],
    capability: str,
    payload: dict[str, Any],
    expected: str,
) -> None:
    runtime = IsaacL2Runtime(Backend(), scenario(initial=initial, faults=faults))
    outcome = execute(runtime, capability, **payload)
    assert not outcome.success
    assert outcome.result_code == expected


def test_drop_and_failed_seating_require_backend_observations() -> None:
    dropped = IsaacL2Runtime(Backend(), scenario(faults=["gripper.object.dropped"]))
    drop = execute(dropped, "robot_motion.action.execute_trajectory", operation="pick")
    assert drop.result_code == "simulation.pen.dropped"

    seating = IsaacL2Runtime(Backend(), scenario(faults=["fixture.sensor.seating_failed"]))
    assert execute(seating, "robot_motion.action.execute_trajectory", operation="pick").success
    assert execute(seating, "robot_motion.action.execute_trajectory", operation="load").success
    verification = execute(seating, "fixture.action.verify_seated")
    assert verification.result_code == "fixture.sensor.seating_failed"


@pytest.mark.parametrize(
    ("initial", "fault", "expected", "certain"),
    [
        ({"laser_ready": False}, None, "laser.process.interlock_not_ready", True),
        ({}, "laser.process.timeout", "laser.process.timeout", True),
        ({}, "laser.process.outcome_unknown", "laser.process.outcome_unknown", False),
    ],
)
def test_process_readiness_timeout_and_unknown_outcome(
    initial: dict[str, Any], fault: str | None, expected: str, certain: bool
) -> None:
    runtime = IsaacL2Runtime(
        Backend(), scenario(initial=initial, faults=[] if fault is None else [fault])
    )
    assert execute(runtime, "process.action.select_program", program_id="ALU_REFERENCE_01").success
    outcome = execute(runtime, "process.action.execute_cycle")
    assert outcome.result_code == expected
    assert outcome.outcome_certain is certain


def test_report_metadata_refuses_a_non_l2_backend() -> None:
    backend = Backend()
    backend.fidelity = "L0"
    with pytest.raises(L2RuntimeError, match="L2 Isaac PhysX backend"):
        IsaacL2Runtime(backend, scenario())

    runtime = IsaacL2Runtime(Backend(), scenario())
    metadata = runtime.evidence_metadata()
    assert metadata["actual_physx_executed"] is True
    assert metadata["event_origin"] == "runtime/adapters"
    assert any("beam/material" in item for item in metadata["limitations"])
