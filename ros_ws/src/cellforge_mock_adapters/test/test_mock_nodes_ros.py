"""Colcon smoke test verifying the mock node starts and accepts a command.

Requires ROS 2 Jazzy with the workspace built and sourced. This test is exercised only when
``colcon test`` runs on a Jazzy host; repository-level unit tests cover the pure core without ROS.
"""

import json
import threading
import time

import pytest
import rclpy
from cellforge_interfaces.action import ExecuteSkill
from cellforge_interfaces.srv import GetDeviceState
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.parameter import Parameter


def _shutdown() -> None:
    if rclpy.ok():
        rclpy.shutdown()


def _wait_for_future(future: object, *, timeout_sec: float) -> object:
    deadline = time.monotonic() + timeout_sec
    while not future.done() and time.monotonic() < deadline:  # type: ignore[attr-defined]
        time.sleep(0.01)
    assert future.done(), "ROS future did not complete before timeout"  # type: ignore[attr-defined]
    result = future.result()  # type: ignore[attr-defined]
    assert result is not None
    return result


@pytest.fixture(scope="module", autouse=True)
def _ros_context() -> None:
    rclpy.init()
    yield
    _shutdown()


def test_mock_gripper_nominal_open_and_get_state() -> None:
    """Start a mock gripper node, open the jaw, and query device state."""

    scenario = json.dumps(
        {
            "component_instance_id": "gripper-test-001",
            "device_kind": "gripper",
            "restart": "ready",
            "operations": {
                "gripper.action.open": {"duration_seconds": 0.01, "fault": None},
                "gripper.action.close": {"duration_seconds": 0.01, "fault": None},
            },
            "device": {"jaw_initial": "closed"},
        }
    )
    from cellforge_mock_adapters.ros_node import MockDeviceNode

    node = MockDeviceNode(
        parameter_overrides=[
            Parameter("scenario_json", value=scenario),
            Parameter("scenario_file", value=""),
        ],
        node_name="mock_gripper_test",
    )
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    time.sleep(0.2)

    try:
        client = ActionClient(node, ExecuteSkill, "/mock_gripper_test/open")
        assert client.wait_for_server(timeout_sec=2.0), "action server not available"

        goal = ExecuteSkill.Goal()
        goal.command_id = "11111111-1111-1111-1111-111111111111"
        goal.skill_id = "gripper.action.open"
        goal.input_payload_json = "{}"
        goal.timeout.sec = 5
        goal.timeout.nanosec = 0

        future = client.send_goal_async(goal)
        goal_handle = _wait_for_future(future, timeout_sec=2.0)
        assert goal_handle.accepted, "goal was rejected"
        result_future = goal_handle.get_result_async()
        result = _wait_for_future(result_future, timeout_sec=2.0).result
        assert result.success
        assert result.result_code == "gripper.action.open.completed"

        state_client = node.create_client(GetDeviceState, "/mock_gripper_test/get_state")
        assert state_client.wait_for_service(timeout_sec=2.0), "state service not available"

        req = GetDeviceState.Request()
        req.component_instance_id = ""
        state_future = state_client.call_async(req)
        state_response = _wait_for_future(state_future, timeout_sec=2.0)
        assert state_response.success
        assert state_response.state.ready
    finally:
        node.close_bridge()
        executor.shutdown()
        spin_thread.join(timeout=1.0)
        node.destroy_node()
