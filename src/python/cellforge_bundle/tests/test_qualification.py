"""Unit and integration tests for software release qualification."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

import pytest
from cellforge_bundle.qualification import (
    QualificationCategory,
    run_software_release_qualification,
    validate_task027_l2_report,
    verify_qualification_report,
    verify_report_integrity,
    verify_tree_and_recipe_parity,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE_PROJECT = ROOT / "examples" / "pen_engraving"
SCHEMAS = ROOT / "schemas"


def test_parity_verification_succeeds_for_canonical_pen_project() -> None:
    result = verify_tree_and_recipe_parity(EXAMPLE_PROJECT)
    assert result.passed
    assert result.tree_valid
    assert result.recipe_valid
    assert not result.has_simulator_branches
    assert len(result.forbidden_branch_nodes) == 0
    assert not result.events_equivalent
    assert not result.dynamic_observed
    assert not result.l2_available


def test_parity_verification_rejects_simulator_specific_tree_branches(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(EXAMPLE_PROJECT, project)

    # Insert a simulator-specific branch in behavior_tree.xml
    tree_path = project / "behavior_tree.xml"
    tree = ElementTree.parse(tree_path)
    root = tree.getroot()
    bt = root.find(".//BehaviorTree")
    assert bt is not None
    sim_elem = ElementTree.SubElement(bt, "IfSim")
    sim_elem.attrib["condition"] = "is_sim"
    tree.write(tree_path)

    result = verify_tree_and_recipe_parity(project)
    assert not result.passed
    assert result.has_simulator_branches
    assert any("IfSim" in item for item in result.forbidden_branch_nodes)


def test_parity_verification_rejects_simulator_specific_recipe_parameters(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(EXAMPLE_PROJECT, project)

    recipe_path = project / "recipe.yaml"
    recipe_text = recipe_path.read_text(encoding="utf-8")
    recipe_text += "\n  sim_laser_override: true\n"
    recipe_path.write_text(recipe_text, encoding="utf-8")

    result = verify_tree_and_recipe_parity(project)
    assert not result.passed
    assert result.has_simulator_branches


def test_qualification_report_signing_and_verification(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    report = run_software_release_qualification(
        EXAMPLE_PROJECT,
        SCHEMAS,
        signing_key=private_key,
        key_id="test-qualification-key",
        evidence_dir=tmp_path / "evidence",
    )

    assert not report.overall_passed
    assert report.l2["status"] == "unavailable"
    assert all(s.observed and s.passed for s in report.scenarios)
    assert report.signature is not None
    assert report.key_id == "test-qualification-key"
    assert verify_report_integrity(report)
    assert verify_qualification_report(report, public_key)

    # Verify tampering causes signature failure
    tampered = replace(report, qualifier_identity="Tampered Identity")
    assert not verify_qualification_report(tampered, public_key)


def test_qualification_matrix_covers_all_nine_required_categories(tmp_path: Path) -> None:
    report = run_software_release_qualification(
        EXAMPLE_PROJECT, SCHEMAS, evidence_dir=tmp_path / "evidence"
    )

    categories_present = {s.category for s in report.scenarios}
    expected_categories = {
        QualificationCategory.NOMINAL,
        QualificationCategory.FAULT,
        QualificationCategory.CANCEL,
        QualificationCategory.TIMEOUT,
        QualificationCategory.RESTART,
        QualificationCategory.CORRUPT_BUNDLE,
        QualificationCategory.OFFLINE_PLATFORM,
        QualificationCategory.STALE_DEVICE,
        QualificationCategory.UNCERTAIN_PROCESS,
    }

    assert categories_present == expected_categories
    assert all(s.observed and s.available and s.passed for s in report.scenarios)
    assert all(s.artifact_path and s.artifact_sha256 for s in report.scenarios)
    assert report.parity.passed
    assert report.parity.dynamic_observed
    assert not report.parity.events_equivalent
    assert report.platform.passed
    assert report.l2["status"] == "unavailable"
    assert not report.overall_passed
    assert verify_report_integrity(report)

    # Verify disclaimers and limitations
    assert "functional_safety" in report.limitations
    assert "laser_process_simulation" in report.limitations
    assert "hardware_qualification" in report.limitations
    assert "Task 034" in report.limitations["hardware_qualification"]


def _task027_shape_fixture(scene_path: Path) -> dict[str, object]:
    """Create a format-only fixture; no test-shaped report is release evidence."""

    runs: list[dict[str, object]] = []
    for seed in range(100):
        runs.append(
            {
                "scenario_id": f"pen-l2-seed-{seed:04d}",
                "seed": seed,
                "backend": "Isaac Sim 6 OpenUSD/PhysX",
                "achieved_fidelity": "L2",
                "actual_physx_executed": True,
                "event_origin": "runtime/adapters",
                "events": [
                    {
                        "origin": "isaac_l2_adapter",
                        "event_type": "cycle.completed",
                        "result_code": "process.command.completed",
                    }
                ],
            }
        )
    faults = [
        "simulation.pen.dropped",
        "fixture.sensor.seating_failed",
        "motion.plan.collision",
    ]
    fault_scenarios = [
        {
            "scenario_id": f"fault-{index}",
            "result_code": code,
            "backend": "Isaac Sim 6 OpenUSD/PhysX",
            "achieved_fidelity": "L2",
            "actual_physx_executed": True,
            "event_origin": "runtime/adapters",
            "events": [{"origin": "isaac_l2_adapter", "result_code": code}],
        }
        for index, code in enumerate(faults)
    ]
    return {
        "schema_version": "0.1.0",
        "kind": "cellforge.isaac_l2_seed_report",
        "isaac_version": "6.0.0-test",
        "gpu": {"name": "NVIDIA test GPU", "is_cuda": True},
        "scene": str(scene_path),
        "scene_sha256": hashlib.sha256(scene_path.read_bytes()).hexdigest(),
        "summary": {"passed": 100, "failed": 0},
        "seed_range": {"first": 0, "count": 100},
        "actual_physx_executed": True,
        "event_origin": "runtime/adapters",
        "runs": runs,
        "fault_scenarios": fault_scenarios,
        "replay_sha256": hashlib.sha256(
            json.dumps(runs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_l2_report_validator_accepts_complete_task027_shape(tmp_path: Path) -> None:
    scene = EXAMPLE_PROJECT / "scene.usda"
    report_path = tmp_path / "task027.json"
    _write_json(report_path, _task027_shape_fixture(scene))

    result = validate_task027_l2_report(report_path, EXAMPLE_PROJECT)

    assert result["status"] == "passed"
    assert result["passed"] is True
    assert result["seed_count"] == 100
    assert set(result["fault_codes"]) == {
        "simulation.pen.dropped",
        "fixture.sensor.seating_failed",
        "motion.plan.collision",
    }


def test_l2_report_validator_rejects_cpu_relabeling_and_tampering(tmp_path: Path) -> None:
    scene = EXAMPLE_PROJECT / "scene.usda"
    cpu_report = _task027_shape_fixture(scene)
    cpu_report["gpu"] = {"name": "CPU model", "is_cuda": False}
    cpu_path = tmp_path / "cpu.json"
    _write_json(cpu_path, cpu_report)
    cpu_result = validate_task027_l2_report(cpu_path, EXAMPLE_PROJECT)
    assert cpu_result["status"] == "failed"
    assert cpu_result["passed"] is False
    assert any("CUDA GPU" in reason for reason in cpu_result["failure_reasons"])

    tampered_report = _task027_shape_fixture(scene)
    runs = tampered_report["runs"]
    assert isinstance(runs, list)
    first_run = runs[0]
    assert isinstance(first_run, dict)
    events = first_run["events"]
    assert isinstance(events, list)
    events[0]["result_code"] = "cpu.mock.success"
    tampered_path = tmp_path / "tampered.json"
    _write_json(tampered_path, tampered_report)
    tampered_result = validate_task027_l2_report(tampered_path, EXAMPLE_PROJECT)
    assert tampered_result["status"] == "failed"
    assert tampered_result["passed"] is False
    assert any("replay_sha256" in reason for reason in tampered_result["failure_reasons"])


def test_l2_report_validator_marks_missing_evidence_unavailable() -> None:
    result = validate_task027_l2_report(None, EXAMPLE_PROJECT)

    assert result["status"] == "unavailable"
    assert result["available"] is False
    assert result["passed"] is False


def test_genuine_task027_report_when_supplied() -> None:
    report_value = os.environ.get("CELLFORGE_TASK027_REPORT")
    if not report_value:
        pytest.skip("set CELLFORGE_TASK027_REPORT to run the external Isaac Sim evidence case")
    report_path = Path(report_value)
    if not report_path.is_file():
        pytest.skip(f"external Task 027 report is unavailable: {report_path}")

    result = validate_task027_l2_report(report_path, EXAMPLE_PROJECT)

    assert result["status"] == "passed"
    assert result["actual_physx_executed"] is True
    assert result["gpu"]["is_cuda"] is True
    assert result["seed_count"] == 100
