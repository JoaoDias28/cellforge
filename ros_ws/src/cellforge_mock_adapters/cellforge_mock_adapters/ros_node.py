"""ROS 2 (rclpy) node edge for the L0 contract mock adapters.

This module is deliberately thin: every deterministic behavior lives in the pure core modules
(``scenarios``, ``core``, ``devices``), which the repository unit tests exercise without ROS. The
node only converts canonical ROS goals into SDK commands, forwards cancellation and timeouts, and
publishes canonical ``DeviceState`` transitions produced by the SDK.

Requires ROS 2 Jazzy with ``cellforge_interfaces`` and ``cellforge_device_sdk`` sourced. The node
refuses to start on an invalid scenario configuration (fail-fast at startup) and never implements
or bypasses any safety-rated function; interlock status is consumed as read-only scenario data.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from datetime import timedelta
from pathlib import Path
from typing import Any

import rclpy
from cellforge_device_sdk.ids import validate_uuid
from cellforge_device_sdk.models import CapabilityCommand, CommandResult, DeviceState
from cellforge_device_sdk.state import RosDeviceStatePublisher
from cellforge_interfaces.action import (
    ExecuteProcess,
    ExecuteSkill,
    InspectObject,
    LocateObject,
)
from cellforge_interfaces.msg import (
    DeviceState as RosDeviceState,
)
from cellforge_interfaces.msg import (
    PoseEstimate,
)
from cellforge_interfaces.srv import GetDeviceState
from geometry_msgs.msg import PoseStamped
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from cellforge_mock_adapters.devices import build_device_mock
from cellforge_mock_adapters.scenarios import (
    DeviceScenario,
    ScenarioConfigError,
    load_scenario_file,
    parse_device_scenario,
)

_ACTION_TYPES: dict[str, Any] = {
    "vision.action.locate_object": LocateObject,
    "vision.action.inspect_object": InspectObject,
    "process.action.execute_cycle": ExecuteProcess,
}


class _AsyncioBridge:
    """Run the pure-async SDK on one dedicated loop thread behind synchronous rclpy callbacks."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="mock-adapter-asyncio", daemon=True
        )
        self._thread.start()

    def submit(self, coroutine: Coroutine[Any, Any, CommandResult]) -> Future[CommandResult]:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def cancel_command(self, adapter: Any, command_id: str) -> bool:
        async def _cancel() -> bool:
            return bool(adapter.cancel(command_id))

        future = asyncio.run_coroutine_threadsafe(_cancel(), self._loop)
        return bool(future.result(timeout=2.0))

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)


