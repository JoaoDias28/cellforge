"""ROS 2 Jazzy integration tests for the Task 010 runtime nodes."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import rclpy
from cellforge_interfaces.msg import DeviceState, JobEvent
from cellforge_state_trace.aggregator import StateAggregatorNode
from cellforge_state_trace.recorder import DurableEventRecorderNode
from cellforge_state_trace.trace_store import SqliteTraceEventStore
from rclpy.parameter import Parameter


@pytest.fixture(scope="module", autouse=True)
def _ros_context() -> Iterator[None]:
    rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


class _CapturePublisher:
    def __init__(self) -> None:
        self.last_message: Any | None = None

    def publish(self, message: Any) -> None:
        self.last_message = message


def test_state_aggregator_fails_closed_without_required_devices() -> None:
    node = StateAggregatorNode(node_name="state_aggregator_empty_test")
    capture = _CapturePublisher()
    node._cell_pub = capture
    node._safety_entry.update(True)

    try:
        node._publish_cell_state()
        message = capture.last_message
        assert message is not None
        assert message.state == "STARTING"
        assert not message.all_required_devices_ready
    finally:
        node.destroy_node()


def test_state_aggregator_reports_ready_for_fresh_required_device() -> None:
    node = StateAggregatorNode(
        node_name="state_aggregator_ready_test",
        parameter_overrides=[Parameter("required_device_ids", value=["robot-test-001"])],
    )
    capture = _CapturePublisher()
    node._cell_pub = capture

    device = DeviceState()
    device.header.stamp = node.get_clock().now().to_msg()
    device.component_instance_id = "robot-test-001"
    device.state = "READY"
    device.ready = True
    device.details_json = "{}"

    try:
        node._on_device_state(device)
        node._safety_entry.update(True)
        node._publish_cell_state()
        message = capture.last_message
        assert message is not None
        assert message.state == "READY"
        assert message.all_required_devices_ready
        assert message.safety_healthy
    finally:
        node.destroy_node()


def test_durable_recorder_persists_a_correlated_event(tmp_path: Path) -> None:
    db_path = tmp_path / "trace" / "events.db"
    node = DurableEventRecorderNode(
        node_name="durable_event_recorder_test",
        parameter_overrides=[Parameter("db_path", value=str(db_path))],
    )
    event = JobEvent()
    event.header.stamp = node.get_clock().now().to_msg()
    event.trace_id = "11111111-1111-1111-1111-111111111111"
    event.job_id = "22222222-2222-2222-2222-222222222222"
    event.cell_id = "cell-test"
    event.component_instance_id = "robot-test-001"
    event.command_id = "33333333-3333-3333-3333-333333333333"
    event.event_type = "device.command.completed"
    event.severity = "INFO"
    event.payload_json = '{"result":"ok"}'

    node._on_job_event(event)
    node.destroy_node()

    store = SqliteTraceEventStore(db_path)
    try:
        recorded = store.query(trace_id=event.trace_id)
        assert len(recorded) == 1
        assert recorded[0].job_id == event.job_id
        assert recorded[0].command_id == event.command_id
        assert recorded[0].payload == {"result": "ok"}
    finally:
        store.close()
