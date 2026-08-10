from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description() -> LaunchDescription:
    moveit_config = (
        MoveItConfigsBuilder("reference_robot", package_name="cellforge_motion")
        .robot_description(file_path="config/reference_robot.urdf.xacro")
        .robot_description_semantic(file_path="config/reference_robot.srdf")
        .robot_description_kinematics(file_path="config/kinematics.yaml")
        .joint_limits(file_path="config/joint_limits.yaml")
        .trajectory_execution(file_path="config/moveit_controllers.yaml")
        .planning_pipelines(pipelines=["ompl"])
        .to_moveit_configs()
    )
    controllers = str(
        Path(get_package_share_directory("cellforge_motion")) / "config" / "ros2_controllers.yaml"
    )
    return LaunchDescription(
        [
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[moveit_config.robot_description],
            ),
            Node(
                package="controller_manager",
                executable="ros2_control_node",
                parameters=[moveit_config.robot_description, controllers],
                output="screen",
            ),
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=["joint_state_broadcaster"],
            ),
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=["reference_robot_controller"],
            ),
            Node(
                package="moveit_ros_move_group",
                executable="move_group",
                parameters=[moveit_config.to_dict()],
                output="screen",
            ),
            Node(
                package="cellforge_motion",
                executable="cellforge_motion_service",
                parameters=[moveit_config.to_dict()],
                output="screen",
            ),
        ]
    )
