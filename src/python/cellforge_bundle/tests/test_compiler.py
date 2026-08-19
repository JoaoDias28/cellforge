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
    assert report.manifest.behavior_tree_plugins[0].package == "cellforge_pen_bt_nodes"
    assert report.manifest.behavior_tree_plugins[0].library == "cellforge_pen_bt_nodes"
    assert report.manifest.behavior_tree_plugins[0].manifest_sha256
    assert "config/behavior-tree-plugins/cellforge_pen_bt_nodes.json" in {
        item.path for item in report.manifest.files
    }
    assert "config/operator-recovery.json" in {item.path for item in report.manifest.files}
    assert "cellforge_mock_adapters" in report.manifest.native_packages
    assert report.manifest.runtime is not None
    assert report.manifest.runtime.simulation_fidelity == "L0"
    assert report.manifest.runtime.tree_root == "config/behavior-trees"
    assert report.manifest.runtime.required_devices == (
        "camera-001",
        "fixture-001",
        "gripper-001",
        "laser-001",
        "robot-001",
        "safety-status-001",
    )
    assert report.manifest.runtime.endpoints["run_job"] == "/cell/run_job"
    assert report.manifest.runtime.endpoints["capability.process.execute_cycle"] == (
        "/device/laser_001/execute_cycle"
    )
    assert report.manifest.runtime.executables["adapter"].executable == "mock_device_node"
    assert "config/adapters/runtime.json" in {item.path for item in report.manifest.files}
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
    import yaml

    project = _project_copy(tmp_path)
    robot_yaml = project / "components" / "robot" / "component.yaml"
    data = yaml.safe_load(robot_yaml.read_text(encoding="utf-8"))
    data["support"]["level"] = "simulated"
    if "adapters" in data:
        data["adapters"]["hardware"] = None
    robot_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = _compile(project, ExecutionMode.PRODUCTION)
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


@pytest.mark.parametrize(
    ("old", "new", "expected_code"),
    [
        ("<LocateProduct ", "<UnknownPenNode ", "compiler.behavior-tree-node-unknown"),
        (" object_type=", ' unexpected="x" object_type=', "compiler.behavior-tree-port-unknown"),
        (
            ' object_type="pen"',
            "",
            "compiler.behavior-tree-port-missing",
        ),
        (
            ' output_pose="{product_pose}"',
            ' output_pose="product_pose"',
            "compiler.behavior-tree-mapping-invalid",
        ),
        (
            ' pose="{product_pose}"',
            ' pose="{missing_pose}"',
            "compiler.behavior-tree-mapping-unresolved",
        ),
    ],
)
def test_behavior_tree_contract_failures_are_compile_time_errors(
    tmp_path: Path, old: str, new: str, expected_code: str
) -> None:
    project = _project_copy(tmp_path)
    tree = project / "behavior_tree.xml"
    tree.write_text(
        tree.read_text(encoding="utf-8").replace(old, new, 1),
        encoding="utf-8",
        newline="\n",
    )

    report = _compile(project)

    assert report.valid is False
    assert expected_code in {finding.code for finding in report.findings}


def test_behavior_tree_plugin_package_must_be_immutable_and_declared(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    profile = project / "deployment-sim.yaml"
    profile.write_text(
        profile.read_text(encoding="utf-8").replace("    - cellforge_pen_bt_nodes\n", "", 1),
        encoding="utf-8",
        newline="\n",
    )

    report = _compile(project)

    assert report.valid is False
    assert "compiler.behavior-tree-plugin-package-undeclared" in {
        finding.code for finding in report.findings
    }


def test_behavior_tree_plugin_manifest_identity_must_match_declaration(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    manifest = project / "behavior_tree_plugins" / "cellforge_pen_bt_nodes.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["plugin"]["package"] = "untrusted_nodes"
    manifest.write_text(json.dumps(document), encoding="utf-8", newline="\n")

    report = _compile(project)

    assert report.valid is False
    assert "compiler.behavior-tree-plugin-manifest-invalid" in {
        finding.code for finding in report.findings
    }


def test_integrated_runtime_fails_closed_when_requested_fidelity_is_unavailable(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    profile = project / "deployment-sim.yaml"
    profile.write_text(
        profile.read_text(encoding="utf-8").replace(
            "simulation_fidelity: L0", "simulation_fidelity: L2"
        ),
        encoding="utf-8",
        newline="\n",
    )

    report = _compile(project)

    assert report.valid is False
    assert report.manifest is None
    assert "compiler.runtime.fidelity-unavailable" in {finding.code for finding in report.findings}


def test_process_action_cannot_be_placed_under_automatic_retry(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    tree = project / "behavior_tree.xml"
    source = tree.read_text(encoding="utf-8")
    source = source.replace(
        "      <ExecuteProcess\n",
        '      <RetryUntilSuccessful num_attempts="2">\n        <ExecuteProcess\n',
    )
    source = source.replace(
        '        recipe_version="{recipe_version}"/>\n',
        '        recipe_version="{recipe_version}"/>\n      </RetryUntilSuccessful>\n',
        1,
    )
    tree.write_text(source, encoding="utf-8", newline="\n")

    report = _compile(project)

    assert report.valid is False
    assert "compiler.behavior-tree-process-retry-forbidden" in {
        finding.code for finding in report.findings
    }


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
