"""Bench testing, on-cell commissioning, and hardware acceptance test suites."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from cellforge_device_sdk.ids import new_command_id, new_trace_id
from cellforge_device_sdk.models import CapabilityCommand, DeviceState

from cellforge_hardware_adapters.devices import (
    CameraVisionHardwareAdapter,
    FixtureHardwareAdapter,
    GripperHardwareAdapter,
    HardwareSafetyStatusAdapter,
    LaserHardwareAdapter,
    RobotHardwareAdapter,
)


@dataclass
class CommissioningTestResult:
    test_id: str
    component_kind: str
    component_id: str
    passed: bool
    result_code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class CommissioningSuiteReport:
    report_id: str
    cell_id: str
    passed: bool
    results: list[CommissioningTestResult]
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


async def run_robot_bench_test(
    adapter: RobotHardwareAdapter | None = None,
) -> list[CommissioningTestResult]:
    adapter = adapter or RobotHardwareAdapter("robot-001")
    await adapter.connect_hardware()
    results: list[CommissioningTestResult] = []

    # 1. Nominal trajectory execution
    traj_payload = (
        '{"trajectory": {"waypoints": [{"x": 0.1, "y": 0.2, "z": 0.3}]}, "velocity_scaling": 0.25}'
    )
    cmd = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="robot_motion.action.execute_trajectory",
        input_payload_json=traj_payload,
        timeout=timedelta(seconds=5.0),
    )
    res = await adapter.execute(cmd)
    results.append(
        CommissioningTestResult(
            test_id="robot_nominal_trajectory",
            component_kind="robot",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res.success,
            result_code=res.result_code,
            message=res.result_message,
        )
    )

    # 2. Protective stop fault handling
    adapter.client.set_protective_stop(True)
    res_fault = await adapter.execute(cmd)
    adapter.client.set_protective_stop(False)
    results.append(
        CommissioningTestResult(
            test_id="robot_protective_stop_fault",
            component_kind="robot",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=not res_fault.success and "protective_stop" in res_fault.result_code,
            result_code=res_fault.result_code,
            message=res_fault.result_message,
        )
    )

    return results


async def run_gripper_bench_test(
    adapter: GripperHardwareAdapter | None = None,
) -> list[CommissioningTestResult]:
    adapter = adapter or GripperHardwareAdapter("gripper-001")
    await adapter.connect_hardware()
    results: list[CommissioningTestResult] = []

    # 1. Open
    cmd_open = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="gripper.action.open",
        input_payload_json="{}",
        timeout=timedelta(seconds=5.0),
    )
    res_open = await adapter.execute(cmd_open)
    results.append(
        CommissioningTestResult(
            test_id="gripper_nominal_open",
            component_kind="gripper",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res_open.success,
            result_code=res_open.result_code,
            message=res_open.result_message,
        )
    )

    # 2. Close nominal
    cmd_close = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="gripper.action.close",
        input_payload_json="{}",
        timeout=timedelta(seconds=5.0),
    )
    res_close = await adapter.execute(cmd_close)
    results.append(
        CommissioningTestResult(
            test_id="gripper_nominal_close",
            component_kind="gripper",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res_close.success,
            result_code=res_close.result_code,
            message=res_close.result_message,
        )
    )

    # 3. Grip loss fault
    adapter.set_simulate_grip_loss(True)
    res_grip_loss = await adapter.execute(cmd_close)
    adapter.set_simulate_grip_loss(False)
    results.append(
        CommissioningTestResult(
            test_id="gripper_grip_loss_fault",
            component_kind="gripper",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=not res_grip_loss.success and "grip_failed" in res_grip_loss.result_code,
            result_code=res_grip_loss.result_code,
            message=res_grip_loss.result_message,
        )
    )

    return results


async def run_fixture_bench_test(
    adapter: FixtureHardwareAdapter | None = None,
) -> list[CommissioningTestResult]:
    adapter = adapter or FixtureHardwareAdapter("fixture-001")
    await adapter.connect_hardware()
    results: list[CommissioningTestResult] = []

    # 1. Clamp
    cmd_clamp = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="fixture.action.clamp",
        input_payload_json="{}",
        timeout=timedelta(seconds=5.0),
    )
    res_clamp = await adapter.execute(cmd_clamp)
    results.append(
        CommissioningTestResult(
            test_id="fixture_nominal_clamp",
            component_kind="fixture",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res_clamp.success,
            result_code=res_clamp.result_code,
            message=res_clamp.result_message,
        )
    )

    # 2. Verify seated nominal
    cmd_verify = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="fixture.action.verify_seated",
        input_payload_json="{}",
        timeout=timedelta(seconds=5.0),
    )
    res_verify = await adapter.execute(cmd_verify)
    results.append(
        CommissioningTestResult(
            test_id="fixture_nominal_verify_seated",
            component_kind="fixture",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res_verify.success,
            result_code=res_verify.result_code,
            message=res_verify.result_message,
        )
    )

    # 3. Seating failure fault
    adapter.set_seating_sensor_state(False)
    res_seat_fail = await adapter.execute(cmd_verify)
    adapter.set_seating_sensor_state(True)
    results.append(
        CommissioningTestResult(
            test_id="fixture_seating_failure_fault",
            component_kind="fixture",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=not res_seat_fail.success and "seating_failed" in res_seat_fail.result_code,
            result_code=res_seat_fail.result_code,
            message=res_seat_fail.result_message,
        )
    )

    return results


async def run_camera_bench_test(
    adapter: CameraVisionHardwareAdapter | None = None,
) -> list[CommissioningTestResult]:
    adapter = adapter or CameraVisionHardwareAdapter("camera-001")
    await adapter.connect_hardware()
    results: list[CommissioningTestResult] = []

    # 1. Locate object nominal
    cmd_locate = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="vision.action.locate_object",
        input_payload_json='{"object_type": "pen", "profile_id": "pen_reference"}',
        timeout=timedelta(seconds=5.0),
    )
    res_locate = await adapter.execute(cmd_locate)
    results.append(
        CommissioningTestResult(
            test_id="camera_nominal_locate",
            component_kind="camera",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res_locate.success,
            result_code=res_locate.result_code,
            message=res_locate.result_message,
        )
    )

    # 2. Inspect object nominal
    inspect_payload = (
        '{"inspection_profile": "contrast_and_text_match", '
        '"expected": {"engraving_text": "CELLFORGE-01"}}'
    )
    cmd_inspect = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="vision.action.inspect_object",
        input_payload_json=inspect_payload,
        timeout=timedelta(seconds=5.0),
    )
    res_inspect = await adapter.execute(cmd_inspect)
    results.append(
        CommissioningTestResult(
            test_id="camera_nominal_inspect",
            component_kind="camera",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res_inspect.success,
            result_code=res_inspect.result_code,
            message=res_inspect.result_message,
        )
    )

    # 3. Object not found fault
    adapter.stream.set_bench_scene(object_present=False)
    res_no_obj = await adapter.execute(cmd_locate)
    adapter.stream.set_bench_scene(object_present=True)
    results.append(
        CommissioningTestResult(
            test_id="camera_object_not_found_fault",
            component_kind="camera",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=not res_no_obj.success and "object.not_found" in res_no_obj.result_code,
            result_code=res_no_obj.result_code,
            message=res_no_obj.result_message,
        )
    )

    return results


async def run_laser_bench_test(
    adapter: LaserHardwareAdapter | None = None,
) -> list[CommissioningTestResult]:
    adapter = adapter or LaserHardwareAdapter("laser-001")
    await adapter.connect_hardware()
    results: list[CommissioningTestResult] = []

    # 1. Select program nominal
    sel_payload = (
        '{"program_id": "ALU_REFERENCE_01", "variable_data": {"engraving_text": "CELLFORGE-01"}}'
    )
    cmd_select = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="process.action.select_program",
        input_payload_json=sel_payload,
        timeout=timedelta(seconds=5.0),
    )
    res_select = await adapter.execute(cmd_select)
    results.append(
        CommissioningTestResult(
            test_id="laser_nominal_select_program",
            component_kind="laser",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res_select.success,
            result_code=res_select.result_code,
            message=res_select.result_message,
        )
    )

    # 2. Execute cycle nominal
    cycle_payload = (
        '{"program_id": "ALU_REFERENCE_01", '
        '"variable_data": {"engraving_text": "CELLFORGE-01"}, '
        '"recipe_id": "pen-recipe-reference", "recipe_version": 1}'
    )
    cmd_cycle = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="process.action.execute_cycle",
        input_payload_json=cycle_payload,
        timeout=timedelta(seconds=5.0),
    )
    res_cycle = await adapter.execute(cmd_cycle)
    results.append(
        CommissioningTestResult(
            test_id="laser_nominal_execute_cycle",
            component_kind="laser",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=res_cycle.success and res_cycle.outcome_certain,
            result_code=res_cycle.result_code,
            message=res_cycle.result_message,
        )
    )

    # 3. Interlock not ready fault
    adapter.client.set_interlock_status(False)
    res_interlock = await adapter.execute(cmd_cycle)
    adapter.client.set_interlock_status(True)
    results.append(
        CommissioningTestResult(
            test_id="laser_interlock_not_ready_fault",
            component_kind="laser",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=not res_interlock.success and "interlock_not_ready" in res_interlock.result_code,
            result_code=res_interlock.result_code,
            message=res_interlock.result_message,
        )
    )

    # 4. Explicit uncertain-outcome handling on communication drop
    # Restore ready state before starting the cycle
    adapter.mark_ready()
    adapter.client.set_drop_connection_during_cycle(True)
    res_uncertain = await adapter.execute(cmd_cycle)
    adapter.client.set_drop_connection_during_cycle(False)
    results.append(
        CommissioningTestResult(
            test_id="laser_uncertain_outcome_on_comm_loss",
            component_kind="laser",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=(not res_uncertain.success)
            and (not res_uncertain.outcome_certain)
            and ("outcome_unknown" in res_uncertain.result_code),
            result_code=res_uncertain.result_code,
            message=res_uncertain.result_message,
        )
    )

    return results


async def run_safety_bench_test(
    adapter: HardwareSafetyStatusAdapter | None = None,
) -> list[CommissioningTestResult]:
    adapter = adapter or HardwareSafetyStatusAdapter("safety-status-001")
    adapter.mark_ready()
    results: list[CommissioningTestResult] = []

    # 1. Nominal healthy status
    adapter.set_safety_health(True)
    results.append(
        CommissioningTestResult(
            test_id="safety_nominal_healthy",
            component_kind="safety_status",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=adapter.state_publisher.snapshot.ready,
            result_code="safety.healthy",
            message="Independent rated safety hardware reports healthy status.",
        )
    )

    # 2. Unhealthy status refusal
    adapter.set_safety_health(False)
    results.append(
        CommissioningTestResult(
            test_id="safety_unhealthy_transition",
            component_kind="safety_status",
            component_id=adapter.state_publisher.snapshot.component_instance_id,
            passed=adapter.state_publisher.snapshot.state == DeviceState.FAULT,
            result_code="safety.status.unhealthy",
            message="Independent rated safety hardware reports unhealthy state; fault logged.",
        )
    )
    adapter.set_safety_health(True)

    return results


async def run_hardware_commissioning_suite(
    cell_id: str = "0d3c6b63-a57f-4207-8638-e4cf76efec90",
) -> CommissioningSuiteReport:
    """Execute complete on-cell commissioning & hardware acceptance suite."""
    all_results: list[CommissioningTestResult] = []

    all_results.extend(await run_robot_bench_test())
    all_results.extend(await run_gripper_bench_test())
    all_results.extend(await run_fixture_bench_test())
    all_results.extend(await run_camera_bench_test())
    all_results.extend(await run_laser_bench_test())
    all_results.extend(await run_safety_bench_test())

    overall_passed = all(r.passed for r in all_results)
    return CommissioningSuiteReport(
        report_id=f"comm-rep-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        cell_id=cell_id,
        passed=overall_passed,
        results=all_results,
    )
