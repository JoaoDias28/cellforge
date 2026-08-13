"""Submit canonical RunJob goals to a running Task 027 Isaac L2 runtime."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import rclpy
import yaml
from cellforge_interfaces.action import RunJob
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

CELL_ID = "0d3c6b63-a57f-4207-8638-e4cf76efec90"


class AcceptanceClient(Node):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__("task_027_runjob_acceptance")
        self.run_job = ActionClient(self, RunJob, "/cell/run_job")
        self.configure = self.create_publisher(String, "/simulation/l2/configure", 10)
        self.events: list[dict[str, Any]] = []
        self.create_subscription(String, "/simulation/l2/events", self._event, 100)
        self._cancel_requested = False

    def _event(self, message: String) -> None:
        value = json.loads(message.data)
        if isinstance(value, dict):
            self.events.append(value)

    def configure_scenario(self, scenario: dict[str, Any], timeout: float = 60.0) -> None:
        scenario_id = str(scenario["scenario"]["id"])
        baseline = len(self.events)
        message = String()
        message.data = json.dumps(scenario, sort_keys=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.configure.publish(message)
            rclpy.spin_once(self, timeout_sec=0.1)
            if any(
                item.get("event_type") == "scenario.configured"
                and item.get("observation", {}).get("scenario_id") == scenario_id
                for item in self.events[baseline:]
            ):
                return
        raise RuntimeError(f"Isaac adapter did not configure scenario '{scenario_id}'")

    def submit(self, scenario: dict[str, Any], *, cancel: bool = False) -> dict[str, Any]:
        if not self.run_job.wait_for_server(timeout_sec=30.0):
            raise RuntimeError("RunJob action server is unavailable")
        identity = scenario["scenario"]
        job = scenario.get("job", {})
        goal = RunJob.Goal()
        goal.job_id = str(uuid4())
        goal.cell_id = CELL_ID
        goal.recipe_id = str(job.get("recipe_id", "pen-aluminium-reference"))
        goal.recipe_version = int(job.get("recipe_version", 1))
        goal.task_id = "pen_engraving"
        goal.input_payload_json = json.dumps(
            job.get("input_payload", {"engraving_text": "CELLFORGE"}), sort_keys=True
        )
        goal.execution_mode = "simulation"
        goal.idempotency_key = f"task-027-{identity['id']}-{uuid4()}"
        timeout = float(identity.get("timeout_seconds", 60.0))
        goal.timeout.sec = int(timeout)
        goal.timeout.nanosec = 0
        self._cancel_requested = False

        def feedback(message: Any) -> None:
            if (
                cancel
                and not self._cancel_requested
                and message.feedback.active_node == "MoveRobotToProcessSafePose"
            ):
                self._cancel_requested = True
                if handle_holder:
                    handle_holder[0].cancel_goal_async()

        handle_holder: list[Any] = []
        future = self.run_job.send_goal_async(goal, feedback_callback=feedback)
        rclpy.spin_until_future_complete(self, future, timeout_sec=30.0)
        handle = future.result()
        if handle is None or not handle.accepted:
            raise RuntimeError(f"RunJob was rejected for scenario '{identity['id']}'")
        handle_holder.append(handle)
        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=timeout + 30.0)
        wrapped = result_future.result()
        if wrapped is None:
            raise RuntimeError(f"RunJob did not finish for scenario '{identity['id']}'")
        result = wrapped.result
        return {
            "scenario_id": str(identity["id"]),
            "seed": int(identity["seed"]),
            "success": bool(result.success),
            "result_code": str(result.result_code),
            "result_message": str(result.result_message),
            "trace_id": str(result.trace_id),
            "action_status": int(wrapped.status),
        }


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain an object")
    return value


def _scenario_paths(project: Path) -> list[Path]:
    return [
        project / "scenarios" / "nominal.yaml",
        project / "physical" / "scenarios" / "dropped_pen.yaml",
        project / "physical" / "scenarios" / "failed_seating.yaml",
        project / "physical" / "scenarios" / "collision.yaml",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--scenario")
    arguments = parser.parse_args()
    project = arguments.project.resolve()
    rclpy.init()
    node = AcceptanceClient()
    results: list[dict[str, Any]] = []
    try:
        paths = _scenario_paths(project)
        if arguments.scenario:
            paths = [path for path in paths if _load(path)["scenario"]["id"] == arguments.scenario]
            if not paths:
                raise RuntimeError(f"Unknown acceptance scenario '{arguments.scenario}'")
        for path in paths:
            scenario = _load(path)
            scenario_id = str(scenario["scenario"]["id"])
            baseline = len(node.events)
            node.configure_scenario(scenario)
            ready_deadline = time.monotonic() + 1.0
            while time.monotonic() < ready_deadline:
                rclpy.spin_once(node, timeout_sec=0.1)
            result = node.submit(scenario, cancel=scenario_id == "pen-operator-cancel")
            adapter_events = node.events[baseline:]
            observed = {
                str(value)
                for event in adapter_events
                for value in (event.get("event_type"), event.get("result_code"))
                if value
            }
            evidence_aliases = {
                "fixture.sensor.seating_failed": ("fixture.seating.false",),
                "simulation.pen.dropped": ("gripper.attachment.false", "product.dropped"),
                "motion.plan.collision": ("collision.detected",),
            }
            observed.update(
                alias
                for code, aliases in evidence_aliases.items()
                if code in observed
                for alias in aliases
            )
            required = {
                str(value)
                for value in scenario.get("assertions", {}).get("required_events", [])
                if not str(value).startswith("job.")
            }
            missing = required - observed
            if missing:
                raise RuntimeError(
                    f"Scenario '{scenario_id}' is missing adapter evidence {sorted(missing)}"
                )
            expected_success = scenario.get("assertions", {}).get("final_status") == "SUCCESS"
            if result["success"] is not expected_success:
                raise RuntimeError(
                    f"Scenario '{scenario_id}' success={result['success']}, "
                    f"expected {expected_success}: {result['result_code']}"
                )
            result["adapter_events"] = adapter_events
            results.append(result)
        report = {
            "schema_version": "0.1.0",
            "kind": "cellforge.isaac_l2_runjob_acceptance",
            "submitted_action": "/cell/run_job",
            "canonical_tree": "behavior_tree.xml",
            "canonical_recipe": "pen-aluminium-reference@1",
            "event_origin": "runtime/adapters",
            "scenario_count": len(results),
            "results": results,
            "laser_qualification_excluded": [
                "beam/material interaction",
                "mark quality",
                "text fidelity",
            ],
        }
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            f"Task 027 RunJob acceptance passed {len(results)}/{len(results)} scenarios; "
            f"report={arguments.report}."
        )
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
