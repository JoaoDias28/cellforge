"""ROS 2 Jazzy smoke coverage for the fixed operator runtime bridge."""

from __future__ import annotations

import asyncio

import rclpy
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
    finally:
        node.destroy_node()
        rclpy.shutdown()