class MockDeviceNode(Node):  # type: ignore[misc]
    """One mock device node exposing canonical actions, state, and state query service."""

    def __init__(
        self,
        *,
        node_name: str = "mock_device",
        parameter_overrides: list[Any] | None = None,
    ) -> None:
        super().__init__(node_name, parameter_overrides=parameter_overrides)
        self.declare_parameter("scenario_file", "")
        self.declare_parameter("scenario_json", "")
        self._bridge = _AsyncioBridge()
        self._commands: dict[bytes, str] = {}
        self._action_servers: list[Any] = []
        self._action_group = ReentrantCallbackGroup()

        scenario = self._load_scenario()
        state_publisher = RosDeviceStatePublisher(
            self.create_publisher(RosDeviceState, "~/state", 10)
        )
        self._adapter = build_device_mock(scenario, state_sink=state_publisher.publish)
        self._state_edge = state_publisher
        self.create_service(
            GetDeviceState,
            "~/get_state",
            self._handle_get_device_state,
            callback_group=self._action_group,
        )
        for capability in sorted(scenario.operations):
            self._create_action_server(capability)
        self.create_timer(1.0, self._publish_heartbeat)

        self._adapter.state_publisher.transition(DeviceState.CONNECTING)
        self._adapter.mark_ready()
        self.get_logger().info(
            f"Mock '{scenario.device_kind}' adapter for "
            f"'{scenario.component_instance_id}' is READY with "
            f"{sorted(scenario.operations)}."
        )

    def close_bridge(self) -> None:
        """Stop the asyncio bridge thread during shutdown."""

        self._bridge.close()

    def _load_scenario(self) -> DeviceScenario:
        scenario_json = str(self.get_parameter("scenario_json").value)
        try:
            if scenario_json.strip():
                return parse_device_scenario(json.loads(scenario_json), where="scenario_json")
            scenario_file = str(self.get_parameter("scenario_file").value)
            scenarios = load_scenario_file(Path(scenario_file))
            scenario = scenarios.get(self.get_name())
            if scenario is None:
                raise ScenarioConfigError(
                    f"scenario file '{scenario_file}' has no entry for node '{self.get_name()}'"
                )
            return scenario
        except (OSError, ScenarioConfigError, json.JSONDecodeError) as error:
            self.get_logger().fatal(f"Invalid mock scenario configuration: {error}")
            raise RuntimeError(f"invalid mock scenario configuration: {error}") from error

    def _create_action_server(self, capability: str) -> None:
        action_type = _ACTION_TYPES.get(capability, ExecuteSkill)
        endpoint = capability.split(".")[-1]
        self._action_servers.append(
            ActionServer(
                self,
                action_type,
                f"~/{endpoint}",
                execute_callback=lambda handle: self._execute(capability, handle),
                goal_callback=lambda goal: self._accept_goal(capability, goal),
                cancel_callback=self._cancel_goal,
                callback_group=self._action_group,
            )
        )

    def _accept_goal(self, capability: str, goal: Any) -> GoalResponse:
        command_id = str(getattr(goal, "command_id", ""))
        try:
            validate_uuid(command_id, field_name="command_id")
        except ValueError:
            self.get_logger().warning(f"Rejecting goal with invalid command_id '{command_id}'.")
            return GoalResponse.REJECT
        if hasattr(goal, "skill_id") and goal.skill_id != capability:
            self.get_logger().warning(
                f"Rejecting skill '{goal.skill_id}' on a '{capability}' endpoint."
            )
            return GoalResponse.REJECT
        timeout = getattr(goal, "timeout", None)
        if timeout is None or _duration_seconds(timeout) <= 0.0:
            self.get_logger().warning("Rejecting goal without a positive timeout.")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_goal(self, goal_handle: Any) -> CancelResponse:
        command_id = self._commands.get(bytes(goal_handle.goal_id.uuid))
        if command_id is None:
            return CancelResponse.REJECT
        self._bridge.cancel_command(self._adapter, command_id)
        return CancelResponse.ACCEPT

    def _execute(self, capability: str, goal_handle: Any) -> Any:
        goal = goal_handle.request
        command = CapabilityCommand(
            command_id=goal.command_id,
            trace_id=goal.command_id,
            capability=capability,
            input_payload_json=json.dumps(self._payload(capability, goal), sort_keys=True),
            timeout=timedelta(seconds=_duration_seconds(goal.timeout)),
        )
        key = bytes(goal_handle.goal_id.uuid)
        self._commands[key] = command.command_id
        feedback_type = _ACTION_TYPES.get(capability, ExecuteSkill).Feedback
        self._publish_feedback(goal_handle, feedback_type(), "BUSY", 0.0, "Mock operation started.")
        try:
            result = self._bridge.submit(self._adapter.execute(command)).result()
        finally:
            self._commands.pop(key, None)
        self._publish_feedback(goal_handle, feedback_type(), "DONE", 1.0, result.result_message)
        self._finish_goal(goal_handle, result)
        return self._action_result(capability, result)

    def _payload(self, capability: str, goal: Any) -> dict[str, Any]:
        if "locate_object" in capability:
            return {
                "object_type": goal.object_type,
                "profile_id": goal.profile_id,
                "region_of_interest": _json_object(goal.region_of_interest_json),
            }
        if "inspect_object" in capability:
            return {
                "inspection_profile": goal.inspection_profile,
                "expected": _json_object(goal.expected_json),
            }
        if "execute_cycle" in capability:
            return {
                "program_id": goal.program_id,
                "variable_data": _json_object(goal.variable_data_json),
                "recipe_id": goal.recipe_id,
                "recipe_version": int(goal.recipe_version),
            }
        if capability.endswith(".select_program"):
            return {
                "program_id": goal.program_id,
                "variable_data": _json_object(goal.variable_data_json),
            }
        return _json_object(goal.input_payload_json)

    def _finish_goal(self, goal_handle: Any, result: CommandResult) -> None:
        if result.result_code == "sdk.command.cancelled":
            goal_handle.canceled()
        elif result.success:
            goal_handle.succeed()
        else:
            goal_handle.abort()

    def _action_result(self, capability: str, result: CommandResult) -> Any:
        output = json.loads(result.output_payload_json)
        if "locate_object" in capability:
            action_result = LocateObject.Result()
            action_result.estimates = [_pose_estimate(item) for item in output.get("estimates", [])]
        elif "inspect_object" in capability:
            action_result = InspectObject.Result()
            action_result.accepted = bool(output.get("accepted", False))
            action_result.measurements_json = json.dumps(output.get("measurements", {}))
            action_result.evidence_uri = str(output.get("evidence_uri", ""))
        elif "execute_cycle" in capability:
            action_result = ExecuteProcess.Result()
            action_result.process_data_json = result.output_payload_json
            action_result.outcome_certain = result.outcome_certain
        else:
            action_result = ExecuteSkill.Result()
            action_result.output_payload_json = result.output_payload_json
        action_result.success = result.success
        action_result.result_code = result.result_code
        action_result.result_message = result.result_message
        return action_result

    def _publish_feedback(
        self, goal_handle: Any, feedback_message: Any, phase: str, progress: float, message: str
    ) -> None:
        if hasattr(feedback_message, "phase"):
            feedback_message.phase = phase
        if hasattr(feedback_message, "progress"):
            feedback_message.progress = float(progress)
        if hasattr(feedback_message, "message"):
            feedback_message.message = message
        goal_handle.publish_feedback(feedback_message)

    def _handle_get_device_state(self, request: Any, response: Any) -> Any:
        snapshot = self._adapter.state_publisher.snapshot
        if request.component_instance_id not in {"", snapshot.component_instance_id}:
            response.success = False
            response.result_code = "mock.state.unknown_instance"
            return response
        response.success = True
        response.result_code = "mock.state.reported"
        state = response.state
        timestamp = snapshot.heartbeat_at
        state.header.stamp.sec = int(timestamp.timestamp())
        state.header.stamp.nanosec = timestamp.microsecond * 1_000
        state.component_instance_id = snapshot.component_instance_id
        state.state = snapshot.state.value
        state.ready = snapshot.ready
        state.busy = snapshot.busy
        state.faulted = snapshot.fault is not None
        state.active_command_id = snapshot.active_command_id or ""
        state.fault_code = snapshot.fault.code if snapshot.fault is not None else ""
        state.fault_message = snapshot.fault.message if snapshot.fault is not None else ""
        state.details_json = json.dumps(snapshot.details, sort_keys=True)
        return response

    def _publish_heartbeat(self) -> None:
        self._state_edge.publish(self._adapter.state_publisher.snapshot)


