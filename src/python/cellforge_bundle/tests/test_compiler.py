from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from cellforge_bundle import CompilationReport, ManifestWriteError, compile_project, write_manifest
from cellforge_domain import ExecutionMode

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "pen_engraving"
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas"
SOURCE_REVISION = "a" * 40


def _project_copy(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(EXAMPLE_ROOT, project)
    shutil.copytree(SCHEMA_ROOT, project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    return project


def _compile(project: Path, mode: ExecutionMode = ExecutionMode.SIMULATION) -> CompilationReport:
    return compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=mode,
        source_revision=SOURCE_REVISION,
    )


def test_repeated_builds_are_byte_deterministic_and_content_addressed(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)

    first = _compile(project)
    second = _compile(project)

    assert first.valid is True
    assert first.findings == ()
    assert first.manifest is not None
    assert first.manifest_json is not None
    assert first.manifest == second.manifest
    assert first.manifest_json == second.manifest_json
    assert first.manifest.bundle_id == second.manifest.bundle_id
    assert [item.path for item in first.manifest.files] == sorted(
        item.path for item in first.manifest.files
    )

    payload = first.manifest.model_dump(mode="json", by_alias=True, exclude={"bundle_id"})
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert first.manifest.bundle_id == hashlib.sha256(canonical).hexdigest()
    assert json.loads(first.manifest_json)["bundle_id"] == first.manifest.bundle_id


def test_manifest_freezes_exact_components_adapters_packages_recipes_and_tasks(
    tmp_path: Path,
) -> None:
    report = _compile(_project_copy(tmp_path))

    assert report.manifest is not None
    assert len(report.manifest.components) == 6
    assert {item.instance_id for item in report.manifest.components} == {
        "camera-001",
        "fixture-001",
        "gripper-001",
        "laser-001",
        "robot-001",
        "safety-status-001",
    }
    assert all(item.adapter_package is not None for item in report.manifest.components)
    assert len(report.manifest.capabilities) == 10
    assert all(item.provider_instance for item in report.manifest.capabilities)
    assert all(item.endpoint for item in report.manifest.capabilities)
    assert report.manifest.recipes[0].id == "pen-aluminium-reference"
    assert report.manifest.recipes[0].sha256 is not None
    assert report.manifest.tasks[0].id == "pen_engraving"
    assert report.manifest.tasks[0].sha256 is not None
    assert "config/operator-recovery.json" in {item.path for item in report.manifest.files}
    assert "cellforge_adapter_laser_sim" in report.manifest.native_packages
    assert report.manifest.evidence.status == "not-required"


def test_changed_recipe_changes_manifest_and_bundle_id(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    before = _compile(project)
    recipe_path = project / "recipe.yaml"
    recipe_path.write_text(
        recipe_path.read_text(encoding="utf-8").replace(
            "robot_speed_scale: 0.25", "robot_speed_scale: 0.20"
        ),
        encoding="utf-8",
        newline="\n",
    )

    after = _compile(project)

    assert before.valid is True
    assert after.valid is True
    assert before.manifest is not None
    assert after.manifest is not None
    assert before.manifest.bundle_id != after.manifest.bundle_id
    assert before.manifest.recipes[0].sha256 != after.manifest.recipes[0].sha256


def test_operator_recovery_catalog_is_validated_and_content_addressed(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    before = _compile(project)
    catalog_path = project / "operator" / "operator-recovery.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["actions"][0]["instructions"] += " Record the inspection result."
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8", newline="\n")

    after = _compile(project)

    assert before.manifest is not None
    assert after.manifest is not None
    assert before.manifest.bundle_id != after.manifest.bundle_id
    before_file = next(
        item for item in before.manifest.files if item.path == "config/operator-recovery.json"
    )
    after_file = next(
        item for item in after.manifest.files if item.path == "config/operator-recovery.json"
    )
    assert before_file.sha256 != after_file.sha256

    catalog["actions"][0]["service_name"] = "/arbitrary/service"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8", newline="\n")
    invalid = _compile(project)
    assert invalid.manifest is None
    assert "compiler.operator-recovery-invalid" in {finding.code for finding in invalid.findings}


def test_production_rejects_simulated_components_unapproved_recipe_and_evidence(
    tmp_path: Path,
) -> None:
    report = _compile(_project_copy(tmp_path), ExecutionMode.PRODUCTION)
    codes = {finding.code for finding in report.findings}

    assert report.valid is False
    assert report.manifest is None
    assert "resolver.support-level-unsupported" in codes
    assert "resolver.adapter-missing" in codes
    assert "compiler.production-recipe-unapproved" in codes
    assert "compiler.production-evidence-unverified" in codes


def test_invalid_document_returns_structured_failure_and_skips_later_stages(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    (project / "cell.yaml").write_text("[invalid", encoding="utf-8", newline="\n")

    report = _compile(project)

    assert report.valid is False
    assert report.manifest is None
    assert any(finding.code == "source.parse-failed" for finding in report.findings)
    assert report.stages[0].status == "failed"
    assert all(stage.status == "skipped" for stage in report.stages[1:])


def test_missing_behavior_tree_is_a_failure_not_a_silent_success(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    (project / "behavior_tree.xml").unlink()

    report = _compile(project)

    assert report.valid is False
    assert report.manifest is None
    assert any(finding.code == "compiler.reference-not-found" for finding in report.findings)
    behavior_stage = next(
        stage for stage in report.stages if stage.stage == "behavior-tree-validation"
    )
    assert behavior_stage.status == "failed"


def test_invalid_source_revision_is_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.SIMULATION,
        source_revision="main",
    )

    assert report.valid is False
    assert report.manifest is None
    assert any(finding.code == "compiler.source-revision-invalid" for finding in report.findings)


def test_manifest_writer_never_overwrites_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    assert write_manifest(output, '{"bundle_id":"first"}') == output.resolve()

    with pytest.raises(ManifestWriteError, match="already exists"):
        write_manifest(output, '{"bundle_id":"second"}')

    assert json.loads(output.read_text(encoding="utf-8"))["bundle_id"] == "first"
