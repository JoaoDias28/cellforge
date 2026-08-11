from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SIMULATION_ROOT = ROOT / "ros_ws" / "src" / "cellforge_simulation"
if str(SIMULATION_ROOT) not in sys.path:
    sys.path.insert(0, str(SIMULATION_ROOT))

from cellforge_simulation.models import load_scenario  # noqa: E402
from cellforge_simulation.physical import (  # noqa: E402
    COLLISION_FAULT,
    DROP_FAULT,
    SEATING_FAULT,
    PenCycle,
    PhysicalSimulationError,
    SpawnBounds,
    build_seed_report,
    cycle_from_scenario,
    sample_pen_pose,
    write_seed_report,
)


def test_seeded_pose_is_bounded_and_reproducible() -> None:
    bounds = SpawnBounds(-2.0, 2.0, -1.0, 1.0, -4.0, 4.0)
    first = sample_pen_pose(42, bounds)
    assert first == sample_pen_pose(42, bounds)
    assert -2.0 <= first.x_mm <= 2.0
    assert -1.0 <= first.y_mm <= 1.0
    assert -4.0 <= first.yaw_deg <= 4.0


def test_invalid_seed_is_rejected() -> None:
    with pytest.raises(PhysicalSimulationError, match="physical.seed.invalid"):
        sample_pen_pose(-1)


def test_invalid_bounds_fail_closed() -> None:
    with pytest.raises(PhysicalSimulationError, match="position limit exceeds 10 mm"):
        SpawnBounds(-1, 11, -1, 1, -1, 1)
    with pytest.raises(PhysicalSimulationError, match="yaw limit exceeds 15 degrees"):
        SpawnBounds(-1, 1, -1, 1, -1, 16)


def test_nominal_pick_load_process_safe_pose_and_unload() -> None:
    result = PenCycle(1001).run()
    assert result.passed
    assert result.final_state == "UNLOADED"
    assert [command.operation for command in result.motion_commands] == [
        "pick",
        "load",
        "process_safe",
        "unload",
    ]
    event_types = [event.event_type for event in result.events]
    assert "fixture.seating.true" in event_types
    assert "process.command.completed" in event_types
    assert event_types[-1] == "cycle.completed"


def test_drop_is_detected_before_fixture_or_process_command() -> None:
    result = PenCycle(7, drop_after_pick=True).run()
    assert not result.passed
    assert result.fault_code == DROP_FAULT
    events = [event.event_type for event in result.events]
    assert "product.dropped" in events
    assert "fixture.seating.true" not in events
    assert "process.command.completed" not in events


def test_failed_seating_is_detected_before_process_command() -> None:
    result = PenCycle(8, fail_seating=True).run()
    assert not result.passed
    assert result.fault_code == SEATING_FAULT
    events = [event.event_type for event in result.events]
    assert "fixture.seating.false" in events
    assert "process.command.completed" not in events


@pytest.mark.parametrize(
    ("filename", "expected_fault"),
    [
        ("nominal.yaml", ""),
        ("dropped_pen.yaml", DROP_FAULT),
        ("failed_seating.yaml", SEATING_FAULT),
    ],
)
def test_canonical_l2_scenarios_drive_cycle_faults(filename: str, expected_fault: str) -> None:
    scenario = load_scenario(
        ROOT / "examples" / "pen_engraving" / "physical" / "scenarios" / filename
    )
    result = cycle_from_scenario(scenario).run()
    assert result.fault_code == expected_fault
    assert result.passed is (not expected_fault)


def test_l0_scenario_cannot_be_claimed_as_physical_cycle() -> None:
    scenario = load_scenario(ROOT / "examples" / "pen_engraving" / "scenarios" / "nominal.yaml")
    with pytest.raises(PhysicalSimulationError, match="fidelity_too_low"):
        cycle_from_scenario(scenario)


@pytest.mark.parametrize("stage", ["pick", "load", "process_safe", "unload"])
def test_collision_stops_cycle_with_stable_fault(stage: str) -> None:
    result = PenCycle(9, collision_stage=stage).run()
    assert not result.passed
    assert result.fault_code == COLLISION_FAULT
    assert any(event.result_code == COLLISION_FAULT for event in result.events)


def test_absent_product_and_invalid_collision_stage_fail() -> None:
    result = PenCycle(11, product_present=False).run()
    assert result.fault_code == "vision.object.not_found"
    assert not result.motion_commands
    with pytest.raises(PhysicalSimulationError, match="collision_stage.invalid"):
        PenCycle(1, collision_stage="laser")


def test_100_seed_report_is_exactly_reproducible_and_writable(tmp_path: Path) -> None:
    first = build_seed_report()
    second = build_seed_report()
    assert first == second
    assert first["seed_range"] == {"first": 0, "count": 100}
    assert first["summary"] == {"passed": 100, "failed": 0}
    assert first["failed_seeds"] == []
    assert first["actual_physx_executed"] is False
    output = tmp_path / "report.json"
    write_seed_report(output, first)
    assert json.loads(output.read_text(encoding="utf-8")) == first


def test_report_rejects_invalid_seed_ranges() -> None:
    with pytest.raises(PhysicalSimulationError, match="invalid_count"):
        build_seed_report(0)
    with pytest.raises(PhysicalSimulationError, match="invalid_seed"):
        build_seed_report(1, first_seed=-1)


def test_scene_contains_required_geometry_and_physics_contracts() -> None:
    scene = (ROOT / "examples" / "pen_engraving" / "scene.usda").read_text(encoding="utf-8")
    for token in (
        'def Xform "Robot"',
        'def Xform "Gripper"',
        'def Capsule "PenTemplate"',
        'def Xform "InputCarrier"',
        'def Xform "Fixture"',
        'def Xform "Laser"',
        'def Xform "Camera"',
        "PhysicsCollisionAPI",
        "PhysicsRigidBodyAPI",
    ):
        assert token in scene


def test_isaac_backend_is_importable_without_loading_isaac_modules() -> None:
    from cellforge_simulation.pen_physics_backend import IsaacPenPhysicsBackend

    with pytest.raises(PhysicalSimulationError, match="stage_missing"):
        IsaacPenPhysicsBackend(None)
