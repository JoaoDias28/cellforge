"""Map Task 020 planner-neutral commands to the generated Task 019 ROS actions."""

from __future__ import annotations

from typing import Any

from cellforge_interfaces.action import ExecuteManipulation, MoveToPose
from geometry_msgs.msg import PoseStamped

from cellforge_simulation.physical import MotionCommand, PenPose, PhysicalSimulationError


class PenMotionGoalFactory:
    """Transport mapping only; behavior-tree sequencing and MoveIt planning stay external."""

    def __init__(self, component_instance_id: str = "robot-001") -> None:
        if not component_instance_id:
            raise PhysicalSimulationError("physical.motion.component_missing: instance ID is blank")
        self._component_instance_id = component_instance_id

    @staticmethod
    def _pose(pose: PenPose, frame_id: str) -> PoseStamped:
        if not frame_id:
            raise PhysicalSimulationError("physical.motion.frame_missing: frame ID is blank")
        message = PoseStamped()
        message.header.frame_id = frame_id
        message.pose.position.x = pose.x_mm / 1000.0
        message.pose.position.y = pose.y_mm / 1000.0
        message.pose.position.z = pose.z_mm / 1000.0
        message.pose.orientation.w = 1.0
        return message

    @staticmethod
    def _timeout(message: Any, seconds: int = 30) -> None:
        message.timeout.sec = seconds
        message.timeout.nanosec = 0

    def create_goal(
        self,
        command: MotionCommand,
        pose: PenPose,
        *,
        command_id: str,
        trace_id: str,
        frame_id: str = "world",
    ) -> Any:
        if not command_id or not trace_id:
            raise PhysicalSimulationError(
                "physical.motion.identity_missing: command_id and trace_id are required"
            )
        if command.operation == "process_safe":
            goal = MoveToPose.Goal()
            goal.component_instance_id = self._component_instance_id
            goal.command_id = command_id
            goal.trace_id = trace_id
            goal.named_pose = command.named_safe_pose
            goal.plan_only = command.plan_only
            goal.max_velocity_scaling = 0.5
            goal.max_acceleration_scaling = 0.5
            self._timeout(goal)
            return goal
        if command.operation not in {"pick", "load", "unload"}:
            raise PhysicalSimulationError(
                f"physical.motion.operation_invalid: unsupported '{command.operation}'"
            )
        goal = ExecuteManipulation.Goal()
        goal.component_instance_id = self._component_instance_id
        goal.command_id = command_id
        goal.trace_id = trace_id
        goal.operation = command.operation
        goal.object_id = command.object_id
        goal.object_pose = self._pose(pose, frame_id)
        goal.tool_frame = command.tool_frame
        goal.named_safe_pose = command.named_safe_pose
        goal.plan_only = command.plan_only
        goal.max_velocity_scaling = 0.5
        goal.max_acceleration_scaling = 0.5
        self._timeout(goal)
        return goal
