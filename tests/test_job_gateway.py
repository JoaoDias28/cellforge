"""Task 012 durable job gateway and recipe-freeze tests."""

from __future__ import annotations

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "ros_ws" / "src" / "cellforge_job_gateway"
sys.path.insert(0, str(PACKAGE_ROOT))

from cellforge_job_gateway import (  # noqa: E402
    BundleResolver,
    GatewayError,
    JobRequest,
    JobResult,
    PrepareKind,
    SqliteJobStore,
)

CELL_ID = "0d3c6b63-a57f-4207-8638-e4cf76efec90"
RECIPE_ID = "pen-aluminium-reference"
TASK_ID = "pen-engraving@1"


def _canonical(document: dict[str, Any]) -> bytes:
    return json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_bundle(
    root: Path,
    *,
    mode: str = "simulation",
    status: str = "TESTED",
    recipe_path: str = "config/recipes/pen.yaml",
) -> Path:
    recipe = yaml.safe_load(
        (ROOT / "examples" / "pen_engraving" / "recipe.yaml").read_text(encoding="utf-8")
    )
    recipe["recipe"]["status"] = status
    recipe_bytes = yaml.safe_dump(recipe, sort_keys=True).encode()
    task_bytes = b'<root BTCPP_format="4"><BehaviorTree ID="Main"/></root>\n'
    recipe_file = root / recipe_path
    task_file = root / "config" / "trees" / "pen-engraving@1.xml"
    recipe_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.parent.mkdir(parents=True, exist_ok=True)
    recipe_file.write_bytes(recipe_bytes)
    task_file.write_bytes(task_bytes)
    manifest: dict[str, Any] = {
        "schema_version": "0.1.0",
        "source_revision": "1" * 40,
        "cell_id": CELL_ID,
        "target_profile": "pen-sim-amd64",
        "execution_mode": mode,
        "capabilities": [
            {"task_id": TASK_ID, "contract": item}
            for item in recipe["compatibility"]["required_capabilities"]
        ],
        "components": [],
        "recipes": [
            {
                "id": RECIPE_ID,
                "version": 1,
                "status": status,
                "path": recipe_path,
                "sha256": _sha(recipe_bytes),
            }
        ],
        "tasks": [
            {
                "id": TASK_ID,
                "path": "config/trees/pen-engraving@1.xml",
                "sha256": _sha(task_bytes),
            }
        ],
        "calibrations": [],
        "native_packages": ["cellforge_job_gateway", "cellforge_supervisor"],
        "containers": [],
        "external_prerequisites": [],
        "evidence": {"required": False, "status": "not-required"},
        "files": [],
    }
    manifest["bundle_id"] = _sha(_canonical(manifest))
    (root / "manifest.json").write_bytes(_canonical(manifest))
    return root


def request(**changes: Any) -> JobRequest:
    values: dict[str, Any] = {
        "job_id": "11111111-1111-4111-8111-111111111111",
        "cell_id": CELL_ID,
        "recipe_id": RECIPE_ID,
        "recipe_version": 1,
        "task_id": TASK_ID,
        "input_payload_json": '{"text":"CELLFORGE"}',
        "execution_mode": "simulation",
        "idempotency_key": "enterprise-order-001",
    }
    values.update(changes)
    return JobRequest(**values)


def test_simulation_accepts_and_freezes_tested_reference_recipe(tmp_path: Path) -> None:
    resolver = BundleResolver(write_bundle(tmp_path / "bundle"))
    frozen = resolver.freeze(request(), "22222222-2222-4222-8222-222222222222")

    assert frozen.recipe["recipe"]["status"] == "TESTED"
    assert frozen.bundle_id == resolver.manifest["bundle_id"]
    assert frozen.recipe_sha256 == resolver.manifest["recipes"][0]["sha256"]
    assert frozen.task_sha256 == resolver.manifest["tasks"][0]["sha256"]
    assert frozen.to_document()["job"]["input_payload"] == {"text": "CELLFORGE"}


def test_unapproved_recipe_is_rejected_in_production(tmp_path: Path) -> None:
    resolver = BundleResolver(write_bundle(tmp_path / "bundle", mode="production", status="TESTED"))
    with pytest.raises(GatewayError) as raised:
        resolver.freeze(request(execution_mode="production"), "trace")
    assert raised.value.code == "gateway.recipe.status_not_allowed"


def test_production_accepts_only_exact_approved_bundle_recipe(tmp_path: Path) -> None:
    resolver = BundleResolver(
        write_bundle(tmp_path / "bundle", mode="production", status="APPROVED")
    )
    frozen = resolver.freeze(request(execution_mode="production"), "trace")
    assert frozen.recipe["recipe"]["status"] == "APPROVED"


