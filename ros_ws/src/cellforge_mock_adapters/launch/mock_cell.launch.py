"""Launch the complete L0 mock cell for the pen-engraving reference cell.

Starts one mock adapter node per reference-cell device capability endpoint. Each node loads its
own validated section of ``config/mock_cell_scenarios.json`` (keyed by node name), so faults and
timing are selected purely by scenario configuration. Requires ROS 2 Jazzy with the workspace
built and sourced; no Isaac Sim or hardware is needed.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

MOCK_CELL_NODES = [
    "mock_robot",
    "mock_gripper",
    "mock_fixture",
    "mock_vision_locator",
    "mock_inspection",
    "mock_laser",
]


def generate_launch_description() -> LaunchDescription:
    scenario_file = (
        Path(get_package_share_directory("cellforge_mock_adapters"))
        / "config"
        / "mock_cell_scenarios.json"
    )
    return LaunchDescription(
        [
            Node(
                package="cellforge_mock_adapters",
                executable="mock_device_node",
                name=node_name,
                parameters=[{"scenario_file": str(scenario_file)}],
            )
            for node_name in MOCK_CELL_NODES
        ]
    )
