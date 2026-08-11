"""State aggregator ROS 2 node that composes cell health from devices and safety.

This node subscribes to per-device ``DeviceState`` topics, a ``SafetyState`` topic, and publishes
an aggregated ``CellState`` message. It detects stale devices (heartbeat timeout) and reflects
degraded readiness. The node never implements or bypasses any safety logic; the safety state it
reads is informational and used only to refuse work.
"""

from __future__ import annotations

import os
from typing import Any

import rclpy
from cellforge_interfaces.msg import (
    CellState as RosCellState,
)
from cellforge_interfaces.msg import (
    DeviceState as RosDeviceState,
)
from cellforge_interfaces.msg import (
    SafetyState as RosSafetyState,
)
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node
from std_msgs.msg import Header

from cellforge_state_trace.state_logic import (
    CELL_STATE_OFFLINE,
    DeviceStateEntry,
    SafetyStatusEntry,
    compute_top_level_cell_state,
    evaluate_required_devices,
)


class StateAggregatorNode(Node):  # type: ignore[misc]
    """Aggregate per-device and safety state into a canonical ``CellState`` publication."""

    def __init__(
        self,
        *,
        node_name: str = "state_aggregator",
        parameter_overrides: list[Any] | None = None,
    ) -> None:
        super().__init__(node_name, parameter_overrides=parameter_overrides)
        self.declare_parameter("cell_id", "")
        self.declare_parameter("bundle_id", os.environ.get("CELLFORGE_BUNDLE_ID", ""))
        self.declare_parameter("device_topics", [""])
        self.declare_parameter("required_device_ids", [""])
        self.declare_parameter("safety_topic", "/safety/state")
        self.declare_parameter("supervisor_state_topic", "/cell/supervisor_state")
        self.declare_parameter("safety_timeout_s", 3.0)
        self.declare_parameter("publish_rate_hz", 1.0)

        self._cell_id = str(self.get_parameter("cell_id").value)
        self._bundle_id = str(self.get_parameter("bundle_id").value)
        safety_timeout = float(self.get_parameter("safety_timeout_s").value)
        self._safety_entry = SafetyStatusEntry(timeout_s=safety_timeout)
        self._supervisor_state: RosCellState | None = None

        self._required_ids: set[str] = set(
            str(v) for v in self.get_parameter("required_device_ids").value if str(v)
        )

        self._devices: dict[str, DeviceStateEntry] = {}
        for instance_id in self._required_ids:
            self._devices[instance_id] = DeviceStateEntry(component_instance_id=instance_id)

        self._group = MutuallyExclusiveCallbackGroup()

        device_topics = [str(t) for t in self.get_parameter("device_topics").value if str(t)]
        self._subs: list[Any] = []
        for topic in device_topics:
            self._subs.append(
                self.create_subscription(
                    RosDeviceState,
                    topic,
                    self._on_device_state,
                    10,
                    callback_group=self._group,
                )
            )

        safety_topic = str(self.get_parameter("safety_topic").value)
        self.create_subscription(
            RosSafetyState,
            safety_topic,
            self._on_safety_state,
            10,
            callback_group=self._group,
        )
        self.create_subscription(
            RosCellState,
            str(self.get_parameter("supervisor_state_topic").value),
            self._on_supervisor_state,
            10,
            callback_group=self._group,
        )

        self._cell_pub = self.create_publisher(RosCellState, "/cell/state", 10)
        rate = float(self.get_parameter("publish_rate_hz").value)
        self.create_timer(1.0 / max(rate, 0.1), self._publish_cell_state)

        self.get_logger().info(
            f"State aggregator started — subscribed to {len(device_topics)} device topics, "
            f"safety on '{safety_topic}' (timeout {safety_timeout:.1f}s), requiring "
            f"{len(self._required_ids)} devices."
        )

    def _on_device_state(self, message: RosDeviceState) -> None:
        instance_id = message.component_instance_id
        if instance_id not in self._devices:
            self._devices[instance_id] = DeviceStateEntry(component_instance_id=instance_id)
        self._devices[instance_id].update(message)

    def _on_safety_state(self, message: RosSafetyState) -> None:
        self._safety_entry.update(message.healthy)

    def _on_supervisor_state(self, message: RosCellState) -> None:
        self._supervisor_state = message

    def _publish_cell_state(self) -> None:
        ros_devices: list[RosDeviceState] = []
        for entry in self._devices.values():
            ros_device = RosDeviceState()
            timestamp = entry.heartbeat_at
            ros_device.header.stamp.sec = int(timestamp.timestamp())
            ros_device.header.stamp.nanosec = timestamp.microsecond * 1_000
            ros_device.component_instance_id = entry.component_instance_id
            ros_device.state = CELL_STATE_OFFLINE if entry.stale else entry.state
            ros_device.ready = entry.ready and not entry.stale
            ros_device.busy = entry.busy and not entry.stale
            ros_device.faulted = entry.faulted or entry.stale
            ros_device.active_command_id = "" if entry.stale else entry.active_command_id
            ros_device.fault_code = (
                "sdk.heartbeat.stale_device" if entry.stale else entry.fault_code
            )
            ros_device.fault_message = (
                f"Device '{entry.component_instance_id}' heartbeat timeout"
                if entry.stale
                else entry.fault_message
            )
            ros_device.details_json = entry.details_json
            ros_devices.append(ros_device)

        safety_healthy = self._safety_entry.effective_healthy

        all_required_ready, any_required_stale = evaluate_required_devices(
            self._devices, self._required_ids
        )

        any_faulted = any(entry.faulted for entry in self._devices.values())
        any_busy = any(entry.busy and not entry.stale for entry in self._devices.values())
        cell_state = compute_top_level_cell_state(
            all_required_ready=all_required_ready,
            safety_healthy=safety_healthy,
            any_faulted=any_faulted,
            any_busy=any_busy,
            any_required_stale=any_required_stale,
        )
        supervisor = self._supervisor_state
        execution_states = {
            "RUNNING",
            "PAUSED",
            "RECOVERABLE_FAULT",
            "TERMINAL_FAULT",
            "MAINTENANCE",
            "STOPPING",
        }
        if supervisor is not None and supervisor.state in execution_states:
            cell_state = supervisor.state

        message = RosCellState()
        now = self.get_clock().now().to_msg()
        message.header = Header(stamp=now)
        message.cell_id = self._cell_id
        message.state = cell_state
        message.safety_healthy = safety_healthy
        message.all_required_devices_ready = all_required_ready
        message.active_job_id = str(supervisor.active_job_id) if supervisor is not None else ""
        message.active_trace_id = str(supervisor.active_trace_id) if supervisor is not None else ""
        message.bundle_id = self._bundle_id
        message.devices = ros_devices
        self._cell_pub.publish(message)


def main() -> None:
    """Run the state aggregator node."""
    rclpy.init()
    node = StateAggregatorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
