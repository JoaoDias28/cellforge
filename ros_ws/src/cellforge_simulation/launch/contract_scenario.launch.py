"""Launch Task 018 control with the complete Task 009 L0 mock cell."""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    mock_launch = (
        get_package_share_directory("cellforge_mock_adapters") + "/launch/mock_cell.launch.py"
    )
    return LaunchDescription(
        [
            Node(
                package="cellforge_simulation",
                executable="simulation_bridge",
                name="cellforge_simulation_bridge",
                output="screen",
            ),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(mock_launch)),
        ]
    )
