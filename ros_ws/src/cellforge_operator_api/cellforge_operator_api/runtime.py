"""Fixed ROS 2 runtime bridge for the local operator service."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cellforge_interfaces.action import RunJob
from cellforge_interfaces.msg import CellState, JobEvent
from cellforge_interfaces.srv import RequestOperatorAction
from rclpy.action import ActionClient
from rclpy.node import Node

from cellforge_operator_api.core import (
    ActiveJob,
    FaultView,
    IdentityView,
    JobSubmission,
    OperationResult,
    Principal,
    RecoveryAction,
    RecoveryCatalog,
    RuntimeSnapshot,
    TraceSummary,
)


class RosRuntimePort(Node):  # type: ignore[misc]
    """Observe canonical runtime state and call only fixed typed control interfaces."""

    RUN_JOB_ACTION = "/cell/run_job"
    CELL_STATE_TOPIC = "/cell/state"
    JOB_EVENT_TOPIC = "/events/job"
    OPERATOR_ACTION_SERVICE = "/cell/operator_action"

    def __init__(
        self,
        *,
        catalog: RecoveryCatalog,
        trace_database: str | Path,
        state_stale_seconds: float = 3.0,
    ) -> None:
        super().__init__("operator_api_bridge")
        self._catalog = catalog
        self._trace_database = Path(trace_database)
        self._state_stale_seconds = state_stale_seconds
        self._lock = threading.RLock()
        self._latest_state: Any | None = None
        self._state_received_monotonic = 0.0
        self._active_job: ActiveJob | None = None
        self._goal_handles: dict[str, Any] = {}
        self._run_job = ActionClient(self, RunJob, self.RUN_JOB_ACTION)
        self._operator_action = self.create_client(
            RequestOperatorAction, self.OPERATOR_ACTION_SERVICE
        )
        self._cell_subscription = self.create_subscription(
            CellState, self.CELL_STATE_TOPIC, self._on_cell_state, 10
        )
        self._event_subscription = self.create_subscription(
            JobEvent, self.JOB_EVENT_TOPIC, self._on_job_event, 100
        )

    async def snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            state = self._latest_state
            received = self._state_received_monotonic
            active_job = self._active_job
        if state is None:
            return RuntimeSnapshot(
                cell_id="",
                state="OFFLINE",
                safety_healthy=False,
                all_required_devices_ready=False,
                identity=IdentityView(bundle_id=""),
                stale=True,
            )
        stale = time.monotonic() - received > self._state_stale_seconds
        faults: list[FaultView] = []
        for device in state.devices:
            if not bool(device.faulted):
                continue
            code = str(device.fault_code or "device.fault.unknown")
            action_ids = tuple(
                action.action_id for action in self._catalog.actions if code in action.fault_codes
            )
            component_id = str(device.component_instance_id)
            faults.append(
                FaultView(
                    fault_id=f"{component_id}:{code}",
                    code=code,
                    component_instance_id=component_id,
                    severity="ERROR",
                    operator_message=str(device.fault_message or code),
                    recovery_action_ids=action_ids,
                )
            )
        identity = IdentityView(
            bundle_id=str(state.bundle_id),
            recipe_id=active_job.recipe_id if active_job else "",
            recipe_version=active_job.recipe_version if active_job else 0,
            task_id=active_job.task_id if active_job else "",
            source_revision=active_job.source_revision if active_job else "",
            recipe_sha256=active_job.recipe_sha256 if active_job else "",
            task_sha256=active_job.task_sha256 if active_job else "",
            execution_mode=active_job.execution_mode if active_job else "",
            calibration_ids=active_job.calibration_ids if active_job else (),
        )
        return RuntimeSnapshot(
            cell_id=str(state.cell_id),
            state="OFFLINE" if stale else str(state.state),
            safety_healthy=bool(state.safety_healthy) and not stale,
            all_required_devices_ready=bool(state.all_required_devices_ready) and not stale,
            identity=identity,
            active_job=active_job,
            faults=tuple(faults),
            observed_at=datetime.now(UTC),
            stale=stale,
        )

    async def trace_summary(self, trace_id: str) -> TraceSummary | None:
        return await asyncio.to_thread(self._read_trace_summary, trace_id)

    async def submit_job(
        self, submission: JobSubmission, cancel_event: asyncio.Event
    ) -> OperationResult:
        return await asyncio.to_thread(self._submit_blocking, submission, cancel_event)

    async def cancel_job(self, job_id: str, cancel_event: asyncio.Event) -> OperationResult:
        return await asyncio.to_thread(self._cancel_blocking, job_id, cancel_event)

    async def perform_recovery(
        self,
        action: RecoveryAction,
        fault_id: str,
        principal: Principal,
        cancel_event: asyncio.Event,
    ) -> OperationResult:
        try:
            return await asyncio.to_thread(
                self._recovery_blocking, action, fault_id, principal, cancel_event
            )
        except Exception as error:
            self.get_logger().error(f"Recovery dispatch failed: {error!r}")
            return OperationResult(
                False,
                "operator.recovery.failure",
                "The fixed local recovery dispatch failed.",
            )

    def _on_cell_state(self, message: Any) -> None:
        with self._lock:
            self._latest_state = message
            self._state_received_monotonic = time.monotonic()
            if str(message.active_job_id) and (
                self._active_job is None or self._active_job.job_id != str(message.active_job_id)
            ):
                self._active_job = ActiveJob(
                    job_id=str(message.active_job_id),
                    trace_id=str(message.active_trace_id),
                    recipe_id="",
                    recipe_version=0,
                    task_id="",
                    execution_mode="",
                )
            elif not str(message.active_job_id) and str(message.state) != "RUNNING":
                self._active_job = None

    def _on_job_event(self, message: Any) -> None:
        try:
            payload: object = json.loads(message.payload_json or "{}")
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        event_type = str(message.event_type)
        with self._lock:
            if event_type in {"job.completed", "job.rejected", "job.cancelled", "job.failed"}:
                if self._active_job and self._active_job.job_id == str(message.job_id):
                    self._active_job = None
                return
            if event_type not in {
                "job.accepted",
                "job.started",
                "behavior_tree.node.entered",
            }:
                return
            previous = self._active_job
            self._active_job = ActiveJob(
                job_id=str(message.job_id),
                trace_id=str(message.trace_id),
                recipe_id=str(getattr(message, "recipe_id", "")),
                recipe_version=_safe_int(getattr(message, "recipe_version", 0)),
                task_id=str(getattr(message, "task_id", "")),
                execution_mode=str(getattr(message, "execution_mode", "")),
                active_step=str(payload.get("node", previous.active_step if previous else "")),
                progress=_safe_float(
                    payload.get("progress", previous.progress if previous else 0.0)
                ),
                bundle_id=str(getattr(message, "bundle_id", "")),
                source_revision=str(getattr(message, "source_revision", "")),
                recipe_sha256=str(getattr(message, "recipe_sha256", "")),
                task_sha256=str(getattr(message, "task_sha256", "")),
                calibration_ids=tuple(getattr(message, "calibration_ids", ())),
            )

    def _submit_blocking(
        self, submission: JobSubmission, cancel_event: asyncio.Event
    ) -> OperationResult:
        if not self._wait_for_server(self._run_job, cancel_event, 5.0):
            return OperationResult(
                False, "operator.gateway.unavailable", "The local job gateway is unavailable."
            )
        goal = RunJob.Goal()
        goal.job_id = submission.job_id
        goal.cell_id = submission.cell_id
        goal.recipe_id = submission.recipe_id
        goal.recipe_version = submission.recipe_version
        goal.task_id = submission.task_id
        goal.input_payload_json = json.dumps(submission.input_payload, sort_keys=True)
        goal.execution_mode = submission.execution_mode
        goal.idempotency_key = submission.idempotency_key
        seconds = int(submission.timeout_seconds)
        goal.timeout.sec = seconds
        goal.timeout.nanosec = int((submission.timeout_seconds - seconds) * 1_000_000_000)
        send_future = self._run_job.send_goal_async(goal, feedback_callback=self._job_feedback)
        if not _wait_future(send_future, cancel_event, 5.0):
            return OperationResult(
                False,
                "operator.gateway.outcome_unknown",
                "Job gateway did not acknowledge submission.",
                outcome_certain=False,
            )
        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return OperationResult(
                False, "operator.job.rejected", "The local job gateway rejected the job."
            )
        with self._lock:
            self._goal_handles[submission.job_id] = goal_handle
            self._active_job = ActiveJob(
                submission.job_id,
                "",
                submission.recipe_id,
                submission.recipe_version,
                submission.task_id,
                submission.execution_mode,
            )
        result_future = goal_handle.get_result_async()
        while not result_future.done():
            if cancel_event.is_set():
                _request_cancel(goal_handle)
                return OperationResult(
                    False,
                    "operator.job.cancel_requested",
                    "Cancellation was requested; final job outcome is pending.",
                    outcome_certain=False,
                )
            time.sleep(0.02)
        with self._lock:
            self._goal_handles.pop(submission.job_id, None)
        wrapped = result_future.result()
        result = wrapped.result
        return OperationResult(
            bool(result.success),
            str(result.result_code),
            str(result.result_message),
            str(result.trace_id),
            "outcome_unknown" not in str(result.result_code),
        )

    def _cancel_blocking(self, job_id: str, cancel_event: asyncio.Event) -> OperationResult:
        with self._lock:
            goal_handle = self._goal_handles.get(job_id)
        if goal_handle is None:
            return OperationResult(
                False, "operator.job.not_active", "No locally submitted active job has this ID."
            )
        future = goal_handle.cancel_goal_async()
        if not _wait_future(future, cancel_event, 5.0):
            return OperationResult(
                False,
                "operator.job.cancel_outcome_unknown",
                "The job gateway did not confirm the cancellation request.",
                outcome_certain=False,
            )
        response = future.result()
        accepted = response is not None and bool(response.goals_canceling)
        return OperationResult(
            accepted,
            "operator.job.cancel_requested" if accepted else "operator.job.cancel_rejected",
            "Cancellation request accepted." if accepted else "Cancellation request was rejected.",
            outcome_certain=False,
        )

    def _recovery_blocking(
        self,
        action: RecoveryAction,
        fault_id: str,
        principal: Principal,
        cancel_event: asyncio.Event,
    ) -> OperationResult:
        if not self._wait_for_service(self._operator_action, cancel_event, 5.0):
            return OperationResult(
                False,
                "operator.recovery.unavailable",
                "The fixed local operator-action service is unavailable.",
            )
        request = RequestOperatorAction.Request()
        request.action_id = action.action_id
        request.action_kind = action.kind.value
        request.fault_id = fault_id
        request.principal_id = principal.principal_id
        future = self._operator_action.call_async(request)
        if not _wait_future(future, cancel_event, 10.0):
            return OperationResult(
                False,
                "operator.recovery.outcome_unknown",
                "The recovery request outcome is unknown.",
                outcome_certain=False,
            )
        try:
            response = future.result()
        except Exception as error:
            self.get_logger().error(f"Operator-action service failed: {error!r}")
            return OperationResult(
                False,
                "operator.recovery.failure",
                "The fixed local recovery service failed.",
            )
        if response is None:
            return OperationResult(
                False, "operator.recovery.failure", "The recovery service returned no result."
            )
        return OperationResult(
            bool(response.accepted),
            str(response.result_code),
            str(response.result_message),
            outcome_certain=bool(response.outcome_certain),
        )

    @staticmethod
    def _wait_for_server(client: Any, cancel_event: asyncio.Event, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and not cancel_event.is_set():
            if client.wait_for_server(timeout_sec=0.1):
                return True
        return False

    @staticmethod
    def _wait_for_service(client: Any, cancel_event: asyncio.Event, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and not cancel_event.is_set():
            if client.wait_for_service(timeout_sec=0.1):
                return True
        return False

    @staticmethod
    def _job_feedback(wrapped: Any) -> None:
        del wrapped

    def _read_trace_summary(self, trace_id: str) -> TraceSummary | None:
        if not self._trace_database.exists():
            return None
        import sqlite3

        connection = sqlite3.connect(f"file:{self._trace_database}?mode=ro", uri=True)
        try:
            rows = connection.execute(
                "SELECT sequence, job_id, event_type, severity, payload_json, bundle_id, "
                "source_revision, recipe_id, recipe_version, recipe_sha256, task_id, task_sha256, "
                "execution_mode, calibration_ids_json FROM events "
                "WHERE trace_id = ? ORDER BY sequence",
                (trace_id,),
            ).fetchall()
        finally:
            connection.close()
        if not rows:
            return None
        fault_codes: set[str] = set()
        for row in rows:
            if str(row[2]) != "fault.raised":
                continue
            try:
                payload = json.loads(row[4])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("fault_code"), str):
                fault_codes.add(payload["fault_code"])
        return TraceSummary(
            trace_id=trace_id,
            job_id=str(rows[-1][1]),
            event_count=len(rows),
            first_sequence=int(rows[0][0]),
            last_sequence=int(rows[-1][0]),
            final_event_type=str(rows[-1][2]),
            final_severity=str(rows[-1][3]),
            fault_codes=tuple(sorted(fault_codes)),
            bundle_id=str(rows[0][5]),
            source_revision=str(rows[0][6]),
            recipe_id=str(rows[0][7]),
            recipe_version=int(rows[0][8]),
            recipe_sha256=str(rows[0][9]),
            task_id=str(rows[0][10]),
            task_sha256=str(rows[0][11]),
            execution_mode=str(rows[0][12]),
            calibration_ids=tuple(json.loads(rows[0][13] or "[]")),
        )


def _wait_future(future: Any, cancel_event: asyncio.Event, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while not future.done() and time.monotonic() < deadline and not cancel_event.is_set():
        time.sleep(0.02)
    return bool(future.done())


def _request_cancel(goal_handle: Any) -> None:
    try:
        goal_handle.cancel_goal_async()
    except Exception:
        pass


def _safe_int(value: object) -> int:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
