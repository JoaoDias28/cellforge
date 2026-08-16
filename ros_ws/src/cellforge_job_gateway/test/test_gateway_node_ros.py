"""Jazzy integration test for public gateway-to-supervisor action flow."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import rclpy
import yaml
from cellforge_interfaces.action import ExecuteFrozenJob, RunJob
from cellforge_job_gateway.node import JobGatewayNode
from rclpy.action import ActionClient, ActionServer, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter

CELL_ID = "0d3c6b63-a57f-4207-8638-e4cf76efec90"


def canonical(document: dict[str, Any]) -> bytes:
    return json.dumps(document, separators=(",", ":"), sort_keys=True).encode()


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_bundle(root: Path) -> None:
    recipe = {
        "schema_version": "0.1.0",
        "recipe": {"id": "reference", "version": 1, "name": "Reference", "status": "TESTED"},
        "compatibility": {"cell_ids": [CELL_ID], "required_capabilities": []},
        "product": {"material": "anodized_aluminium"},
        "parameters": {},
        "timeouts": {"process": 1.0},
        "traceability": {"record_fields": []},
    }
    recipe_bytes = yaml.safe_dump(recipe, sort_keys=True).encode()
    task_bytes = b'<root BTCPP_format="4"><BehaviorTree ID="Main"/></root>\n'
    recipe_path = root / "recipes" / "reference" / "1" / "recipe.yaml"
    task_path = root / "config" / "behavior-trees" / "reference@1.xml"
    recipe_path.parent.mkdir(parents=True)
    task_path.parent.mkdir(parents=True)
    recipe_path.write_bytes(recipe_bytes)
    task_path.write_bytes(task_bytes)
    manifest: dict[str, Any] = {
        "schema_version": "0.1.0",
        "source_revision": "1" * 40,
        "cell_id": CELL_ID,
        "target_profile": "test",
        "execution_mode": "simulation",
        "capabilities": [],
        "components": [],
        "recipes": [
            {
                "id": "reference",
                "version": 1,
                "status": "TESTED",
                "path": "recipes/reference/1/recipe.yaml",
                "sha256": sha256(recipe_bytes),
            }
        ],
        "tasks": [
            {
                "id": "reference@1",
                "path": "config/behavior-trees/reference@1.xml",
                "sha256": sha256(task_bytes),
            }
        ],
        "calibrations": [],
        "native_packages": [],
        "containers": [],
        "external_prerequisites": [],
        "evidence": {"required": False, "status": "not-required"},
        "files": [],
    }
    manifest["bundle_id"] = sha256(canonical(manifest))
    (root / "manifest.json").write_bytes(canonical(manifest))


def make_goal(payload: str = '{"text":"OK"}', *, idempotency_key: str = "order-001") -> RunJob.Goal:
    goal = RunJob.Goal()
    goal.job_id = "11111111-1111-4111-8111-111111111111"
    goal.cell_id = CELL_ID
    goal.recipe_id = "reference"
    goal.recipe_version = 1
    goal.task_id = "reference@1"
    goal.input_payload_json = payload
    goal.execution_mode = "simulation"
    goal.idempotency_key = idempotency_key
    goal.timeout.sec = 3
    return goal


def wait_future(future: Any, timeout: float = 5.0) -> Any:
    deadline = time.monotonic() + timeout
    while not future.done() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert future.done()
    return future.result()


def test_gateway_forwards_once_persists_then_replays_and_rejects_conflict() -> None:
    if not rclpy.ok():
        rclpy.init()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        bundle = root / "bundle"
        bundle.mkdir()
        write_bundle(bundle)
        database = root / "jobs.db"
        gateway = JobGatewayNode(
            parameter_overrides=[
                Parameter("bundle_root", value=str(bundle)),
                Parameter("database_path", value=str(database)),
            ]
        )
        harness = Node("job_gateway_test_harness")
        supervisor_calls = 0

        frozen_goals: list[Any] = []

        def execute_supervisor(goal_handle: Any) -> ExecuteFrozenJob.Result:
            nonlocal supervisor_calls
            supervisor_calls += 1
            frozen_goals.append(goal_handle.request)
            result = ExecuteFrozenJob.Result()
            result.trace_id = goal_handle.request.trace_id
            if json.loads(goal_handle.request.input_payload_json).get("hang"):
                while not goal_handle.is_cancel_requested:
                    time.sleep(0.01)
                result.success = False
                result.result_code = "supervisor.job.cancelled"
                result.result_message = "Cancelled."
                result.output_payload_json = "{}"
                goal_handle.canceled()
            else:
                result.success = True
                result.result_code = "supervisor.job.completed"
                result.result_message = "Done."
                result.output_payload_json = '{"count":1}'
                goal_handle.succeed()
            return result

        supervisor = ActionServer(
            harness,
            ExecuteFrozenJob,
            "/cell/supervisor/run_job",
            execute_callback=execute_supervisor,
            cancel_callback=lambda _goal: CancelResponse.ACCEPT,
            callback_group=ReentrantCallbackGroup(),
        )
        client = ActionClient(harness, RunJob, "/cell/run_job")
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(gateway)
        executor.add_node(harness)
        spin = threading.Thread(target=executor.spin, daemon=True)
        spin.start()
        try:
            assert client.wait_for_server(timeout_sec=2.0)
            first_handle = wait_future(client.send_goal_async(make_goal()))
            assert first_handle.accepted
            first = wait_future(first_handle.get_result_async())
            assert first.result.success
            assert supervisor_calls == 1
            assert first.result.trace_id == frozen_goals[0].trace_id
            assert (
                frozen_goals[0].bundle_id
                == json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["bundle_id"]
            )
            assert frozen_goals[0].source_revision == "1" * 40
            assert frozen_goals[0].recipe_sha256 == sha256(
                (bundle / "recipes/reference/1/recipe.yaml").read_bytes()
            )
            assert frozen_goals[0].task_sha256 == sha256(
                (bundle / "config/behavior-trees/reference@1.xml").read_bytes()
            )

            with closing(sqlite3.connect(database)) as connection:
                status, result_json = connection.execute(
                    "SELECT status, result_json FROM jobs WHERE idempotency_key = 'order-001'"
                ).fetchone()
            assert status == "TERMINAL"
            assert json.loads(result_json)["result_code"] == "supervisor.job.completed"

            replay_handle = wait_future(client.send_goal_async(make_goal()))
            replay = wait_future(replay_handle.get_result_async())
            assert replay.result.success
            assert supervisor_calls == 1

            conflict_handle = wait_future(client.send_goal_async(make_goal('{"text":"OTHER"}')))
            conflict = wait_future(conflict_handle.get_result_async())
            assert not conflict.result.success
            assert conflict.result.result_code == "gateway.idempotency.conflict"
            assert supervisor_calls == 1

            cancel_handle = wait_future(
                client.send_goal_async(make_goal('{"hang":true}', idempotency_key="order-cancel"))
            )
            wait_future(cancel_handle.cancel_goal_async())
            cancelled = wait_future(cancel_handle.get_result_async())
            assert cancelled.result.result_code == "supervisor.job.cancelled"

            timeout_goal = make_goal('{"hang":true}', idempotency_key="order-timeout")
            timeout_goal.timeout.sec = 0
            timeout_goal.timeout.nanosec = 100_000_000
            timeout_handle = wait_future(client.send_goal_async(timeout_goal))
            timed_out = wait_future(timeout_handle.get_result_async())
            assert timed_out.result.result_code == "gateway.supervisor.outcome_unknown"
        finally:
            executor.shutdown()
            spin.join(timeout=2.0)
            client.destroy()
            supervisor.destroy()
            gateway.destroy_node()
            harness.destroy_node()
    rclpy.shutdown()
