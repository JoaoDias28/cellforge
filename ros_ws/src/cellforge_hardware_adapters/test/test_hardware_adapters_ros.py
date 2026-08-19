"""ROS 2 node tests for hardware adapters."""

from __future__ import annotations

import pytest
import rclpy
from cellforge_hardware_adapters.ros_node import HardwareDeviceNode, HardwareSafetyStatusNode
from cellforge_interfaces.srv import GetDeviceState


@pytest.fixture(scope="module")
def ros_context():
    rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def test_hardware_device_nodes_lifecycle(ros_context):
    kinds = [
        ("robot-001", "robot", ["robot_motion.action.execute_trajectory"]),
        ("gripper-001", "gripper", ["gripper.action.open", "gripper.action.close"]),
        ("fixture-001", "fixture", ["fixture.action.clamp", "fixture.action.verify_seated"]),
        ("camera-001", "camera", ["vision.action.locate_object", "vision.action.inspect_object"]),
        ("laser-001", "laser", ["process.action.select_program", "process.action.execute_cycle"]),
    ]

    for comp_id, kind_str, caps in kinds:
        node = HardwareDeviceNode(
            node_name=f"test_hw_{kind_str}",
            parameter_overrides=[
                rclpy.parameter.Parameter("component_instance_id", value=comp_id),
                rclpy.parameter.Parameter("device_kind", value=kind_str),
                rclpy.parameter.Parameter("capabilities", value=caps),
                rclpy.parameter.Parameter("endpoint_root", value=f"/test/device/{kind_str}"),
            ],
        )

        req = GetDeviceState.Request()
        req.component_instance_id = comp_id
        resp = GetDeviceState.Response()
        resp = node._handle_get_device_state(req, resp)

        assert resp.success is True
        assert resp.result_code == "hardware.state.reported"
        assert resp.state.component_instance_id == comp_id
        assert resp.state.state == "READY"
        assert resp.state.ready is True

        node.close_bridge()
        node.destroy_node()


def test_hardware_safety_status_node(ros_context):
    node = HardwareSafetyStatusNode(
        parameter_overrides=[
            rclpy.parameter.Parameter("component_instance_id", value="safety-status-001"),
            rclpy.parameter.Parameter("healthy", value=True),
        ]
    )
    assert node._healthy is True
    node.destroy_node()
