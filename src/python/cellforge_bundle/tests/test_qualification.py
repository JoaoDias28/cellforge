"""Unit and integration tests for software release qualification."""

from __future__ import annotations

import shutil
from pathlib import Path
from xml.etree import ElementTree

from cellforge_bundle.qualification import (
    QualificationCategory,
    SoftwareReleaseQualificationReport,
    run_software_release_qualification,
    verify_qualification_report,
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
    assert result.events_equivalent


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


def test_qualification_report_signing_and_verification() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    report = run_software_release_qualification(
        EXAMPLE_PROJECT,
        SCHEMAS,
        signing_key=private_key,
        key_id="test-qualification-key",
    )

    assert report.overall_passed
    assert report.signature is not None
    assert report.key_id == "test-qualification-key"
    assert verify_qualification_report(report, public_key)

    # Verify tampering causes signature failure
    tampered = SoftwareReleaseQualificationReport(
        report_id=report.report_id,
        timestamp=report.timestamp,
        suite_version=report.suite_version,
        qualifier_identity="Tampered Identity",
        git_revision=report.git_revision,
        git_tree_sha=report.git_tree_sha,
        git_clean=report.git_clean,
        cell_id=report.cell_id,
        cell_name=report.cell_name,
        cell_yaml_sha256=report.cell_yaml_sha256,
        scene_sha256=report.scene_sha256,
        components=report.components,
        recipe=report.recipe,
        bundles=report.bundles,
        scenarios=report.scenarios,
        parity=report.parity,
        platform=report.platform,
        limitations=report.limitations,
        overall_passed=report.overall_passed,
        schema_version=report.schema_version,
        signature=report.signature,
        key_id=report.key_id,
    )
    assert not verify_qualification_report(tampered, public_key)


def test_qualification_matrix_covers_all_nine_required_categories() -> None:
    report = run_software_release_qualification(EXAMPLE_PROJECT, SCHEMAS)

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
    assert all(s.passed for s in report.scenarios)
    assert report.parity.passed
    assert report.platform.passed
    assert report.overall_passed

    # Verify disclaimers and limitations
    assert "functional_safety" in report.limitations
    assert "laser_process_simulation" in report.limitations
    assert "hardware_qualification" in report.limitations
    assert "Task 034" in report.limitations["hardware_qualification"]
