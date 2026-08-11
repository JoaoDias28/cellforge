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

from pathlib import Path
from typing import Any

import rclpy
from cellforge_interfaces.msg import (
    JobEvent as RosJobEvent,
)
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node

from cellforge_state_trace.correlation import CorrelationError, validate_correlation
from cellforge_state_trace.trace_store import (
    SqliteTraceEventStore,
    TraceEventStore,
    convert_job_event_to_trace_event,
)


class DurableEventRecorderNode(Node):  # type: ignore[misc]
    """Subscribe to ``JobEvent`` and persist every message durably."""

    def __init__(
        self,
        *,
        node_name: str = "durable_event_recorder",
        parameter_overrides: list[Any] | None = None,
    ) -> None:
        super().__init__(node_name, parameter_overrides=parameter_overrides)
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
            trace_event = convert_job_event_to_trace_event(message)
        except ValueError as exc:
            self.get_logger().error(f"Conversion failed for trace '{message.trace_id}': {exc}")
            return

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
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
