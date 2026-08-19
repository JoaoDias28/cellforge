"""Tests for physical hardware device adapters and commissioning suite."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_device_sdk"
MOCK_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_mock_adapters"
HW_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_hardware_adapters"
sys.path.insert(0, str(SDK_ROOT))
sys.path.insert(0, str(MOCK_ROOT))
sys.path.insert(0, str(HW_ROOT))

import pytest  # noqa: E402
from cellforge_device_sdk.contract import run_adapter_contract_suite  # noqa: E402
from cellforge_device_sdk.ids import new_command_id, new_trace_id  # noqa: E402
from cellforge_device_sdk.models import CapabilityCommand  # noqa: E402
from cellforge_hardware_adapters.commissioning import (  # noqa: E402
    run_camera_bench_test,
    run_fixture_bench_test,
    run_gripper_bench_test,
    run_hardware_commissioning_suite,
    run_laser_bench_test,
    run_robot_bench_test,
    run_safety_bench_test,
)
from cellforge_hardware_adapters.devices import (  # noqa: E402
    CameraVisionHardwareAdapter,
    FixtureHardwareAdapter,
    GripperHardwareAdapter,
    HardwareDeviceKind,
    HardwareSafetyStatusAdapter,
    LaserHardwareAdapter,
    RobotHardwareAdapter,
    make_hardware_contract_factory,
)


@pytest.mark.anyio
async def test_all_hardware_adapters_generic_contract_suite():
    for kind in HardwareDeviceKind:
        factory = make_hardware_contract_factory(kind)
        report = await run_adapter_contract_suite(factory)
        assert len(report.result_codes) >= 6


@pytest.mark.anyio
async def test_robot_hardware_adapter():
    adapter = RobotHardwareAdapter("robot-001")
    await adapter.connect_hardware()
    assert adapter.state_publisher.snapshot.ready

    results = await run_robot_bench_test(adapter)
    assert all(r.passed for r in results)


@pytest.mark.anyio
async def test_gripper_hardware_adapter():
    adapter = GripperHardwareAdapter("gripper-001")
    await adapter.connect_hardware()
    assert adapter.state_publisher.snapshot.ready

    results = await run_gripper_bench_test(adapter)
    assert all(r.passed for r in results)


@pytest.mark.anyio
async def test_fixture_hardware_adapter():
    adapter = FixtureHardwareAdapter("fixture-001")
    await adapter.connect_hardware()
    assert adapter.state_publisher.snapshot.ready

    results = await run_fixture_bench_test(adapter)
    assert all(r.passed for r in results)


@pytest.mark.anyio
async def test_camera_hardware_adapter():
    adapter = CameraVisionHardwareAdapter("camera-001")
    await adapter.connect_hardware()
    assert adapter.state_publisher.snapshot.ready

    results = await run_camera_bench_test(adapter)
    assert all(r.passed for r in results)


@pytest.mark.anyio
async def test_laser_hardware_adapter_and_uncertain_outcome():
    adapter = LaserHardwareAdapter("laser-001")
    await adapter.connect_hardware()
    assert adapter.state_publisher.snapshot.ready

    results = await run_laser_bench_test(adapter)
    assert all(r.passed for r in results)

    # Reconnect and restore nominal state before second run
    await adapter.connect_hardware()
    adapter.client.set_drop_connection_during_cycle(False)

    # Stage 1: select program
    sel_payload = '{"program_id": "ALU_REFERENCE_01", "variable_data": {"engraving_text": "TEXT"}}'
    cmd_sel = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="process.action.select_program",
        input_payload_json=sel_payload,
        timeout=timedelta(seconds=5.0),
    )
    res_sel = await adapter.execute(cmd_sel)
    assert res_sel.success

    # Stage 2: execute cycle with communication drop
    adapter.client.set_drop_connection_during_cycle(True)
    cycle_payload = (
        '{"program_id": "ALU_REFERENCE_01", "variable_data": {"engraving_text": "TEXT"}, '
        '"recipe_id": "r1", "recipe_version": 1}'
    )
    cmd = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="process.action.execute_cycle",
        input_payload_json=cycle_payload,
        timeout=timedelta(seconds=5.0),
    )
    result = await adapter.execute(cmd)
    assert not result.success
    assert not result.outcome_certain
    assert result.result_code == "laser.process.outcome_unknown"


@pytest.mark.anyio
async def test_safety_hardware_adapter():
    adapter = HardwareSafetyStatusAdapter("safety-status-001")
    adapter.mark_ready()
    assert adapter.state_publisher.snapshot.ready

    results = await run_safety_bench_test(adapter)
    assert all(r.passed for r in results)


@pytest.mark.anyio
async def test_hardware_commissioning_suite():
    report = await run_hardware_commissioning_suite()
    assert report.passed
    assert len(report.results) >= 15
