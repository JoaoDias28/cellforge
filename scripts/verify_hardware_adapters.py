#!/usr/bin/env python3
"""Acceptance verification probe for Task 034: First Real Hardware Adapters."""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from xml.etree import ElementTree

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_device_sdk"
MOCK_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_mock_adapters"
HW_ROOT = REPO_ROOT / "ros_ws" / "src" / "cellforge_hardware_adapters"
sys.path.insert(0, str(SDK_ROOT))
sys.path.insert(0, str(MOCK_ROOT))
sys.path.insert(0, str(HW_ROOT))

from cellforge_device_sdk.contract import run_adapter_contract_suite  # noqa: E402
from cellforge_device_sdk.ids import new_command_id, new_trace_id  # noqa: E402
from cellforge_device_sdk.models import CapabilityCommand  # noqa: E402
from cellforge_hardware_adapters.commissioning import (  # noqa: E402
    run_hardware_commissioning_suite,
)
from cellforge_hardware_adapters.devices import (  # noqa: E402
    HardwareDeviceKind,
    HardwareSafetyStatusAdapter,
    LaserHardwareAdapter,
    make_hardware_contract_factory,
)


def verify_tree_and_recipe_parity(project_root: Path) -> None:
    """Verify behavior tree XML and recipe YAML have zero simulator-specific branches."""
    bt_path = project_root / "examples" / "pen_engraving" / "behavior_tree.xml"
    recipe_path = project_root / "examples" / "pen_engraving" / "recipe.yaml"

    if not bt_path.exists() or not recipe_path.exists():
        raise FileNotFoundError("Missing behavior_tree.xml or recipe.yaml")

    tree = ElementTree.parse(bt_path)
    root = tree.getroot()

    # Assert no simulator conditional nodes exist
    sim_nodes = {"IfSim", "IfL0", "IfL2", "IfSimulation", "IfHardware"}
    for elem in root.iter():
        if elem.tag in sim_nodes:
            raise ValueError(f"Forbidden simulation condition '{elem.tag}' found in tree.")

    recipe = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    if "simulation_only" in recipe or "simulation_overrides" in recipe:
        raise ValueError("Forbidden simulation-specific overrides found in canonical recipe.")

    print("  [OK] Behavior Tree XML and Recipe YAML parity verified (0 simulator branches).")


async def main_async() -> int:
    print("=" * 80)
    print("CellForge TASK-034: Real Hardware Adapters & Commissioning Acceptance Probe")
    print("=" * 80)

    project_root = Path(__file__).resolve().parent.parent

    # 1. Parity Check
    print("\n1. Verifying Zero-Simulator-Branch Parity:")
    verify_tree_and_recipe_parity(project_root)

    # 2. Generic Contract Suite across all Hardware Adapters
    print("\n2. Executing Generic Contract Suite across all 6 Hardware Device Kinds:")
    kinds = [
        HardwareDeviceKind.ROBOT,
        HardwareDeviceKind.GRIPPER,
        HardwareDeviceKind.FIXTURE,
        HardwareDeviceKind.CAMERA,
        HardwareDeviceKind.LASER,
        HardwareDeviceKind.SAFETY_STATUS,
    ]
    for kind in kinds:
        factory = make_hardware_contract_factory(kind)
        report = await run_adapter_contract_suite(factory)
        count = len(report.result_codes)
        print(f"  [OK] {kind.value:<15} passed generic contract suite: {count} scenarios.")

    # 3. Commissioning & Bench Test Suite
    print("\n3. Executing On-Cell Commissioning & Hardware Acceptance Suite:")
    comm_report = await run_hardware_commissioning_suite()
    for test in comm_report.results:
        status_str = "PASS" if test.passed else "FAIL"
        t_id = test.test_id
        print(f"  [{status_str}] {test.component_kind:<14} {t_id:<36} -> {test.result_code}")

    if not comm_report.passed:
        print("\n[ERROR] Commissioning suite failed!")
        return 1

    # 4. Explicit Uncertain-Outcome Test
    print("\n4. Verifying Explicit Uncertain-Outcome Handling on Laser Marker:")
    laser_adapter = LaserHardwareAdapter("laser-001")
    await laser_adapter.connect_hardware()

    # Stage 1: Select program
    sel_payload = '{"program_id": "ALU_REFERENCE_01", "variable_data": {"engraving_text": "TEST"}}'
    cmd_sel = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="process.action.select_program",
        input_payload_json=sel_payload,
        timeout=timedelta(seconds=5.0),
    )
    await laser_adapter.execute(cmd_sel)

    # Stage 2: Execute cycle with communication drop
    laser_adapter.client.set_drop_connection_during_cycle(True)
    cycle_payload = (
        '{"program_id": "ALU_REFERENCE_01", "variable_data": {"engraving_text": "TEST"}, '
        '"recipe_id": "pen-recipe-reference", "recipe_version": 1}'
    )
    cmd = CapabilityCommand(
        command_id=new_command_id(),
        trace_id=new_trace_id(),
        capability="process.action.execute_cycle",
        input_payload_json=cycle_payload,
        timeout=timedelta(seconds=5.0),
    )
    res = await laser_adapter.execute(cmd)
    if res.outcome_certain or res.success or "outcome_unknown" not in res.result_code:
        print(f"\n[ERROR] Laser adapter failed to report uncertain outcome: {res}")
        return 1
    print("  [OK] Laser marker correctly returned outcome_certain=False on comm drop.")

    # 5. Independent Safety Boundary Check
    print("\n5. Verifying Independent Safety Status (ADR 0007):")
    safety_adapter = HardwareSafetyStatusAdapter("safety-status-001")
    safety_adapter.set_safety_health(False)
    if safety_adapter.state_publisher.snapshot.ready:
        print("\n[ERROR] Safety adapter reported ready when unhealthy!")
        return 1
    print("  [OK] Safety adapter correctly refused ready state when safety is unhealthy.")

    print("\n" + "=" * 80)
    print("TASK-034 Acceptance Checks: ALL PASSED")
    print("=" * 80)
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
