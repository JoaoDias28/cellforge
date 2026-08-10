"""Deterministic tests for the Task 009 L0 contract mock adapters."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_device_sdk"
MOCK_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_mock_adapters"
sys.path.insert(0, str(SDK_ROOT))
sys.path.insert(0, str(MOCK_ROOT))

from cellforge_device_sdk.contract import ContractScenario, run_adapter_contract_suite  # noqa: E402
from cellforge_device_sdk.ids import new_command_id, new_trace_id  # noqa: E402
from cellforge_device_sdk.models import (  # noqa: E402
    CapabilityCommand,
    DeviceState,
    DeviceStateSnapshot,
)
from cellforge_mock_adapters import (  # noqa: E402
    TEST_HOOK_FAULT,
    DeviceKind,
    DeviceScenario,
    ScenarioConfigError,
    build_device_mock,
    make_contract_factory,
    parse_device_scenario,
    parse_scenario_document,
)
from cellforge_mock_adapters.scenarios import ProcessData  # noqa: E402

LAUNCH_FILE = MOCK_ROOT / "launch" / "mock_cell.launch.py"
CONFIG_FILE = MOCK_ROOT / "config" / "mock_cell_scenarios.json"
CELL_YAML = REPO_ROOT / "examples" / "pen_engraving" / "cell.yaml"
RECIPE_YAML = REPO_ROOT / "examples" / "pen_engraving" / "recipe.yaml"

EXPECTED_CONTRACT_CODES = {
    ContractScenario.NOMINAL: "sdk.test.execute.completed",
    ContractScenario.INVALID_INPUT: "sdk.command.invalid_input",
    ContractScenario.NOT_READY: "sdk.command.not_ready",
    ContractScenario.CANCELLATION: "sdk.command.cancelled",
    ContractScenario.TIMEOUT: "sdk.command.timeout",
    ContractScenario.FAULT: TEST_HOOK_FAULT,
}

DEFAULT_INSTANCES = {
    "robot": "robot-001",
    "gripper": "gripper-001",
    "fixture": "fixture-001",
    "vision_locator": "camera-001",
    "process_machine": "laser-001",
    "inspection": "camera-001",
}

ROBOT_PAYLOAD = {"trajectory": {"waypoints": [{"joints": [0.0, 0.1]}, {"joints": [0.2, 0.3]}]}}
LOCATE_PAYLOAD = {"object_type": "pen", "profile_id": "pen_reference"}
INSPECT_PAYLOAD = {"inspection_profile": "contrast_and_text_match", "expected": {"text": "OK"}}
SELECT_PAYLOAD = {"program_id": "ALU_REFERENCE_01"}
CYCLE_PAYLOAD = {
    "program_id": "ALU_REFERENCE_01",
    "variable_data": {"text": "CELLFORGE"},
    "recipe_id": "pen-aluminium-reference",
    "recipe_version": 1,
}


def make_scenario(
    kind: str,
    operations: dict[str, Any],
    device: dict[str, Any] | None = None,
    *,
    restart: str = "ready",
    instance_id: str | None = None,
) -> DeviceScenario:
    document: dict[str, Any] = {
        "component_instance_id": instance_id or DEFAULT_INSTANCES[kind],
        "device_kind": kind,
        "restart": restart,
        "operations": operations,
    }
    if device is not None:
        document["device"] = device
    return parse_device_scenario(document)


def make_command(
    capability: str,
    payload: dict[str, Any],
    timeout: timedelta = timedelta(seconds=1),
) -> CapabilityCommand:
    return CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability=capability,
        input_payload_json=json.dumps(payload),
        timeout=timeout,
    )


def test_all_six_mock_devices_pass_generic_contract_suite() -> None:
    """Every mock satisfies the mandatory generic adapter contract scenarios."""

    for kind in DeviceKind:
        report = asyncio.run(run_adapter_contract_suite(make_contract_factory(kind)))
        assert report.result_codes == EXPECTED_CONTRACT_CODES, kind.value


def test_invalid_scenario_configurations_are_rejected() -> None:
    """Malformed scenario documents fail validation with structured errors."""

    with pytest.raises(ScenarioConfigError, match="not valid JSON"):
        parse_scenario_document("{")
    with pytest.raises(ScenarioConfigError, match="missing required"):
        parse_scenario_document(json.dumps({"schema_version": "0.1.0"}))
    with pytest.raises(ScenarioConfigError, match="unknown configuration keys"):
        parse_scenario_document(
            json.dumps({"schema_version": "0.1.0", "nodes": {"n": {}}, "extra": 1})
        )
    with pytest.raises(ScenarioConfigError, match="schema_version"):
        parse_scenario_document(json.dumps({"schema_version": "9.9.9", "nodes": {"n": {}}}))
    with pytest.raises(ScenarioConfigError, match="at least one node"):
        parse_scenario_document(json.dumps({"schema_version": "0.1.0", "nodes": {}}))
    with pytest.raises(ScenarioConfigError, match="node name"):
        parse_scenario_document(json.dumps({"schema_version": "0.1.0", "nodes": {"Bad-Name": {}}}))
        with pytest.raises(ScenarioConfigError, match="device_kind"):
            parse_device_scenario(
                {
                    "component_instance_id": "test-001",
                    "device_kind": "hovercraft",
                    "operations": {},
                }
            )
    with pytest.raises(ScenarioConfigError, match="component_instance_id"):
        make_scenario("gripper", {}, instance_id="Gripper 001")
    with pytest.raises(ScenarioConfigError, match="restart"):
        make_scenario("gripper", {}, restart="maybe")
    with pytest.raises(ScenarioConfigError, match="not declared"):
        make_scenario("gripper", {"gripper.hover": {"duration_seconds": 0.1}})
    with pytest.raises(ScenarioConfigError, match="missing required"):
        make_scenario("gripper", {"gripper.action.open": {}})
    with pytest.raises(ScenarioConfigError, match="duration_seconds"):
        make_scenario("gripper", {"gripper.action.open": {"duration_seconds": 0}})
    with pytest.raises(ScenarioConfigError, match="duration_seconds"):
        make_scenario("gripper", {"gripper.action.open": {"duration_seconds": True}})
    with pytest.raises(ScenarioConfigError, match="unknown configuration keys"):
        make_scenario(
            "gripper", {"gripper.action.open": {"duration_seconds": 0.1}}, {"jaw": "open"}
        )
    with pytest.raises(ScenarioConfigError, match="jaw_initial"):
        make_scenario("gripper", {}, {"jaw_initial": "ajar"})
    with pytest.raises(ScenarioConfigError, match="confidence"):
        make_scenario("vision_locator", {}, {"confidence": 1.5})
    with pytest.raises(ScenarioConfigError, match="known_programs"):
        make_scenario("process_machine", {}, {"known_programs": [42]})
    with pytest.raises(ScenarioConfigError, match="measurements"):
        make_scenario("inspection", {}, {"measurements": "high"})


def test_unsupported_fault_scenarios_are_rejected() -> None:
    """Fault injection accepts only the device catalog plus the documented SDK test hook."""

    with pytest.raises(ScenarioConfigError, match="not in the 'gripper' catalog"):
        make_scenario(
            "gripper",
            {"gripper.action.close": {"duration_seconds": 0.1, "fault": "laser.program.not_found"}},
        )
    with pytest.raises(ScenarioConfigError, match="not in the 'robot' catalog"):
        make_scenario(
            "robot",
            {
                "robot_motion.action.execute_trajectory": {
                    "duration_seconds": 0.1,
                    "fault": "totally.made.up",
                }
            },
        )
    hook = make_scenario(
        "robot",
        {
            "robot_motion.action.execute_trajectory": {
                "duration_seconds": 0.1,
                "fault": TEST_HOOK_FAULT,
            }
        },
    )
    assert hook.operations["robot_motion.action.execute_trajectory"].fault == TEST_HOOK_FAULT
    uncertain = make_scenario(
        "process_machine",
        {
            "process.action.execute_cycle": {
                "duration_seconds": 0.1,
                "fault": "laser.process.outcome_unknown",
            }
        },
        {"known_programs": ["ALU_REFERENCE_01"]},
    )
    assert (
        uncertain.operations["process.action.execute_cycle"].fault
        == "laser.process.outcome_unknown"
    )


def _states(emitted: list[DeviceStateSnapshot]) -> list[DeviceState]:
    return [snapshot.state for snapshot in emitted]


def test_configured_device_faults_produce_catalog_codes_and_fault_state() -> None:
    """Scenario-selected faults surface as deterministic catalog codes with FAULT state."""

    async def run() -> None:
        laser_fault = make_scenario(
            "process_machine",
            {
                "process.action.select_program": {"duration_seconds": 0.005},
                "process.action.execute_cycle": {
                    "duration_seconds": 0.005,
                    "fault": "laser.process.timeout",
                },
            },
            {"known_programs": ["ALU_REFERENCE_01"]},
        )
        laser = build_device_mock(laser_fault)
        laser.mark_ready()
        selected = await laser.execute(
            make_command("process.action.select_program", SELECT_PAYLOAD)
        )
        assert selected.success
        cycle = await laser.execute(make_command("process.action.execute_cycle", CYCLE_PAYLOAD))
        assert not cycle.success
        assert cycle.result_code == "laser.process.timeout"
        assert cycle.fault is not None and cycle.fault.code == "laser.process.timeout"
        assert laser.state_publisher.snapshot.state is DeviceState.FAULT

        robot_fault = make_scenario(
            "robot",
            {
                "robot_motion.action.execute_trajectory": {
                    "duration_seconds": 0.005,
                    "fault": "robot.motion.protective_stop",
                }
            },
        )
        robot = build_device_mock(robot_fault)
        robot.mark_ready()
        moved = await robot.execute(
            make_command("robot_motion.action.execute_trajectory", ROBOT_PAYLOAD)
        )
        assert moved.result_code == "robot.motion.protective_stop"
        assert robot.state_publisher.snapshot.state is DeviceState.FAULT

        gripper_fault = make_scenario(
            "gripper",
            {
                "gripper.action.close": {
                    "duration_seconds": 0.005,
                    "fault": "gripper.motion.close_failed",
                }
            },
        )
        gripper = build_device_mock(gripper_fault)
        gripper.mark_ready()
        closed = await gripper.execute(make_command("gripper.action.close", {}))
        assert closed.result_code == "gripper.motion.close_failed"

        vision_absent = make_scenario(
            "vision_locator",
            {"vision.action.locate_object": {"duration_seconds": 0.005}},
            {"object_present": False},
        )
        locator = build_device_mock(vision_absent)
        locator.mark_ready()
        located = await locator.execute(make_command("vision.action.locate_object", LOCATE_PAYLOAD))
        assert located.result_code == "vision.object.not_found"

        not_seated = make_scenario(
            "fixture",
            {"fixture.action.verify_seated": {"duration_seconds": 0.005}},
            {"seated": False},
        )
        fixture = build_device_mock(not_seated)
        fixture.mark_ready()
        verified = await fixture.execute(make_command("fixture.action.verify_seated", {}))
        assert verified.result_code == "fixture.sensor.seating_failed"

        inspection_fault = make_scenario(
            "inspection",
            {
                "vision.action.inspect_object": {
                    "duration_seconds": 0.005,
                    "fault": "vision.inspection.measurement_invalid",
                }
            },
        )
        inspector = build_device_mock(inspection_fault)
        inspector.mark_ready()
        inspected = await inspector.execute(
            make_command("vision.action.inspect_object", INSPECT_PAYLOAD)
        )
        assert inspected.result_code == "vision.inspection.measurement_invalid"

    asyncio.run(run())


def test_bridge_selected_fault_is_applied_once_to_next_mock_operation() -> None:
    async def run() -> None:
        scenario = make_scenario(
            "gripper",
            {"gripper.action.close": {"duration_seconds": 0.001}},
        )
        adapter = build_device_mock(scenario)
        adapter.mark_ready()
        adapter.inject_next_fault("gripper.motion.close_failed")
        failed = await adapter.execute(make_command("gripper.action.close", {}))
        assert failed.result_code == "gripper.motion.close_failed"
        adapter.mark_ready()
        succeeded = await adapter.execute(make_command("gripper.action.close", {}))
        assert succeeded.success
        with pytest.raises(ValueError, match="not supported"):
            adapter.inject_next_fault("unsupported.fault")

    asyncio.run(run())


def test_operation_timeout_is_uncertain_and_blocks_new_work() -> None:
    """A command deadline produces an uncertain timeout and a non-ready UNKNOWN state."""

    async def run() -> None:
        scenario = make_scenario(
            "gripper",
            {
                "gripper.action.close": {"duration_seconds": 5.0},
                "gripper.action.open": {"duration_seconds": 0.005},
            },
        )
        adapter = build_device_mock(scenario)
        adapter.mark_ready()
        result = await adapter.execute(
            make_command("gripper.action.close", {}, timeout=timedelta(milliseconds=20))
        )
        assert result.result_code == "sdk.command.timeout"
        assert not result.outcome_certain
        snapshot = adapter.state_publisher.snapshot
        assert snapshot.state is DeviceState.UNKNOWN
        assert not snapshot.ready
        follow_up = await adapter.execute(make_command("gripper.action.open", {}))
        assert follow_up.result_code == "sdk.command.not_ready"

    asyncio.run(run())


def test_cancellation_is_certain_and_returns_to_ready() -> None:
    """Cancellation stops the virtual timer provably and publishes READY afterwards."""

    async def run() -> None:
        emitted: list[DeviceStateSnapshot] = []
        scenario = make_scenario("gripper", {"gripper.action.close": {"duration_seconds": 5.0}})
        adapter = build_device_mock(scenario, state_sink=emitted.append)
        adapter.mark_ready()
        command = make_command("gripper.action.close", {})
        task = asyncio.create_task(adapter.execute(command))
        await asyncio.wait_for(adapter.operation_started.wait(), timeout=0.5)
        assert adapter.cancel(command.command_id)
        result = await task
        assert result.result_code == "sdk.command.cancelled"
        assert result.outcome_certain
        assert adapter.state_publisher.snapshot.state is DeviceState.READY
        assert not adapter.cancel(command.command_id)
        assert _states(emitted) == [DeviceState.READY, DeviceState.BUSY, DeviceState.READY]
        assert emitted[1].active_command_id == command.command_id

    asyncio.run(run())


def test_state_transition_ordering_is_coherent_before_completion() -> None:
    """Nominal and fault completions publish monotonic BUSY-first transition sequences."""

    async def run() -> None:
        nominal_events: list[DeviceStateSnapshot] = []
        nominal = build_device_mock(
            make_scenario("gripper", {"gripper.action.open": {"duration_seconds": 0.005}}),
            state_sink=nominal_events.append,
        )
        nominal.mark_ready()
        command = make_command("gripper.action.open", {})
        result = await nominal.execute(command)
        assert result.success
        assert _states(nominal_events) == [
            DeviceState.READY,
            DeviceState.BUSY,
            DeviceState.READY,
        ]
        assert [snapshot.revision for snapshot in nominal_events] == [1, 2, 3]
        assert nominal_events[1].busy
        assert nominal_events[1].active_command_id == command.command_id
        assert nominal_events[2].active_command_id is None

        fault_events: list[DeviceStateSnapshot] = []
        faulty = build_device_mock(
            make_scenario(
                "robot",
                {
                    "robot_motion.action.execute_trajectory": {
                        "duration_seconds": 0.005,
                        "fault": "robot.motion.planning_failed",
                    }
                },
            ),
            state_sink=fault_events.append,
        )
        faulty.mark_ready()
        failed = await faulty.execute(
            make_command("robot_motion.action.execute_trajectory", ROBOT_PAYLOAD)
        )
        assert not failed.success
        assert _states(fault_events) == [DeviceState.READY, DeviceState.BUSY, DeviceState.FAULT]
        assert fault_events[2].fault is not None
        assert fault_events[2].fault.code == "robot.motion.planning_failed"

    asyncio.run(run())


def test_repeated_execution_is_deterministic() -> None:
    """Identical scenario plus identical command yields identical outcomes across repetitions."""

    async def run() -> list[tuple[str, str, str]]:
        scenario = make_scenario(
            "vision_locator",
            {"vision.action.locate_object": {"duration_seconds": 0.005}},
            {
                "object_id": "pen-001",
                "confidence": 0.95,
                "pose": {"x": 0.4, "y": -0.02, "z": 0.15},
            },
        )
        adapter = build_device_mock(scenario)
        adapter.mark_ready()
        outcomes: list[tuple[str, str, str]] = []
        for _ in range(3):
            result = await adapter.execute(
                make_command("vision.action.locate_object", LOCATE_PAYLOAD)
            )
            outcomes.append((result.result_code, result.result_message, result.output_payload_json))
        return outcomes

    first_run = asyncio.run(run())
    second_run = asyncio.run(run())
    assert len(set(first_run)) == 1
    assert first_run == second_run


def test_success_results_carry_deterministic_non_empty_outputs() -> None:
    """No mock reports success through an empty placeholder payload."""

    async def run() -> None:
        robot = build_device_mock(
            make_scenario(
                "robot", {"robot_motion.action.execute_trajectory": {"duration_seconds": 0.005}}
            )
        )
        robot.mark_ready()
        moved = await robot.execute(
            make_command("robot_motion.action.execute_trajectory", ROBOT_PAYLOAD)
        )
        assert moved.success
        robot_output = json.loads(moved.output_payload_json)
        assert robot_output["executed_waypoints"] == 2
        assert robot_output["final_waypoint"] == {"joints": [0.2, 0.3]}

        gripper = build_device_mock(
            make_scenario(
                "gripper",
                {
                    "gripper.action.close": {"duration_seconds": 0.005},
                    "gripper.action.open": {"duration_seconds": 0.005},
                },
            )
        )
        gripper.mark_ready()
        closed = await gripper.execute(make_command("gripper.action.close", {}))
        assert json.loads(closed.output_payload_json)["jaw_state"] == "closed"
        # Verify that the close took effect by checking the output of a subsequent open
        gripper.mark_ready()
        reopened = await gripper.execute(make_command("gripper.action.open", {}))
        assert json.loads(reopened.output_payload_json)["jaw_state"] == "open"

        fixture = build_device_mock(
            make_scenario(
                "fixture",
                {
                    "fixture.action.clamp": {"duration_seconds": 0.005},
                    "fixture.action.verify_seated": {"duration_seconds": 0.005},
                },
            )
        )
        fixture.mark_ready()
        clamped = await fixture.execute(make_command("fixture.action.clamp", {}))
        assert json.loads(clamped.output_payload_json)["clamped"] is True
        seated = await fixture.execute(make_command("fixture.action.verify_seated", {}))
        assert json.loads(seated.output_payload_json)["seated"] is True

        locator = build_device_mock(
            make_scenario(
                "vision_locator", {"vision.action.locate_object": {"duration_seconds": 0.005}}
            )
        )
        locator.mark_ready()
        located = await locator.execute(make_command("vision.action.locate_object", LOCATE_PAYLOAD))
        estimate = json.loads(located.output_payload_json)["estimates"][0]
        assert estimate["object_id"] == "pen-001"
        assert estimate["source_frame"] == "camera-001/optical"

        inspector = build_device_mock(
            make_scenario(
                "inspection",
                {"vision.action.inspect_object": {"duration_seconds": 0.005}},
                {"accepted": False, "measurements": {"contrast": 0.4, "text_match": False}},
            )
        )
        inspector.mark_ready()
        inspected = await inspector.execute(
            make_command("vision.action.inspect_object", INSPECT_PAYLOAD)
        )
        inspection_output = json.loads(inspected.output_payload_json)
        assert inspected.success
        assert inspection_output["accepted"] is False
        assert inspection_output["measurements"]["contrast"] == 0.4

    asyncio.run(run())


def test_process_machine_two_stage_interlock_and_uncertainty_contract() -> None:
    """The process mock enforces prepare-then-execute, interlock status, and uncertainty."""

    async def run() -> None:
        machine = build_device_mock(
            make_scenario(
                "process_machine",
                {
                    "process.action.select_program": {"duration_seconds": 0.005},
                    "process.action.execute_cycle": {"duration_seconds": 0.005},
                },
                {"known_programs": ["ALU_REFERENCE_01"]},
            )
        )
        machine.mark_ready()
        premature = await machine.execute(
            make_command("process.action.execute_cycle", CYCLE_PAYLOAD)
        )
        assert premature.result_code == "sdk.command.invalid_input"
        assert machine.state_publisher.snapshot.state is DeviceState.READY

        unknown = await machine.execute(
            make_command("process.action.select_program", {"program_id": "DOES_NOT_EXIST"})
        )
        assert unknown.result_code == "laser.program.not_found"
        machine.mark_ready()

        selected = await machine.execute(
            make_command("process.action.select_program", SELECT_PAYLOAD)
        )
        assert selected.success
        mismatch = await machine.execute(
            make_command("process.action.execute_cycle", {"program_id": "OTHER_PROGRAM"})
        )
        assert mismatch.result_code == "sdk.command.invalid_input"
        completed = await machine.execute(
            make_command("process.action.execute_cycle", CYCLE_PAYLOAD)
        )
        assert completed.success
        cycle_output = json.loads(completed.output_payload_json)
        assert cycle_output["cycle"] == "completed"
        assert cycle_output["verification_passed"] is True
        assert cycle_output["process_data"]["variable_data"] == {"text": "CELLFORGE"}

        interlocked = build_device_mock(
            make_scenario(
                "process_machine",
                {
                    "process.action.select_program": {"duration_seconds": 0.005},
                    "process.action.execute_cycle": {"duration_seconds": 0.005},
                },
                {"known_programs": ["ALU_REFERENCE_01"], "interlock_permitted": False},
            )
        )
        interlocked.mark_ready()
        await interlocked.execute(make_command("process.action.select_program", SELECT_PAYLOAD))
        blocked = await interlocked.execute(
            make_command("process.action.execute_cycle", CYCLE_PAYLOAD)
        )
        assert blocked.result_code == "laser.process.interlock_not_ready"
        assert interlocked.state_publisher.snapshot.state is DeviceState.FAULT

        uncertain = build_device_mock(
            make_scenario(
                "process_machine",
                {
                    "process.action.select_program": {"duration_seconds": 0.005},
                    "process.action.execute_cycle": {
                        "duration_seconds": 0.005,
                        "fault": "laser.process.outcome_unknown",
                    },
                },
                {"known_programs": ["ALU_REFERENCE_01"]},
            )
        )
        uncertain.mark_ready()
        await uncertain.execute(make_command("process.action.select_program", SELECT_PAYLOAD))
        unknown_outcome = await uncertain.execute(
            make_command("process.action.execute_cycle", CYCLE_PAYLOAD)
        )
        assert not unknown_outcome.success
        assert unknown_outcome.result_code == "laser.process.outcome_unknown"
        assert not unknown_outcome.outcome_certain
        assert uncertain.state_publisher.snapshot.state is DeviceState.UNKNOWN

    asyncio.run(run())


def test_mock_cell_launch_and_configuration_validation() -> None:
    """The complete mock-cell launch file and scenario config match the reference cell."""

    assert LAUNCH_FILE.is_file()
    launch_text = LAUNCH_FILE.read_text(encoding="utf-8")
    assert "mock_device_node" in launch_text
    assert "mock_cell_scenarios.json" in launch_text

    scenarios = parse_scenario_document(CONFIG_FILE.read_text(encoding="utf-8"))
    expected_nodes = {
        "mock_robot": ("robot", "robot-001"),
        "mock_gripper": ("gripper", "gripper-001"),
        "mock_fixture": ("fixture", "fixture-001"),
        "mock_vision_locator": ("vision_locator", "camera-001"),
        "mock_inspection": ("inspection", "camera-001"),
        "mock_laser": ("process_machine", "laser-001"),
    }
    assert set(scenarios) == set(expected_nodes)
    for node_name, (kind, instance_id) in expected_nodes.items():
        assert node_name in launch_text
        scenario = scenarios[node_name]
        assert scenario.device_kind == kind
        assert scenario.component_instance_id == instance_id
        assert scenario.operations, node_name
        for behavior in scenario.operations.values():
            assert behavior.duration_seconds > 0
            assert behavior.fault is None, "the shipped nominal mock cell injects no faults"

    cell = yaml.safe_load(CELL_YAML.read_text(encoding="utf-8"))
    cell_instance_ids = {component["id"] for component in cell["components"]}
    configured_ids = {scenario.component_instance_id for scenario in scenarios.values()}
    assert configured_ids <= cell_instance_ids

    required: set[str] = set()
    for task in cell["tasks"]:
        required.update(task["required_capabilities"])
    provided: set[str] = set()
    for scenario in scenarios.values():
        provided.update(
            capability for capability in scenario.operations if not capability.startswith("sdk.")
        )
    canonical_required: set[str] = set()
    for cap in required:
        parts = cap.split(".")
        canonical_required.add(f"{parts[0]}.action.{parts[1]}")
    assert canonical_required <= provided

    recipe = yaml.safe_load(RECIPE_YAML.read_text(encoding="utf-8"))
    laser_program = recipe["parameters"]["laser_program"]
    laser = scenarios["mock_laser"]
    process_device = laser.device
    assert isinstance(process_device, ProcessData)
    assert laser_program in process_device.known_programs
