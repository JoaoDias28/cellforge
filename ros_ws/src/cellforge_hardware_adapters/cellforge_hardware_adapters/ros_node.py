"""ROS 2 node wrapper for physical hardware device adapters."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import rclpy
from cellforge_device_sdk.adapter import BaseDeviceAdapter
from cellforge_device_sdk.models import (
    CapabilityCommand,
    CommandResult,
    DeviceStateSnapshot,
)
from cellforge_interfaces.action import (
    ExecuteProcess,
    ExecuteSkill,
    InspectObject,
    LocateObject,
)
from cellforge_interfaces.msg import (
    DeviceState as RosDeviceState,
    PoseEstimate,
    SafetyState as RosSafetyState,
)
from cellforge_interfaces.srv import GetDeviceState
from geometry_msgs.msg import PoseStamped
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node

from cellforge_hardware_adapters.devices import (
    HardwareDeviceKind,
    build_hardware_adapter,
)

_ACTION_TYPES: dict[str, Any] = {
    "robot_motion.action.execute_trajectory": ExecuteSkill,
    "gripper.action.open": ExecuteSkill,
    "gripper.action.close": ExecuteSkill,
    "fixture.action.clamp": ExecuteSkill,
    "fixture.action.release": ExecuteSkill,
    "fixture.action.verify_seated": ExecuteSkill,
    "vision.action.locate_object": LocateObject,
    "vision.action.inspect_object": InspectObject,
    "process.action.select_program": ExecuteProcess,
    "process.action.execute_cycle": ExecuteProcess,
}


class _AsyncioBridge:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="hardware-adapter-asyncio",
        )
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def close(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=1.0)


class HardwareDeviceNode(Node):
    """ROS 2 Node hosting physical device capability actions, queries, and state telemetry."""

    def __init__(
        self,
        node_name: str = "hardware_device_node",
        *,
        adapter: BaseDeviceAdapter | None = None,
        parameter_overrides: list[rclpy.parameter.Parameter] | None = None,
    ) -> None:
        super().__init__(node_name, parameter_overrides=parameter_overrides)
        self.declare_parameter("component_instance_id", "robot-001")
        self.declare_parameter("device_kind", "robot")
        self.declare_parameter("endpoint_root", "/device/robot_001")
        self.declare_parameter("capabilities", ["robot_motion.action.execute_trajectory"])

        component_id = str(self.get_parameter("component_instance_id").value)
        device_kind_str = str(self.get_parameter("device_kind").value)
        self._endpoint_root = str(self.get_parameter("endpoint_root").value)
        capabilities = list(self.get_parameter("capabilities").value)

        self._bridge = _AsyncioBridge()
        self._action_servers: list[ActionServer] = []
        self._commands: dict[str, str] = {}
        self._cb_group = ReentrantCallbackGroup()

        # Publishers
        self._state_pub = self.create_publisher(
            RosDeviceState,
            f"{self._endpoint_root}/state",
            10,
        )

        # Service
        self._state_srv = self.create_service(
            GetDeviceState,
            f"{self._endpoint_root}/get_state",
            self._handle_get_device_state,
            callback_group=self._cb_group,
        )

        # Build physical adapter
        kind = HardwareDeviceKind(device_kind_str)
        self._adapter = adapter or build_hardware_adapter(
            kind,
            component_id,
            state_sink=self._on_device_state_change,
        )

        # Initialize connection
        if hasattr(self._adapter, "connect_hardware"):
            self._bridge.submit(self._adapter.connect_hardware()).result()

        # Action Servers
        for capability in capabilities:
            action_type = _ACTION_TYPES.get(capability, ExecuteSkill)
            action_name = f"{self._endpoint_root}/{capability.split('.')[-1]}"
            server = ActionServer(
                self,
                action_type,
                action_name,
                execute_callback=self._make_execute_callback(capability),
                goal_callback=self._goal_callback,
                cancel_callback=self._cancel_callback,
                callback_group=self._cb_group,
            )
            self._action_servers.append(server)

        # Heartbeat timer
        self._timer = self.create_timer(1.0, self._publish_heartbeat)
        self.get_logger().info(
            f"Physical '{device_kind_str}' adapter for '{component_id}' ready on "
            f"{self._endpoint_root}."
        )

    def _on_device_state_change(self, snapshot: DeviceStateSnapshot) -> None:
        msg = RosDeviceState()
        msg.component_instance_id = snapshot.component_instance_id
        msg.state = snapshot.state.value
        msg.ready = snapshot.ready
        msg.busy = snapshot.busy
        msg.faulted = snapshot.fault is not None
        msg.active_command_id = snapshot.active_command_id or ""
        if snapshot.fault:
            msg.fault_code = snapshot.fault.code
            msg.fault_message = snapshot.fault.message
            msg.details_json = json.dumps(snapshot.fault.details, sort_keys=True)
        else:
            msg.details_json = json.dumps(snapshot.details, sort_keys=True)
        if hasattr(self, "_state_pub"):
            self._state_pub.publish(msg)

    def _publish_heartbeat(self) -> None:
        snapshot = self._adapter.state_publisher.snapshot
        self._on_device_state_change(snapshot)

    def _handle_get_device_state(
        self, request: GetDeviceState.Request, response: GetDeviceState.Response
    ) -> GetDeviceState.Response:
        snapshot = self._adapter.state_publisher.snapshot
        response.success = True
        response.result_code = "hardware.state.reported"
        response.state.component_instance_id = snapshot.component_instance_id
        response.state.state = snapshot.state.value
        response.state.ready = snapshot.ready
        response.state.busy = snapshot.busy
        response.state.faulted = snapshot.fault is not None
        response.state.active_command_id = snapshot.active_command_id or ""
        if snapshot.fault:
            response.state.fault_code = snapshot.fault.code
            response.state.fault_message = snapshot.fault.message
            response.state.details_json = json.dumps(snapshot.fault.details, sort_keys=True)
        else:
            response.state.details_json = json.dumps(snapshot.details, sort_keys=True)
        return response

    def _goal_callback(self, goal_request: Any) -> GoalResponse:
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle: ServerGoalHandle) -> CancelResponse:
        key = str(goal_handle.goal_id.uuid.tobytes())
        command_id = self._commands.get(key)
        if command_id:
            self._bridge.submit(self._adapter.cancel_command(command_id))
        return CancelResponse.ACCEPT

    def _make_execute_callback(self, capability: str) -> Any:
        def execute_callback(goal_handle: ServerGoalHandle) -> Any:
            return self._execute_action_goal(goal_handle, capability)

        return execute_callback

    def _execute_action_goal(self, goal_handle: ServerGoalHandle, capability: str) -> Any:
        goal = goal_handle.request
        key = str(goal_handle.goal_id.uuid.tobytes())

        # Extract payload and IDs from goal
        command_id = getattr(goal, "command_id", "") or str(goal_handle.goal_id)
        trace_id = getattr(goal, "trace_id", "") or "trace-hw"
        payload_json = self._extract_payload_json(goal, capability)

        command = CapabilityCommand(
            command_id=command_id,
            trace_id=trace_id,
            capability=capability,
            input_payload_json=payload_json,
        )
        self._commands[key] = command.command_id
        feedback_type = _ACTION_TYPES.get(capability, ExecuteSkill).Feedback
        self._publish_feedback(
            goal_handle,
            feedback_type(),
            "BUSY",
            0.0,
            "Hardware operation started.",
        )
        try:
            result = self._bridge.submit(self._adapter.execute(command)).result()
        finally:
            self._commands.pop(key, None)

        action_result = _ACTION_TYPES.get(capability, ExecuteSkill).Result()
        self._populate_action_result(action_result, result, capability)

        if result.success:
            goal_handle.succeed()
        else:
            goal_handle.abort()
        return action_result

    def _extract_payload_json(self, goal: Any, capability: str) -> str:
        if hasattr(goal, "input_payload_json") and goal.input_payload_json:
            return goal.input_payload_json
        if hasattr(goal, "program_id"):
            data = {
                "program_id": goal.program_id,
                "variable_data": (
                    json.loads(goal.variable_data_json) if goal.variable_data_json else {}
                ),
            }
            return json.dumps(data)
        if hasattr(goal, "object_type"):
            return json.dumps(
                {
                    "object_type": goal.object_type,
                    "profile_id": getattr(goal, "profile_id", "default"),
                }
            )
        if hasattr(goal, "inspection_profile"):
            return json.dumps(
                {
                    "inspection_profile": goal.inspection_profile,
                    "expected": (
                        json.loads(goal.expected_json) if getattr(goal, "expected_json", "") else {}
                    ),
                }
            )
        return "{}"

    def _publish_feedback(
        self, goal_handle: ServerGoalHandle, feedback: Any, state: str, progress: float, msg: str
    ) -> None:
        if hasattr(feedback, "phase"):
            feedback.phase = state
        if hasattr(feedback, "state"):
            feedback.state = state
        if hasattr(feedback, "progress"):
            feedback.progress = progress
        if hasattr(feedback, "message"):
            feedback.message = msg
        goal_handle.publish_feedback(feedback)

    def _populate_action_result(
        self, action_result: Any, result: CommandResult, capability: str
    ) -> None:
        if hasattr(action_result, "success"):
            action_result.success = result.success
        if hasattr(action_result, "result_code"):
            action_result.result_code = result.result_code
        if hasattr(action_result, "result_message"):
            action_result.result_message = result.result_message
        if hasattr(action_result, "output_payload_json"):
            action_result.output_payload_json = result.output_payload_json
        if hasattr(action_result, "outcome_certain"):
            action_result.outcome_certain = result.outcome_certain

        # Fill typed action fields
        if hasattr(action_result, "estimates"):
            try:
                out = json.loads(result.output_payload_json)
                estimates_list = []
                for est in out.get("estimates", []):
                    pe = PoseEstimate()
                    pe.object_id = est.get("object_id", "object")
                    pe.confidence = float(est.get("confidence", 1.0))
                    pe.source_frame = est.get("source_frame", "camera_optical")
                    pe.metadata_json = json.dumps(est.get("metadata", {}))

                    ps = PoseStamped()
                    ps.header.frame_id = pe.source_frame
                    p = est.get("pose", {})
                    ps.pose.position.x = float(p.get("x", 0.0))
                    ps.pose.position.y = float(p.get("y", 0.0))
                    ps.pose.position.z = float(p.get("z", 0.0))
                    ps.pose.orientation.x = float(p.get("qx", 0.0))
                    ps.pose.orientation.y = float(p.get("qy", 0.0))
                    ps.pose.orientation.z = float(p.get("qz", 0.0))
                    ps.pose.orientation.w = float(p.get("qw", 1.0))
                    pe.pose = ps
                    estimates_list.append(pe)
                action_result.estimates = estimates_list
            except Exception:
                pass

    def close_bridge(self) -> None:
        self._bridge.close()


class HardwareSafetyStatusNode(Node):
    """Read-only ROS 2 Node publishing external rated safety hardware state (ADR 0007)."""

    def __init__(
        self,
        node_name: str = "hardware_safety_status_node",
        *,
        parameter_overrides: list[rclpy.parameter.Parameter] | None = None,
    ) -> None:
        super().__init__(node_name, parameter_overrides=parameter_overrides)
        self.declare_parameter("component_instance_id", "safety-status-001")
        self.declare_parameter("healthy", True)

        self._component_id = str(self.get_parameter("component_instance_id").value)
        self._healthy = bool(self.get_parameter("healthy").value)

        self._pub = self.create_publisher(RosSafetyState, "/safety/state", 10)
        self._timer = self.create_timer(0.05, self._publish_safety_state)
        self.get_logger().info(
            f"Hardware safety status monitor active for '{self._component_id}' "
            f"(healthy={self._healthy})."
        )

    def _publish_safety_state(self) -> None:
        safety = RosSafetyState()
        safety.component_instance_id = self._component_id
        safety.safe_motion_permitted = self._healthy
        safety.laser_emission_permitted = self._healthy
        safety.e_stop_active = not self._healthy
        safety.guard_interlock_open = not self._healthy
        safety.reset_required = not self._healthy
        safety.details_json = json.dumps(
            {
                "source": "Rated Safety Hardware Relay Monitor",
                "safety_claim": "independent_hardware",
            },
            sort_keys=True,
        )
        self._pub.publish(safety)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = HardwareDeviceNode()
    try:
        rclpy.spin(node)
    finally:
        node.close_bridge()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main_safety(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = HardwareSafetyStatusNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
