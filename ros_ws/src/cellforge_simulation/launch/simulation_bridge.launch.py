"""Launch the CPU-only L0 scenario-control bridge for contract adapters."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            Node(
                package="cellforge_simulation",
                executable="simulation_bridge",
                name="cellforge_simulation_bridge",
                output="screen",
            )
        ]
    )
