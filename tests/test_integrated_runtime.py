"""Task 025 immutable runtime graph and offline bringup-loader tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from cellforge_bundle import compile_project
from cellforge_domain import ExecutionMode

ROOT = Path(__file__).resolve().parents[1]
BRINGUP_ROOT = ROOT / "ros_ws" / "src" / "cellforge_bringup"
sys.path.insert(0, str(BRINGUP_ROOT))

from cellforge_bringup.runtime import BringupError, load_runtime_bundle  # noqa: E402


def _bundle(tmp_path: Path, *, fidelity: str = "L0") -> Path:
    project = ROOT / "examples" / "pen_engraving"
    target_profile = "pen-sim-amd64" if fidelity == "L0" else "pen-isaac-l2-win64"
    report = compile_project(
        project,
        ROOT / "schemas",
        target_profile=target_profile,
        mode=ExecutionMode.SIMULATION,
        source_revision="a" * 40,
    )
    assert report.valid and report.manifest is not None and report.manifest_json is not None
    bundle = tmp_path / "bundle"
    sources = {
        "config/cell.yaml": project / "cell.yaml",
        "assets/scene.usda": project / "scene.usda",
        "config/behavior-trees/pen_engraving.xml": project / "behavior_tree.xml",
        "config/behavior-tree-plugins/cellforge_pen_bt_nodes.json": (
            project / "behavior_tree_plugins" / "cellforge_pen_bt_nodes.json"
        ),
        "config/adapters/runtime.json": (
            project / "runtime" / ("l0-adapters.json" if fidelity == "L0" else "l2-adapters.json")
        ),
        "config/operator-recovery.json": project / "operator" / "operator-recovery.json",
    }
    for relative, source in sources.items():
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (bundle / "manifest.json").write_text(report.manifest_json, encoding="utf-8", newline="\n")
    return bundle


def test_loader_verifies_exact_identity_graph_files_and_offline_fidelity(tmp_path: Path) -> None:
    runtime = load_runtime_bundle(_bundle(tmp_path), "L0")

    assert runtime.fidelity == "L0"
    assert runtime.bundle_id
    assert runtime.required_devices[-1] == "safety-status-001"
    assert runtime.endpoints["operator_action"] == "/cell/operator_action"
    assert runtime.executables["gateway"].package == "cellforge_job_gateway"
    assert runtime.adapter_configuration.is_file()
    assert runtime.cell_config_sha256 != runtime.scene_sha256

    l2 = load_runtime_bundle(_bundle(tmp_path / "l2", fidelity="L2"), "L2")
    assert l2.fidelity == "L2"
    assert l2.executables["adapter"].package == "cellforge_simulation"
    assert l2.executables["adapter"].executable == "isaac_l2_adapter"
    assert l2.executables["motion_l2"].executable == "cellforge_motion_service"


def test_loader_rejects_tampering_identity_and_fidelity_mismatch(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    adapter_path = bundle / "config" / "adapters" / "runtime.json"
    adapter_path.write_text("{}", encoding="utf-8")
    with pytest.raises(BringupError, match="bringup.manifest.file_mismatch"):
        load_runtime_bundle(bundle, "L0")

    bundle = _bundle(tmp_path / "second")
    with pytest.raises(BringupError, match="bringup.fidelity.identity_mismatch"):
        load_runtime_bundle(bundle, "L2")

    manifest_path = bundle / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["runtime"]["executables"]["adapter"]["executable"] = "unapproved_adapter"
    hash_input = {key: value for key, value in document.items() if key != "bundle_id"}
    document["bundle_id"] = hashlib.sha256(
        json.dumps(hash_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(BringupError, match="bringup.runtime.executables_invalid"):
        load_runtime_bundle(bundle, "L0")

    document["bundle_id"] = "0" * 64
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(BringupError, match="bringup.manifest.identity_mismatch"):
        load_runtime_bundle(bundle, "L0")
