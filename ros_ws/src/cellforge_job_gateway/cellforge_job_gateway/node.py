"""ROS 2 action gateway for durable job admission and supervisor forwarding."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import rclpy
from cellforge_interfaces.action import ExecuteFrozenJob, RunJob
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.task import Future

from cellforge_job_gateway.core import (
    BundleResolver,
    FrozenJob,
    GatewayError,
    JobRequest,
    JobResult,
    PrepareKind,
    SqliteJobStore,
)


class JobGatewayNode(Node):  # type: ignore[misc]
    """Freeze public RunJob requests before forwarding them to the supervisor."""

    def __init__(self, *, parameter_overrides: list[Any] | None = None) -> None:
        super().__init__("job_gateway", parameter_overrides=parameter_overrides)
        bundle_root = str(self.declare_parameter("bundle_root", "").value)
        manifest_path = str(self.declare_parameter("manifest_path", "manifest.json").value)
        database_path = str(
            self.declare_parameter("database_path", "var/lib/cellforge/jobs.db").value
        )
        public_action = str(self.declare_parameter("action_name", "/cell/run_job").value)
        supervisor_action = str(
            self.declare_parameter("supervisor_action_name", "/cell/supervisor/run_job").value
        )
        self._discovery_timeout = float(
            self.declare_parameter("supervisor_discovery_timeout_seconds", 5.0).value
        )
        if not bundle_root:
            raise RuntimeError("bundle_root parameter must identify the active immutable bundle")
        callback_group = ReentrantCallbackGroup()
        self._resolver = BundleResolver(bundle_root, manifest_path)
        self._store = SqliteJobStore(Path(database_path))
        self._supervisor = ActionClient(
            self, ExecuteFrozenJob, supervisor_action, callback_group=callback_group
        )
        self._server = ActionServer(
            self,
            RunJob,
            public_action,
            execute_callback=self._execute,
            goal_callback=self._accept_goal,
            cancel_callback=self._accept_cancel,
            callback_group=callback_group,
        )

    @staticmethod
    def _accept_goal(_goal: Any) -> GoalResponse:
        return GoalResponse.ACCEPT

    @staticmethod
    def _accept_cancel(_goal_handle: Any) -> CancelResponse:
        return CancelResponse.ACCEPT

    async def _execute(self, goal_handle: Any) -> Any:
        trace_id = str(uuid4())
        request = self._request_from_message(goal_handle.request)
        try:
            frozen = self._resolver.freeze(request, trace_id)
            decision = self._store.prepare(frozen)
        except GatewayError as error:
            goal_handle.abort()
            return self._result_message(JobResult(False, error.code, error.message, "{}", trace_id))

        if decision.kind is PrepareKind.REPLAY:
            assert decision.result is not None
            self._set_terminal_state(goal_handle, decision.result)
            return self._result_message(decision.result)

        assert decision.frozen_job is not None
        result = await self._forward(goal_handle, decision.frozen_job)
        try:
            self._store.finish(request.idempotency_key, result)
        except GatewayError as error:
            self.get_logger().error(f"Could not persist terminal job result: {error.code}")
            goal_handle.abort()
            return self._result_message(
                JobResult(False, "gateway.store.failure", error.message, "{}", trace_id)
            )
        self._set_terminal_state(goal_handle, result)
        return self._result_message(result)

    async def _forward(self, public_goal_handle: Any, frozen: FrozenJob) -> JobResult:
        request = frozen.request
        trace_id = frozen.trace_id
        discovery_deadline = time.monotonic() + self._discovery_timeout
        while not self._supervisor.server_is_ready():
            if public_goal_handle.is_cancel_requested:
                return JobResult(
                    False,
                    "gateway.job.cancelled",
                    "Job was cancelled before supervisor submission.",
                    "{}",
                    trace_id,
                )
            if time.monotonic() >= discovery_deadline:
                return JobResult(
                    False,
                    "gateway.supervisor.unavailable",
                    "Supervisor action server is unavailable.",
                    "{}",
                    trace_id,
                )
            await self._yield_executor()

        supervisor_goal = self._frozen_goal(frozen, public_goal_handle.request.timeout)
        send_future = self._supervisor.send_goal_async(
            supervisor_goal,
            feedback_callback=lambda feedback: self._forward_feedback(public_goal_handle, feedback),
        )
        supervisor_handle = await send_future
        if not supervisor_handle.accepted:
            return JobResult(
                False,
                "gateway.supervisor.rejected",
                "Supervisor rejected the validated frozen job.",
                "{}",
                trace_id,
            )
        self._store.mark_running(request.idempotency_key)
        result_future = supervisor_handle.get_result_async()
        cancel_sent = False
        deadline = time.monotonic() + self._goal_timeout_seconds(public_goal_handle.request)
        while not result_future.done():
            if public_goal_handle.is_cancel_requested and not cancel_sent:
                await supervisor_handle.cancel_goal_async()
                cancel_sent = True
            if time.monotonic() >= deadline:
                await supervisor_handle.cancel_goal_async()
                return JobResult(
                    False,
                    "gateway.supervisor.outcome_unknown",
                    "Supervisor did not return before the job deadline; recovery is required.",
                    "{}",
                    trace_id,
                )
            await self._yield_executor()
        wrapped = result_future.result()
        returned = wrapped.result
        return JobResult(
            bool(returned.success),
            str(returned.result_code),
            str(returned.result_message),
            str(returned.output_payload_json),
            str(returned.trace_id or trace_id),
        )

    @staticmethod
    def _request_from_message(goal: Any) -> JobRequest:
        return JobRequest(
            job_id=str(goal.job_id),
            cell_id=str(goal.cell_id),
            recipe_id=str(goal.recipe_id),
            recipe_version=int(goal.recipe_version),
            task_id=str(goal.task_id),
            input_payload_json=str(goal.input_payload_json),
            execution_mode=str(goal.execution_mode),
            idempotency_key=str(goal.idempotency_key),
        )

    async def _yield_executor(self) -> None:
        future: Any = Future()
        timer = self.create_timer(0.02, lambda: future.set_result(None))
        try:
            await future
        finally:
            self.destroy_timer(timer)

    @staticmethod
    def _frozen_goal(frozen: FrozenJob, timeout: Any) -> Any:
        request = frozen.request
        goal = ExecuteFrozenJob.Goal()
        goal.trace_id = frozen.trace_id
        goal.job_id = request.job_id
        goal.cell_id = request.cell_id
        goal.bundle_id = frozen.bundle_id
        goal.source_revision = frozen.source_revision
        goal.recipe_id = request.recipe_id
        goal.recipe_version = request.recipe_version
        goal.recipe_sha256 = frozen.recipe_sha256
        goal.recipe_yaml = frozen.recipe_yaml
        goal.task_id = request.task_id
        goal.task_sha256 = frozen.task_sha256
        goal.input_payload_json = request.input_payload_json
        goal.execution_mode = request.execution_mode
        goal.idempotency_key = request.idempotency_key
        goal.calibration_ids = list(frozen.calibration_ids)
        goal.calibration_sha256s = list(frozen.calibration_sha256s)
        goal.timeout = timeout
        return goal

    @staticmethod
    def _goal_timeout_seconds(goal: Any) -> float:
        value = float(goal.timeout.sec) + float(goal.timeout.nanosec) / 1_000_000_000
        return value if value > 0 else 300.0

    @staticmethod
    def _forward_feedback(public_goal_handle: Any, wrapped_feedback: Any) -> None:
        source = wrapped_feedback.feedback
        feedback = RunJob.Feedback()
        feedback.cell_state = source.cell_state
        feedback.active_node = source.active_node
        feedback.progress = source.progress
        feedback.message = source.message
        public_goal_handle.publish_feedback(feedback)

    @staticmethod
    def _result_message(result: JobResult) -> Any:
        message = RunJob.Result()
        message.success = result.success
        message.result_code = result.result_code
        message.result_message = result.result_message
        message.output_payload_json = result.output_payload_json
        message.trace_id = result.trace_id
        return message

    @staticmethod
    def _set_terminal_state(goal_handle: Any, result: JobResult) -> None:
        if result.result_code in {"supervisor.job.cancelled", "gateway.job.cancelled"}:
            goal_handle.canceled()
        elif result.success:
            goal_handle.succeed()
        else:
            goal_handle.abort()

    def destroy_node(self) -> None:
        self._server.destroy()
        self._store.close()
        super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = JobGatewayNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
