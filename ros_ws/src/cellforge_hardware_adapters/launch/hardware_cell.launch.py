"""Launch description for physical hardware device adapters."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_instance", default_value="robot-001"),
            DeclareLaunchArgument("gripper_instance", default_value="gripper-001"),
            DeclareLaunchArgument("fixture_instance", default_value="fixture-001"),
            DeclareLaunchArgument("camera_instance", default_value="camera-001"),
            DeclareLaunchArgument("laser_instance", default_value="laser-001"),
            DeclareLaunchArgument("safety_instance", default_value="safety-status-001"),
            Node(
                package="cellforge_hardware_adapters",
                executable="hardware_device_node",
                name="hardware_robot",
                parameters=[
                    {
                        "component_instance_id": LaunchConfiguration("robot_instance"),
                        "device_kind": "robot",
                        "endpoint_root": "/device/robot_001",
                        "capabilities": ["robot_motion.action.execute_trajectory"],
                    }
                ],
                output="screen",
            ),
            Node(
                package="cellforge_hardware_adapters",
                executable="hardware_device_node",
                name="hardware_gripper",
                parameters=[
                    {
                        "component_instance_id": LaunchConfiguration("gripper_instance"),
                        "device_kind": "gripper",
                        "endpoint_root": "/device/gripper_001",
                        "capabilities": ["gripper.action.open", "gripper.action.close"],
                    }
                ],
                output="screen",
            ),
            Node(
                package="cellforge_hardware_adapters",
                executable="hardware_device_node",
                name="hardware_fixture",
                parameters=[
                    {
                        "component_instance_id": LaunchConfiguration("fixture_instance"),
                        "device_kind": "fixture",
                        "endpoint_root": "/device/fixture_001",
                        "capabilities": [
                            "fixture.action.clamp",
                            "fixture.action.release",
                            "fixture.action.verify_seated",
                        ],
                    }
                ],
                output="screen",
            ),
            Node(
                package="cellforge_hardware_adapters",
                executable="hardware_device_node",
                name="hardware_camera",
                parameters=[
                    {
                        "component_instance_id": LaunchConfiguration("camera_instance"),
                        "device_kind": "camera",
                        "endpoint_root": "/device/camera_001",
                        "capabilities": [
                            "vision.action.locate_object",
                            "vision.action.inspect_object",
                        ],
                    }
                ],
                output="screen",
            ),
            Node(
                package="cellforge_hardware_adapters",
                executable="hardware_device_node",
                name="hardware_laser",
                parameters=[
                    {
                        "component_instance_id": LaunchConfiguration("laser_instance"),
                        "device_kind": "laser",
                        "endpoint_root": "/device/laser_001",
                        "capabilities": [
                            "process.action.select_program",
                            "process.action.execute_cycle",
                        ],
                    }
                ],
                output="screen",
            ),
            Node(
                package="cellforge_hardware_adapters",
                executable="hardware_safety_status_node",
                name="hardware_safety_status",
                parameters=[
                    {
                        "component_instance_id": LaunchConfiguration("safety_instance"),
                        "healthy": True,
                    }
                ],
                output="screen",
            ),
        ]
    )
