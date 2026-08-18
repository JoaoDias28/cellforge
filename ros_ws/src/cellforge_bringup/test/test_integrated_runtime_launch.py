"""ROS 2 launch acceptance for the complete Task 025 offline L0 runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

import launch
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from ament_index_python.packages import get_package_share_directory
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from std_msgs.msg import String

ROOT = Path(__file__).resolve().parents[4]
PROJECT = ROOT / "examples" / "pen_engraving"
PORT = 19080
TOKEN = "task-025-operator"
MAINTAINER_TOKEN = "task-025-maintainer"
CELL_ID = "0d3c6b63-a57f-4207-8638-e4cf76efec90"
SOURCE_REVISION = "a" * 40


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _prepare_fixture(root: Path) -> tuple[Path, Path, Path, str]:
    bundle = root / "bundle"
    state = root / "state"
    auth = root / "operator-auth.json"
    sources = {
        "config/cell.yaml": PROJECT / "cell.yaml",
        "assets/scene.usda": PROJECT / "scene.usda",
        "config/behavior-trees/pen_engraving.xml": PROJECT / "behavior_tree.xml",
        "config/behavior-tree-plugins/cellforge_pen_bt_nodes.json": (
            PROJECT / "behavior_tree_plugins" / "cellforge_pen_bt_nodes.json"
        ),
        "config/adapters/runtime.json": PROJECT / "runtime" / "l0-adapters.json",
        "config/operator-recovery.json": PROJECT / "operator" / "operator-recovery.json",
        "recipes/pen-aluminium-reference@1.yaml": PROJECT / "recipe.yaml",
    }
    inventory: list[dict[str, object]] = []
    for relative, source in sources.items():
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if relative == "config/adapters/runtime.json":
            adapter_document = json.loads(target.read_text(encoding="utf-8"))
            adapter_document["nodes"]["mock_laser"]["operations"]["process.action.execute_cycle"][
                "duration_seconds"
            ] = 1.0
            target.write_text(json.dumps(adapter_document, sort_keys=True), encoding="utf-8")
        content = target.read_bytes()
        inventory.append({"path": relative, "sha256": _digest(content), "size": len(content)})
    tree_digest = _digest(sources["config/behavior-trees/pen_engraving.xml"].read_bytes())
    recipe_digest = _digest(sources["recipes/pen-aluminium-reference@1.yaml"].read_bytes())
    plugin_digest = _digest(
        sources["config/behavior-tree-plugins/cellforge_pen_bt_nodes.json"].read_bytes()
    )
    required_devices = [
        "camera-001",
        "fixture-001",
        "gripper-001",
        "laser-001",
        "robot-001",
        "safety-status-001",
    ]
    topics = {
        "cell_state": "/cell/state",
        "events": "/events/job",
        "safety_state": "/safety/state",
        "supervisor_state": "/cell/supervisor_state",
        **{
            f"device.{item}": f"/device/{item.replace('-', '_')}/state" for item in required_devices
        },
    }
    endpoints = {
        "operator_action": "/cell/operator_action",
        "run_job": "/cell/run_job",
        "supervisor_run_job": "/cell/supervisor/run_job",
        "motion.move_to_pose": "/skills/move_to_pose",
        "motion.execute_manipulation": "/skills/execute_manipulation",
        "motion.sync_planning_scene": "/motion/sync_planning_scene",
        "capability.fixture.clamp": "/device/fixture_001/clamp",
        "capability.fixture.release": "/device/fixture_001/release",
        "capability.fixture.verify_seated": "/device/fixture_001/verify_seated",
        "capability.gripper.close": "/device/gripper_001/close",
        "capability.gripper.open": "/device/gripper_001/open",
        "capability.process.select_program": "/device/laser_001/select_program",
        "capability.process.execute_cycle": "/device/laser_001/execute_cycle",
        "capability.robot_motion.execute_trajectory": ("/device/robot_001/execute_trajectory"),
        "capability.vision.locate_object": "/device/camera_001/locate_object",
        "capability.vision.inspect_object": "/device/camera_001/inspect_object",
    }
    executables = {
        "adapter": {"package": "cellforge_mock_adapters", "executable": "mock_device_node"},
        "coordinator": {"package": "cellforge_bringup", "executable": "runtime_coordinator"},
        "gateway": {"package": "cellforge_job_gateway", "executable": "job_gateway"},
        "motion_l0": {
            "package": "cellforge_motion",
            "executable": "cellforge_l0_motion_service",
        },
        "motion_l2": {"package": "cellforge_motion", "executable": "cellforge_motion_service"},
        "operator": {"package": "cellforge_operator_api", "executable": "operator_api"},
        "safety_status": {
            "package": "cellforge_mock_adapters",
            "executable": "mock_safety_status_node",
        },
        "state": {"package": "cellforge_state_trace", "executable": "state_aggregator"},
        "supervisor": {
            "package": "cellforge_supervisor",
            "executable": "cellforge_supervisor_node",
        },
        "trace": {
            "package": "cellforge_state_trace",
            "executable": "durable_event_recorder",
        },
    }
    manifest: dict[str, Any] = {
        "schema_version": "0.1.0",
        "bundle_id": "0" * 64,
        "source_revision": SOURCE_REVISION,
        "cell_id": CELL_ID,
        "target_profile": "pen-sim-amd64",
        "execution_mode": "simulation",
        "capabilities": [
            {
                "task_id": "pen_engraving",
                "contract": contract,
                "version": "1.0.0",
                "provider_instance": provider,
                "endpoint": endpoint,
            }
            for contract, provider, endpoint in [
                ("fixture.clamp", "fixture-001", "clamp"),
                ("fixture.release", "fixture-001", "release"),
                ("fixture.verify_seated", "fixture-001", "verify_seated"),
                ("gripper.close", "gripper-001", "close"),
                ("gripper.open", "gripper-001", "open"),
                ("process.execute_cycle", "laser-001", "execute_cycle"),
                ("process.select_program", "laser-001", "select_program"),
                ("robot_motion.execute_trajectory", "robot-001", "execute_trajectory"),
                ("vision.inspect_object", "camera-001", "inspect_object"),
                ("vision.locate_object", "camera-001", "locate_object"),
            ]
        ],
        "components": [],
        "recipes": [
            {
                "id": "pen-aluminium-reference",
                "version": 1,
                "status": "TESTED",
                "path": "recipes/pen-aluminium-reference@1.yaml",
                "sha256": recipe_digest,
            }
        ],
        "tasks": [
            {
                "id": "pen_engraving",
                "path": "config/behavior-trees/pen_engraving.xml",
                "sha256": tree_digest,
            }
        ],
        "behavior_tree_plugins": [
            {
                "package": "cellforge_pen_bt_nodes",
                "library": "cellforge_pen_bt_nodes",
                "manifest_path": "config/behavior-tree-plugins/cellforge_pen_bt_nodes.json",
                "manifest_sha256": plugin_digest,
            }
        ],
        "calibrations": [],
        "native_packages": sorted(
            {value["package"] for value in executables.values()} | {"cellforge_pen_bt_nodes"}
        ),
        "containers": [],
        "external_prerequisites": [],
        "runtime": {
            "simulation_fidelity": "L0",
            "topics": topics,
            "endpoints": endpoints,
            "required_devices": required_devices,
            "tree_root": "config/behavior-trees",
            "cell_config_path": "config/cell.yaml",
            "scene_path": "assets/scene.usda",
            "adapter_configuration_path": "config/adapters/runtime.json",
            "recovery_catalog_path": "config/operator-recovery.json",
            "executables": executables,
        },
        "evidence": {"required": False, "status": "not-required"},
        "files": sorted(inventory, key=lambda item: str(item["path"])),
    }
    manifest["bundle_id"] = _digest(
        _canonical({k: v for k, v in manifest.items() if k != "bundle_id"})
    )
    (bundle / "manifest.json").write_bytes(_canonical(manifest) + b"\n")
    auth.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "tokens": [
                    {
                        "token_sha256": _digest(TOKEN.encode()),
                        "principal_id": "task-025-operator",
                        "display_name": "Task 025 Operator",
                        "role": "operator",
                    },
                    {
                        "token_sha256": _digest(MAINTAINER_TOKEN.encode()),
                        "principal_id": "task-025-maintainer",
                        "display_name": "Task 025 Maintainer",
                        "role": "maintainer",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return bundle, state, auth, str(manifest["bundle_id"])


@pytest.mark.launch_test
def generate_test_description() -> tuple[launch.LaunchDescription, dict[str, object]]:
    fixture_root = Path(tempfile.mkdtemp(prefix="cellforge-task-025-"))
    bundle, state, auth, bundle_id = _prepare_fixture(fixture_root)
    launch_file = (
        Path(get_package_share_directory("cellforge_bringup"))
        / "launch"
        / "integrated_runtime.launch.py"
    )
    runtime = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(launch_file)),
        launch_arguments={
            "bundle_root": str(bundle),
            "fidelity": "L0",
            "local_state_root": str(state),
            "operator_auth": str(auth),
            "operator_port": str(PORT),
        }.items(),
    )
    return (
        launch.LaunchDescription([runtime, launch_testing.actions.ReadyToTest()]),
        {"fixture_root": fixture_root, "state_root": state, "bundle_id": bundle_id},
    )


class TestIntegratedRuntime(unittest.TestCase):
    def test_nominal_cancel_fault_recovery_persistence_identity_and_offline(
        self, state_root: Path, bundle_id: str
    ) -> None:
        health = _wait_json("GET", "/health", token=None, timeout=30.0)
        self.assertEqual(health, {"status": "healthy", "bundle_id": bundle_id})
        status = _wait_ready(timeout=30.0)
        self.assertEqual(status["state"], "READY")
        self.assertTrue(status["safety_healthy"])
        self.assertTrue(status["all_required_devices_ready"])

        nominal = _job("nominal", timeout=20.0)
        nominal_result: dict[str, Any] = {}
        thread = threading.Thread(
            target=lambda: nominal_result.update(_json("POST", "/api/v1/jobs", nominal)),
            daemon=True,
        )
        thread.start()
        observed_live_identity = False
        deadline = time.monotonic() + 10.0
        while thread.is_alive() and time.monotonic() < deadline:
            active = _json("GET", "/api/v1/jobs/active")
            identity = _json("GET", "/api/v1/identity")
            if active.get("active_job") and active["active_job"].get("active_step"):
                observed_live_identity = identity.get("bundle_id") == bundle_id
                if observed_live_identity:
                    break
            time.sleep(0.05)
        thread.join(timeout=20.0)
        self.assertFalse(thread.is_alive())
        self.assertTrue(observed_live_identity)
        self.assertTrue(nominal_result["success"])
        self.assertEqual(nominal_result["code"], "supervisor.job.completed")
        trace_id = nominal_result["trace_id"]
        trace = _wait_trace(trace_id, timeout=10.0)
        self.assertEqual(trace["bundle_id"], bundle_id)
        self.assertEqual(trace["source_revision"], SOURCE_REVISION)
        self.assertEqual(trace["recipe_id"], "pen-aluminium-reference")
        self.assertEqual(trace["task_id"], "pen_engraving")
        self.assertIn(trace["final_event_type"], {"job.completed", "cell.state.changed"})

        _wait_stable_ready(timeout=10.0)
        cancel_job = _job("cancel", timeout=20.0)
        cancel_result: dict[str, Any] = {}
        cancel_thread = threading.Thread(
            target=lambda: cancel_result.update(_json("POST", "/api/v1/jobs", cancel_job)),
            daemon=True,
        )
        cancel_thread.start()
        _wait_active(cancel_job["job_id"], timeout=5.0)
        cancel_response = _json(
            "POST", f"/api/v1/jobs/{cancel_job['job_id']}/cancel", {"timeout_seconds": 5.0}
        )
        self.assertIn(
            cancel_response["code"],
            {"operator.job.cancel_requested", "operator.job.cancel_rejected"},
        )
        cancel_thread.join(timeout=15.0)
        self.assertFalse(cancel_thread.is_alive())
        self.assertFalse(cancel_result["success"])
        self.assertIn(
            cancel_result["code"],
            {"supervisor.job.cancelled", "gateway.supervisor.outcome_unknown"},
        )

        _wait_stable_ready(timeout=10.0)
        if not rclpy.ok():
            rclpy.init()
        node = rclpy.create_node("task_025_fault_injector")
        publisher = node.create_publisher(String, "/simulation/fault_injection", 10)
        discovery_deadline = time.monotonic() + 10.0
        while publisher.get_subscription_count() < 5 and time.monotonic() < discovery_deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        self.assertGreater(publisher.get_subscription_count(), 0)
        message = String()
        message.data = json.dumps(
            {"component_instance_id": "laser-001", "fault_code": "laser.process.timeout"}
        )
        for _ in range(50):
            publisher.publish(message)
            rclpy.spin_once(node, timeout_sec=0.05)
        time.sleep(1.0)
        node.destroy_node()
        fault_result = _json("POST", "/api/v1/jobs", _job("fault", timeout=20.0))
        self.assertFalse(fault_result["success"])
        self.assertEqual(fault_result["code"], "laser.process.timeout")
        faults = _wait_fault("laser.process.timeout", timeout=5.0)
        fault_id = faults[0]["fault_id"]
        acknowledged = _json(
            "POST",
            "/api/v1/recovery-actions/acknowledge-laser-timeout",
            {"fault_id": fault_id, "confirmation": "ACKNOWLEDGE", "timeout_seconds": 5.0},
        )
        self.assertEqual(acknowledged["code"], "operator.recovery.acknowledged")
        unavailable = _json(
            "POST",
            "/api/v1/recovery-actions/inspect-laser-after-timeout",
            {
                "fault_id": fault_id,
                "confirmation": "ENTER MAINTENANCE",
                "timeout_seconds": 5.0,
            },
            token=MAINTAINER_TOKEN,
        )
        self.assertEqual(unavailable["code"], "operator.recovery.service_unavailable")

        with sqlite3.connect(state_root / "jobs.db") as connection:
            rows = connection.execute(
                "SELECT status, result_json FROM jobs ORDER BY idempotency_key"
            ).fetchall()
        self.assertGreaterEqual(len(rows), 3)
        result_codes = {
            json.loads(result_json)["result_code"]
            for status, result_json in rows
            if status == "TERMINAL" and result_json
        }
        self.assertIn("supervisor.job.completed", result_codes)
        with sqlite3.connect(state_root / "traces.db") as connection:
            persisted = connection.execute(
                "SELECT COUNT(*) FROM events WHERE trace_id = ? AND bundle_id = ?",
                (trace_id, bundle_id),
            ).fetchone()[0]
            completed = connection.execute(
                "SELECT COUNT(*) FROM events WHERE trace_id = ? AND event_type = 'job.completed'",
                (trace_id,),
            ).fetchone()[0]
        self.assertGreater(persisted, 0)
        self.assertEqual(completed, 1)
        self.assertEqual(os.environ.get("CELLFORGE_PLATFORM_REQUIRED", ""), "")


def _job(suffix: str, *, timeout: float) -> dict[str, object]:
    return {
        "job_id": str(uuid4()),
        "cell_id": CELL_ID,
        "recipe_id": "pen-aluminium-reference",
        "recipe_version": 1,
        "task_id": "pen_engraving",
        "input_payload": {"engraving_text": f"CELLFORGE-{suffix}"},
        "execution_mode": "simulation",
        "idempotency_key": f"task-025-{suffix}-{uuid4()}",
        "timeout_seconds": timeout,
    }


def _json(
    method: str, path: str, body: object | None = None, *, token: str = TOKEN
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30.0) as response:
            result: object = json.loads(response.read())
    except urllib.error.HTTPError as error:
        result = json.loads(error.read())
    assert isinstance(result, dict)
    return result


def _wait_json(method: str, path: str, *, token: str | None, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return _json(method, path, token=TOKEN if token else "")
        except (OSError, TimeoutError):
            time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {path}")


def _wait_ready(*, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = _json("GET", "/api/v1/status")
        if status.get("state") == "READY":
            return status
        time.sleep(0.1)
    raise AssertionError("Runtime did not reach READY")


def _wait_stable_ready(*, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    consecutive = 0
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = _json("GET", "/api/v1/status")
        if latest.get("state") == "READY" and latest.get("active_job") is None:
            consecutive += 1
            if consecutive >= 3:
                return latest
        else:
            consecutive = 0
        time.sleep(0.1)
    raise AssertionError(f"Runtime did not remain quiescent and READY: {latest}")


def _wait_active(job_id: object, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        active = _json("GET", "/api/v1/jobs/active").get("active_job")
        if isinstance(active, dict) and active.get("job_id") == job_id:
            return
        time.sleep(0.05)
    raise AssertionError("Job did not become active")


def _wait_trace(trace_id: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _json("GET", f"/api/v1/traces/{trace_id}/summary")
        if result.get("trace_id") == trace_id and result.get("final_event_type") in {
            "job.completed",
            "cell.state.changed",
        }:
            return result
        time.sleep(0.1)
    raise AssertionError("Completed trace did not persist")


def _wait_fault(code: str, *, timeout: float) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        faults = _json("GET", "/api/v1/faults").get("faults", [])
        matches = [item for item in faults if item.get("code") == code]
        if matches:
            return matches
        time.sleep(0.1)
    raise AssertionError(f"Fault {code} was not visible")
