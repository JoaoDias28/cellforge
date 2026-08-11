"""Launch the complete L0 mock cell for the pen-engraving reference cell.

Starts one mock adapter node per reference-cell device capability endpoint. Each node loads its
own validated section of ``config/mock_cell_scenarios.json`` (keyed by node name), so faults and
timing are selected purely by scenario configuration. Requires ROS 2 Jazzy with the workspace
built and sourced; no Isaac Sim or hardware is needed.
"""

import json
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

REFERENCE_NODES = (
    "mock_fixture",
    "mock_gripper",
    "mock_inspection",
    "mock_laser",
    "mock_robot",
    "mock_vision_locator",
)


def generate_launch_description() -> LaunchDescription:
    scenario_file = (
        Path(get_package_share_directory("cellforge_mock_adapters"))
        / "config"
        / "mock_cell_scenarios.json"
    )
    document = json.loads(scenario_file.read_text(encoding="utf-8"))
    nodes = []
    if tuple(sorted(document["nodes"])) != REFERENCE_NODES:
        raise RuntimeError("Mock-cell scenario does not contain the exact reference node set.")
    for node_name in REFERENCE_NODES:
        scenario = document["nodes"][node_name]
        nodes.append(
            Node(
                package="cellforge_mock_adapters",
                executable="mock_device_node",
                name=node_name,
                parameters=[
                    {
                        "scenario_file": str(scenario_file),
                        "endpoint_root": (
                            f"/device/{scenario['component_instance_id'].replace('-', '_')}"
                        ),
                    }
                ],
            )
        )
    nodes.append(
        Node(
            package="cellforge_mock_adapters",
            executable="mock_safety_status_node",
            parameters=[{"component_instance_id": "safety-status-001", "healthy": True}],
        )
    )
    return LaunchDescription(nodes)
