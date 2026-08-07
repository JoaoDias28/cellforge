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

pytestmark = pytest.mark.skipif(
    not rclpy.ok() if hasattr(rclpy, "ok") else True,
    reason="requires a running ROS 2 Jazzy domain",
)


def _shutdown() -> None:
    if rclpy.ok():
        rclpy.shutdown()


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
            ("scenario_json", scenario),
            ("scenario_file", ""),
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
        rclpy.spin_until_future_complete(node, future, timeout_sec=2.0)
        goal_handle = future.result()
        assert goal_handle.accepted, "goal was rejected"
        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(node, result_future, timeout_sec=2.0)
        result = result_future.result().result
        assert result.success
        assert result.result_code == "gripper.action.open.completed"

        state_client = node.create_client(GetDeviceState, "/mock_gripper_test/get_state")
        assert state_client.wait_for_service(timeout_sec=2.0), "state service not available"

        req = GetDeviceState.Request()
        req.component_instance_id = ""
        state_future = state_client.call_async(req)
        rclpy.spin_until_future_complete(node, state_future, timeout_sec=2.0)
        state_response = state_future.result()
        assert state_response.success
        assert state_response.state.ready
    finally:
        node.close_bridge()
        executor.shutdown()
        spin_thread.join(timeout=1.0)
        node.destroy_node()