def test_physical_execution_rejects_unknown_material(tmp_path: Path) -> None:
    bundle = write_bundle(tmp_path / "bundle", mode="commissioning", status="TESTED")
    recipe_path = bundle / "config" / "recipes" / "pen.yaml"
    recipe = yaml.safe_load(recipe_path.read_text())
    recipe["product"]["material"] = "unknown"
    recipe_bytes = yaml.safe_dump(recipe, sort_keys=True).encode()
    recipe_path.write_bytes(recipe_bytes)
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["recipes"][0]["sha256"] = _sha(recipe_bytes)
    del manifest["bundle_id"]
    manifest["bundle_id"] = _sha(_canonical(manifest))
    (bundle / "manifest.json").write_bytes(_canonical(manifest))

    with pytest.raises(GatewayError) as raised:
        BundleResolver(bundle).freeze(request(execution_mode="commissioning"), "trace")
    assert raised.value.code == "gateway.recipe.material_unknown"


def test_conflicting_idempotency_payload_cannot_run_twice(tmp_path: Path) -> None:
    resolver = BundleResolver(write_bundle(tmp_path / "bundle"))
    store = SqliteJobStore(tmp_path / "jobs.db")
    try:
        first = resolver.freeze(request(), "trace-1")
        assert store.prepare(first).kind is PrepareKind.NEW
        conflicting = resolver.freeze(request(input_payload_json='{"text":"DIFFERENT"}'), "trace-2")
        with pytest.raises(GatewayError) as raised:
            store.prepare(conflicting)
        assert raised.value.code == "gateway.idempotency.conflict"
    finally:
        store.close()


def test_matching_active_duplicate_is_rejected_without_resubmission(tmp_path: Path) -> None:
    resolver = BundleResolver(write_bundle(tmp_path / "bundle"))
    store = SqliteJobStore(tmp_path / "jobs.db")
    try:
        store.prepare(resolver.freeze(request(), "trace-1"))
        with pytest.raises(GatewayError) as raised:
            store.prepare(resolver.freeze(request(), "trace-2"))
        assert raised.value.code == "gateway.idempotency.active"
    finally:
        store.close()


def test_completed_duplicate_replays_result_and_preserves_original_trace(tmp_path: Path) -> None:
    resolver = BundleResolver(write_bundle(tmp_path / "bundle"))
    store = SqliteJobStore(tmp_path / "jobs.db")
    try:
        original = resolver.freeze(request(), "trace-1")
        store.prepare(original)
        result = JobResult(True, "supervisor.job.completed", "Done.", '{"count":1}', "trace-1")
        store.finish(request().idempotency_key, result)

        replay = store.prepare(resolver.freeze(request(), "trace-2"))
        assert replay.kind is PrepareKind.REPLAY
        assert replay.result == result
    finally:
        store.close()


def test_same_request_against_different_bundle_is_an_idempotency_conflict(tmp_path: Path) -> None:
    first_bundle = write_bundle(tmp_path / "first")
    second_bundle = write_bundle(tmp_path / "second")
    manifest_path = second_bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source_revision"] = "2" * 40
    del manifest["bundle_id"]
    manifest["bundle_id"] = _sha(_canonical(manifest))
    manifest_path.write_bytes(_canonical(manifest))
    store = SqliteJobStore(tmp_path / "jobs.db")
    try:
        store.prepare(BundleResolver(first_bundle).freeze(request(), "trace-1"))
        with pytest.raises(GatewayError) as raised:
            store.prepare(BundleResolver(second_bundle).freeze(request(), "trace-2"))
        assert raised.value.code == "gateway.idempotency.conflict"
    finally:
        store.close()


def test_result_is_durable_before_external_completion_observer_runs(tmp_path: Path) -> None:
    resolver = BundleResolver(write_bundle(tmp_path / "bundle"))
    store = SqliteJobStore(tmp_path / "jobs.db")
    try:
        store.prepare(resolver.freeze(request(), "trace-1"))
        store.mark_running(request().idempotency_key)
        result = JobResult(True, "supervisor.job.completed", "Done.", "{}", "trace-1")
        store.finish(request().idempotency_key, result)

        # This read models the public action completion boundary in JobGatewayNode.
        status, frozen, persisted = store.read(request().idempotency_key)
        assert status == "TERMINAL"
        assert frozen["bundle_id"]
        assert persisted == result
    finally:
        store.close()


