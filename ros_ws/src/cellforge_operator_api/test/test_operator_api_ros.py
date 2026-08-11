"""ROS 2 Jazzy smoke coverage for the fixed operator runtime bridge."""

from __future__ import annotations

import asyncio

import rclpy
from cellforge_interfaces.msg import CellState, JobEvent
from cellforge_interfaces.srv import RequestOperatorAction
from cellforge_operator_api.core import RecoveryCatalog
from cellforge_operator_api.runtime import RosRuntimePort


def test_ros_bridge_constructs_with_fixed_contracts_and_fails_status_closed(tmp_path) -> None:
    rclpy.init()
    node = RosRuntimePort(catalog=RecoveryCatalog(()), trace_database=tmp_path / "traces.db")
    try:
        snapshot = asyncio.run(node.snapshot())
        request = RequestOperatorAction.Request()
        request.action_id = "acknowledge-timeout"
        request.action_kind = "acknowledge_fault"

        assert node.RUN_JOB_ACTION == "/cell/run_job"
        assert node.CELL_STATE_TOPIC == "/cell/state"
        assert node.JOB_EVENT_TOPIC == "/events/job"
        assert node.OPERATOR_ACTION_SERVICE == "/cell/operator_action"
        assert snapshot.state == "OFFLINE"
        assert snapshot.stale is True
        assert snapshot.safety_healthy is False
        assert request.action_kind == "acknowledge_fault"

        event = JobEvent()
        event.trace_id = "22222222-2222-4222-8222-222222222222"
        event.job_id = "11111111-1111-4111-8111-111111111111"
        event.bundle_id = "b" * 64
        event.source_revision = "a" * 40
        event.recipe_id = "pen-reference"
        event.recipe_version = 1
        event.recipe_sha256 = "c" * 64
        event.task_id = "engrave@1"
        event.task_sha256 = "d" * 64
        event.execution_mode = "simulation"
        event.event_type = "behavior_tree.node.entered"
        event.payload_json = '{"node":"Main/Engrave"}'
        node._on_job_event(event)
        state = CellState()
        state.cell_id = "cell-test"
        state.state = "RUNNING"
        state.bundle_id = event.bundle_id
        node._on_cell_state(state)
        active = asyncio.run(node.snapshot())
        assert active.active_job is not None
        assert active.active_job.active_step == "Main/Engrave"
        assert active.identity.recipe_sha256 == event.recipe_sha256
    finally:
        node.destroy_node()
        rclpy.shutdown()
