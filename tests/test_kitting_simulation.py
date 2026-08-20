from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "ros_ws" / "src" / "cellforge_device_sdk",
    ROOT / "ros_ws" / "src" / "cellforge_mock_adapters",
    ROOT / "ros_ws" / "src" / "cellforge_simulation",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from cellforge_mock_adapters.headless import ScenarioError, load_scenario  # noqa: E402
from cellforge_mock_adapters.kitting import (  # noqa: E402
    KITTING_CELL_ID,
    KittingHeadlessExecutor,
    load_kitting_project,
)

PROJECT = ROOT / "examples" / "kitting"
NOMINAL = PROJECT / "scenarios" / "nominal.yaml"
RECOVERY = PROJECT / "scenarios" / "gripper_close_recovery.yaml"
TREE = PROJECT / "behavior_tree.xml"


def _load_demo_module() -> Any:
    path = ROOT / "scripts" / "run_simulation_demo.py"
    spec = importlib.util.spec_from_file_location("cellforge_kitting_demo", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


demo = _load_demo_module()
ARTIFACT_NAMES = ("report.json", "trace.json", "events.json", "junit.xml", "run.log", "replay.txt")


def test_kitting_project_binds_identity_frames_ports_and_contract_documents() -> None:
    project = load_kitting_project(PROJECT)

    assert project.cell_id == KITTING_CELL_ID
    assert set(project.components) == {
        "robot-001",
        "gripper-001",
        "camera-001",
        "kit-fixture-001",
        "source-carrier-001",
        "safety-status-001",
    }
    assert project.resolve_port("robot-001", "trajectory") == (
        "robot_motion.execute_trajectory",
        "execute_trajectory",
    )
    assert project.resolve_port("gripper-001", "close")[0] == "gripper.close"
    assert project.resolve_port("camera-001", "inspect")[0] == "vision.inspect_object"
    assert project.has_frame("source_slot_1")
    assert project.has_frame("slot_2")
    assert len(project.capability_documents) == 8
    assert len(project.fault_catalogs) == 1


def test_kitting_nominal_and_fault_recovery_use_shared_l0_adapters() -> None:
    nominal = load_scenario(NOMINAL)
    nominal_executor = KittingHeadlessExecutor(nominal, TREE, PROJECT)
    nominal_result = asyncio.run(nominal_executor.execute())
    assert nominal_result.passed is True
    assert nominal_result.final_status == "SUCCESS"
    assert any(event.event_type == "part.placed" for event in nominal_result.trace)
    assert all(event.component_instance_id != "safety-status-001" for event in nominal_result.trace)

    recovery = load_scenario(RECOVERY)
    recovery_executor = KittingHeadlessExecutor(recovery, TREE, PROJECT)
    recovery_result = asyncio.run(recovery_executor.execute())
    events = [event.event_type for event in recovery_result.trace]
    assert recovery_result.passed is True
    assert recovery_result.final_status == "SUCCESS"
    assert events.index("gripper.motion.close_failed") < events.index("fault.recovered")
    assert "recovery.adapter_ready" in events


def test_kitting_invalid_payload_is_rejected_before_execution() -> None:
    scenario = load_scenario(NOMINAL)
    invalid_job = dict(scenario.job)
    invalid_job["input_payload"] = {
        "kit_sku": "KIT-2PART-REF",
        "parts": [{"sku": "PART-A", "slot": "slot_1"}],
    }
    invalid = replace(scenario, job=invalid_job)

    with pytest.raises(ScenarioError, match="exactly two parts"):
        KittingHeadlessExecutor(invalid, TREE, PROJECT)


def test_kitting_demo_same_seed_reproduces_all_normalized_artifacts(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    arguments = [
        "--backend",
        "l0",
        "--workflow",
        "kitting",
        "--scenario",
        "nominal",
        "--seed",
        "3801",
    ]
    assert demo.main([*arguments, "--output-dir", str(first)]) == 0
    assert demo.main([*arguments, "--output-dir", str(second)]) == 0
    assert {name: (first / name).read_bytes() for name in ARTIFACT_NAMES} == {
        name: (second / name).read_bytes() for name in ARTIFACT_NAMES
    }
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    assert report["project"]["component_manifests"]
    assert report["project"]["capability_contracts"]
    assert report["project"]["fault_catalogs"]
    assert report["fidelity"] == {
        "requested": "L0",
        "achieved": "L0",
        "actual_physx_executed": False,
    }
    assert all(item["fidelity"] == "L0" for item in report["selected_adapters"])
    assert report["execution"]["physical_operation_authorized"] is False


def test_kitting_failed_assertion_is_non_zero_and_recorded(tmp_path: Path) -> None:
    output = tmp_path / "failed"
    assert (
        demo.main(
            [
                "--backend",
                "l0",
                "--workflow",
                "kitting",
                "--scenario",
                "nominal",
                "--output-dir",
                str(output),
                "--assertion",
                "require-event:missing.kitting.event",
            ]
        )
        == 1
    )
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["result"]["passed"] is False


def test_kitting_l2_request_is_unavailable_and_never_relabelled(tmp_path: Path) -> None:
    output = tmp_path / "l2-unavailable"
    assert (
        demo.main(
            [
                "--backend",
                "l2",
                "--workflow",
                "kitting",
                "--scenario",
                "nominal",
                "--output-dir",
                str(output),
            ]
        )
        == 1
    )
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "unavailable"
    assert report["result"]["final_status"] == "UNAVAILABLE"
    assert report["fidelity"]["achieved"] is None
    assert report["fidelity"]["actual_physx_executed"] is False
    assert "no robot/tray/product PhysX adapter" in report["limitations"]["physics_evidence"]