def test_restart_marks_nonterminal_job_unknown_and_never_replays_work(tmp_path: Path) -> None:
    resolver = BundleResolver(write_bundle(tmp_path / "bundle"))
    database = tmp_path / "jobs.db"
    first = SqliteJobStore(database)
    first.prepare(resolver.freeze(request(), "trace-before-restart"))
    first.mark_running(request().idempotency_key)
    first.close()

    restarted = SqliteJobStore(database)
    try:
        decision = restarted.prepare(resolver.freeze(request(), "new-trace"))
        assert decision.kind is PrepareKind.REPLAY
        assert decision.result is not None
        assert decision.result.result_code == "gateway.restart.outcome_unknown"
        assert decision.result.trace_id == "trace-before-restart"
        assert restarted.read(request().idempotency_key)[0] == "OUTCOME_UNKNOWN"
    finally:
        restarted.close()


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"input_payload_json": "{"}, "gateway.payload.invalid"),
        ({"input_payload_json": "[]"}, "gateway.payload.invalid"),
        ({"execution_mode": "maintenance"}, "gateway.mode.invalid"),
        ({"recipe_version": 0}, "gateway.job.invalid"),
        ({"task_id": "missing@1"}, "gateway.task.not_found"),
        ({"cell_id": "another-cell"}, "gateway.compatibility.cell"),
    ],
)
def test_invalid_or_incompatible_jobs_fail_closed(
    tmp_path: Path, changes: dict[str, Any], code: str
) -> None:
    resolver = BundleResolver(write_bundle(tmp_path / "bundle"))
    with pytest.raises(GatewayError) as raised:
        resolver.freeze(request(**changes), "trace")
    assert raised.value.code == code


def test_recipe_and_task_digest_mismatch_fail_closed(tmp_path: Path) -> None:
    bundle = write_bundle(tmp_path / "bundle")
    resolver = BundleResolver(bundle)
    (bundle / "config" / "recipes" / "pen.yaml").write_text("tampered: true\n")
    with pytest.raises(GatewayError) as recipe_error:
        resolver.freeze(request(), "trace")
    assert recipe_error.value.code == "gateway.recipe.digest_mismatch"

    bundle = write_bundle(tmp_path / "second")
    resolver = BundleResolver(bundle)
    (bundle / "config" / "trees" / "pen-engraving@1.xml").write_text("tampered")
    with pytest.raises(GatewayError) as task_error:
        resolver.freeze(request(), "trace")
    assert task_error.value.code == "gateway.task.digest_mismatch"


def test_bundle_reference_cannot_escape_active_root(tmp_path: Path) -> None:
    bundle = write_bundle(tmp_path / "bundle")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["recipes"][0]["path"] = "../outside.yaml"
    del manifest["bundle_id"]
    manifest["bundle_id"] = _sha(_canonical(manifest))
    (bundle / "manifest.json").write_bytes(_canonical(manifest))
    resolver = BundleResolver(bundle)
    with pytest.raises(GatewayError) as raised:
        resolver.freeze(request(), "trace")
    assert raised.value.code == "gateway.bundle.path_invalid"


def test_missing_recipe_capability_is_rejected(tmp_path: Path) -> None:
    bundle = write_bundle(tmp_path / "bundle")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["capabilities"] = manifest["capabilities"][:-1]
    del manifest["bundle_id"]
    manifest["bundle_id"] = _sha(_canonical(manifest))
    (bundle / "manifest.json").write_bytes(_canonical(manifest))
    with pytest.raises(GatewayError) as raised:
        BundleResolver(bundle).freeze(request(), "trace")
    assert raised.value.code == "gateway.recipe.capability_incompatible"


def test_ros_package_and_endpoint_contracts_are_declared() -> None:
    package = ET.parse(PACKAGE_ROOT / "package.xml").getroot()
    dependencies = {element.text for element in package.findall("exec_depend")}
    assert {"cellforge_interfaces", "python3-yaml", "rclpy"} <= dependencies
    setup_text = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
    assert "job_gateway = cellforge_job_gateway.node:main" in setup_text

    node_text = (PACKAGE_ROOT / "cellforge_job_gateway" / "node.py").read_text(encoding="utf-8")
    assert '"/cell/run_job"' in node_text
    assert '"/cell/supervisor/run_job"' in node_text
    assert node_text.index("self._store.finish") < node_text.rindex("self._set_terminal_state")

    supervisor = (
        ROOT / "ros_ws" / "src" / "cellforge_supervisor" / "src" / "supervisor_node.cpp"
    ).read_text(encoding="utf-8")
    assert 'declare_parameter<std::string>("action_name", "/cell/supervisor/run_job")' in supervisor