def _json_object(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    decoded = json.loads(raw)
    return decoded if isinstance(decoded, dict) else {}


def _duration_seconds(duration: Any) -> float:
    return float(duration.sec) + float(duration.nanosec) / 1_000_000_000.0


def _pose_estimate(data: dict[str, Any]) -> Any:
    message = PoseEstimate()
    pose = PoseStamped()
    pose.header.frame_id = str(data.get("source_frame", ""))
    values = data.get("pose", {})
    pose.pose.position.x = float(values.get("x", 0.0))
    pose.pose.position.y = float(values.get("y", 0.0))
    pose.pose.position.z = float(values.get("z", 0.0))
    pose.pose.orientation.x = float(values.get("qx", 0.0))
    pose.pose.orientation.y = float(values.get("qy", 0.0))
    pose.pose.orientation.z = float(values.get("qz", 0.0))
    pose.pose.orientation.w = float(values.get("qw", 1.0))
    message.pose = pose
    message.confidence = float(data.get("confidence", 0.0))
    message.object_id = str(data.get("object_id", ""))
    message.source_frame = str(data.get("source_frame", ""))
    message.covariance_json = "[]"
    message.metadata_json = json.dumps(data.get("metadata", {}), sort_keys=True)
    return message


def main() -> None:
    """Run one mock device node under a multi-threaded executor."""

    rclpy.init()
    node = MockDeviceNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.close_bridge()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
