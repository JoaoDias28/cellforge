"""Durable event recorder ROS 2 node.

Subscribes to the canonical ``cellforge_interfaces/JobEvent`` topic, converts each message
losslessly to the durable ``TraceEvent`` representation, validates correlation identifiers,
and persists through a ``TraceEventStore``. Sequence assignment is delegated to the store;
the recorder does not acknowledge a durable write until the store's ``record()`` call returns.

This component is generic — it consumes any ``JobEvent`` regardless of origin.  Task 011
supervisor and later producers will emit events here; this node does not implement any
behavior-tree logic.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import rclpy
from cellforge_interfaces.msg import (
    JobEvent as RosJobEvent,
)
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node

from cellforge_state_trace.correlation import CorrelationError, validate_correlation
from cellforge_state_trace.trace_store import SqliteTraceEventStore, TraceEvent, TraceEventStore


class DurableEventRecorderNode(Node):  # type: ignore[misc]
    """Subscribe to ``JobEvent`` and persist every message durably."""

    def __init__(self) -> None:
        super().__init__("durable_event_recorder")
        self.declare_parameter("db_path", "")
        self.declare_parameter("event_topic", "/events/job")

        db_path = str(self.get_parameter("db_path").value)
        if not db_path.strip():
            db_path = str(Path.home() / ".cellforge" / "trace" / "events.db")
            self.get_logger().warn(f"db_path not set; using default '{db_path}'")

        self._store: TraceEventStore = SqliteTraceEventStore(Path(db_path))
        self._group = MutuallyExclusiveCallbackGroup()

        topic = str(self.get_parameter("event_topic").value)
        self.create_subscription(
            RosJobEvent,
            topic,
            self._on_job_event,
            10,
            callback_group=self._group,
        )

        self.get_logger().info(
            f"Durable recorder started — listening on '{topic}', store at '{db_path}'."
        )

    def _on_job_event(self, message: RosJobEvent) -> None:
        try:
            validate_correlation(
                trace_id=message.trace_id,
                job_id=message.job_id,
                command_id=message.command_id,
                event_type=message.event_type,
            )
        except CorrelationError as exc:
            self.get_logger().error(f"Correlation validation failed, event dropped: {exc}")
            return

        try:
            payload = json.loads(message.payload_json) if message.payload_json.strip() else {}
        except json.JSONDecodeError:
            self.get_logger().error(
                f"Invalid payload_json for trace '{message.trace_id}', event dropped."
            )
            return
        if not isinstance(payload, dict):
            self.get_logger().error(
                f"payload_json must be a JSON object for trace '{message.trace_id}', event dropped."
            )
            return

        sec = message.header.stamp.sec
        nanosec = message.header.stamp.nanosec
        timestamp = datetime.fromtimestamp(sec + nanosec / 1_000_000_000.0, tz=UTC)

        trace_event = TraceEvent(
            trace_id=message.trace_id,
            job_id=message.job_id,
            cell_id=message.cell_id,
            component_instance_id=message.component_instance_id,
            command_id=message.command_id,
            sequence=0,
            event_type=message.event_type,
            severity=message.severity,
            payload=payload,
            timestamp=timestamp,
        )

        try:
            seq = self._store.record(trace_event)
        except Exception as exc:
            self.get_logger().error(
                f"Failed to persist event for trace '{message.trace_id}': {exc}"
            )
            return

        self.get_logger().debug(
            f"Recorded event seq={seq} type='{message.event_type}' trace='{message.trace_id}'"
        )

    def close_store(self) -> None:
        self._store.close()

    def destroy_node(self) -> None:
        self._store.close()
        super().destroy_node()


def main() -> None:
    """Run the durable event recorder node."""
    rclpy.init()
    node = DurableEventRecorderNode()
    try:
        rclpy.spin(node)
    finally:
        node.close_store()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
