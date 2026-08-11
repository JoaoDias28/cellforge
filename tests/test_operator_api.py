"""Task 022 local operator API, authorization, audit, and runtime-boundary tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "ros_ws" / "src" / "cellforge_operator_api"
sys.path.insert(0, str(PACKAGE_ROOT))

from cellforge_operator_api.api import create_app  # noqa: E402
from cellforge_operator_api.core import (  # noqa: E402
    ActiveJob,
    FaultView,
    IdentityView,
    JobSubmission,
    OperationResult,
    OperatorError,
    OperatorService,
    Principal,
    RecoveryAction,
    RecoveryCatalog,
    Role,
    RuntimeSnapshot,
    SqliteAuditStore,
    TokenAuthorizer,
    TraceSummary,
)

TOKENS = {
    "viewer-token": ("viewer-1", "Viewer", "viewer"),
    "operator-token": ("operator-1", "Operator", "operator"),
    "maintainer-token": ("maintainer-1", "Maintainer", "maintainer"),
}


class FakeRuntime:
    def __init__(self) -> None:
        self.snapshot_value = RuntimeSnapshot(
            cell_id="pen-cell-01",
            state="RECOVERABLE_FAULT",
            safety_healthy=False,
            all_required_devices_ready=True,
            identity=IdentityView("b" * 64, "pen-reference", 3, "engrave@1"),
            active_job=ActiveJob(
                "job-1", "trace-1", "pen-reference", 3, "engrave@1", "simulation", "pick", 0.25
            ),
            faults=(
                FaultView(
                    "laser-1:laser.timeout",
                    "laser.timeout",
                    "laser-1",
                    "ERROR",
                    "Laser cycle timed out.",
                    ("ack-timeout", "maintenance-inspection"),
                ),
            ),
            observed_at=datetime.now(UTC),
        )
        self.calls: list[tuple[str, object]] = []
        self.result = OperationResult(True, "operator.test.accepted", "Accepted.", "trace-1")
        self.delay = 0.0
        self.started = asyncio.Event()
        self.cancel_seen = False

    async def snapshot(self) -> RuntimeSnapshot:
        return self.snapshot_value

    async def trace_summary(self, trace_id: str) -> TraceSummary | None:
        if trace_id != "trace-1":
            return None
        return TraceSummary(trace_id, "job-1", 4, 1, 4, "job.completed", "INFO")

    async def submit_job(
        self, submission: JobSubmission, cancel_event: asyncio.Event
    ) -> OperationResult:
        self.calls.append(("submit", submission))
        return await self._complete(cancel_event)

    async def cancel_job(self, job_id: str, cancel_event: asyncio.Event) -> OperationResult:
        self.calls.append(("cancel", job_id))
        return await self._complete(cancel_event)

    async def perform_recovery(
        self,
        action: RecoveryAction,
        fault_id: str,
        principal: Principal,
        cancel_event: asyncio.Event,
    ) -> OperationResult:
        self.calls.append(("recovery", (action.action_id, fault_id, principal.principal_id)))
        return await self._complete(cancel_event)

    async def _complete(self, cancel_event: asyncio.Event) -> OperationResult:
        self.started.set()
        if self.delay:
            deadline = asyncio.get_running_loop().time() + self.delay
            while asyncio.get_running_loop().time() < deadline:
                if cancel_event.is_set():
                    self.cancel_seen = True
                    return OperationResult(
                        False, "operator.test.cancelled", "Cancelled.", outcome_certain=False
                    )
                await asyncio.sleep(0.005)
        return self.result


def _write_auth(path: Path) -> TokenAuthorizer:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "tokens": [
                    {
                        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                        "principal_id": values[0],
                        "display_name": values[1],
                        "role": values[2],
                    }
                    for token, values in TOKENS.items()
                ],
            }
        ),
        encoding="utf-8",
    )
    return TokenAuthorizer.from_file(path)


def _write_catalog(path: Path, *, forbidden: bool = False) -> RecoveryCatalog:
    action: dict[str, Any] = {
        "action_id": "ack-timeout",
        "fault_codes": ["laser.timeout"],
        "kind": "acknowledge_fault",
        "label": "Acknowledge timeout",
        "instructions": "Inspect the machine and acknowledge the timeout.",
        "required_role": "operator",
        "confirmation": "ACKNOWLEDGE",
    }
    if forbidden:
        action["service_name"] = "/arbitrary/service"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "actions": [
                    action,
                    {
                        "action_id": "maintenance-inspection",
                        "fault_codes": ["laser.timeout"],
                        "kind": "enter_maintenance",
                        "label": "Enter maintenance inspection",
                        "instructions": "Use local enabling and inspect the laser.",
                        "required_role": "maintainer",
                        "confirmation": "ENTER MAINTENANCE",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return RecoveryCatalog.from_file(path)


def _service(tmp_path: Path) -> tuple[OperatorService, FakeRuntime, SqliteAuditStore]:
    runtime = FakeRuntime()
    audit = SqliteAuditStore(tmp_path / "operator-audit.db")
    service = OperatorService(
        _write_auth(tmp_path / "auth.json"),
        _write_catalog(tmp_path / "recovery.json"),
        audit,
        runtime,
    )
    return service, runtime, audit


def _job_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "job_id": "job-2",
        "cell_id": "pen-cell-01",
        "recipe_id": "pen-reference",
        "recipe_version": 3,
        "task_id": "engrave@1",
        "input_payload": {"text": "CELLFORGE"},
        "execution_mode": "simulation",
        "idempotency_key": "job-2-attempt-1",
        "timeout_seconds": 2.0,
    }
    document.update(changes)
    return document


async def _request(
    app: Any,
    method: str,
    path: str,
    *,
    token: str = "viewer-token",
    json_body: object | None = None,
    raw_body: bytes | None = None,
    request_id: str = "request-1",
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}", "X-Request-ID": request_id}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://operator.local"
    ) as client:
        return await client.request(method, path, headers=headers, json=json_body, content=raw_body)


def test_token_authorization_and_invalid_configuration_fail_closed(tmp_path: Path) -> None:
    authorizer = _write_auth(tmp_path / "auth.json")
    assert authorizer.authenticate("operator-token").role is Role.OPERATOR
    with pytest.raises(OperatorError, match="operator.auth.invalid"):
        authorizer.authenticate("wrong")
    (tmp_path / "bad.json").write_text('{"schema_version":"0.1.0","tokens":[]}', encoding="utf-8")
    with pytest.raises(OperatorError, match="operator.auth.config_invalid"):
        TokenAuthorizer.from_file(tmp_path / "bad.json")


def test_recovery_catalog_rejects_arbitrary_ros_names_and_weak_maintenance_role(
    tmp_path: Path,
) -> None:
    with pytest.raises(OperatorError, match="operator.recovery.catalog_invalid"):
        _write_catalog(tmp_path / "forbidden.json", forbidden=True)
    path = tmp_path / "weak.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "actions": [
                    {
                        "action_id": "maintenance",
                        "fault_codes": ["laser.timeout"],
                        "kind": "enter_maintenance",
                        "label": "Maintenance",
                        "instructions": "Inspect.",
                        "required_role": "operator",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(OperatorError, match="Maintenance requires maintainer"):
        RecoveryCatalog.from_file(path)


def test_audit_events_survive_restart_without_tokens_or_payloads(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    store = SqliteAuditStore(path)
    store.record(
        request_id="r1",
        principal=Principal("operator-1", "Operator", Role.OPERATOR),
        action="job.submit",
        resource="job-1",
        outcome="REQUESTED",
        code="operator.action.requested",
        details={"execution_mode": "simulation"},
    )
    store.close()
    reopened = SqliteAuditStore(path)
    events = reopened.query(request_id="r1")
    assert [(event.sequence, event.action, event.outcome) for event in events] == [
        (1, "job.submit", "REQUESTED")
    ]
    assert "token" not in json.dumps(events[0].details).lower()
    reopened.close()


def test_status_identity_fault_active_job_trace_and_ui_endpoints(tmp_path: Path) -> None:
    service, _, audit = _service(tmp_path)
    app = create_app(service, bundle_id="b" * 64)
    responses = {
        path: asyncio.run(_request(app, "GET", path))
        for path in (
            "/api/v1/status",
            "/api/v1/jobs/active",
            "/api/v1/faults",
            "/api/v1/identity",
            "/api/v1/traces/trace-1/summary",
            "/api/v1/recovery-actions",
        )
    }
    assert all(response.status_code == 200 for response in responses.values())
    assert responses["/api/v1/status"].json()["safety_boundary"].startswith("display_only")
    assert responses["/api/v1/identity"].json()["bundle_id"] == "b" * 64
    ui = asyncio.run(_request(app, "GET", "/"))
    assert ui.status_code == 200
    assert "arbitrary ROS" not in ui.text
    assert "Submit approved job" in ui.text
    assert "requestRecovery" in ui.text
    health = asyncio.run(_request(app, "GET", "/health"))
    assert health.json() == {"status": "healthy", "bundle_id": "b" * 64}
    audit.close()


def test_submit_cancel_and_recovery_success_are_audited(tmp_path: Path) -> None:
    service, runtime, audit = _service(tmp_path)
    app = create_app(service)
    submit = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/jobs",
            token="operator-token",
            json_body=_job_document(),
            request_id="submit-request",
        )
    )
    cancel = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/jobs/job-1/cancel",
            token="operator-token",
            json_body={},
            request_id="cancel-request",
        )
    )
    recover = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/recovery-actions/ack-timeout",
            token="operator-token",
            json_body={
                "fault_id": "laser-1:laser.timeout",
                "confirmation": "ACKNOWLEDGE",
            },
            request_id="recovery-request",
        )
    )
    assert [submit.status_code, cancel.status_code, recover.status_code] == [202, 202, 202]
    assert [call[0] for call in runtime.calls] == ["submit", "cancel", "recovery"]
    assert [event.outcome for event in audit.query(request_id="submit-request")] == [
        "REQUESTED",
        "COMPLETED",
    ]
    assert [event.outcome for event in audit.query(request_id="recovery-request")] == [
        "REQUESTED",
        "COMPLETED",
    ]
    audit.close()


def test_unauthorized_and_maintenance_recovery_are_rejected_and_audited(tmp_path: Path) -> None:
    service, runtime, audit = _service(tmp_path)
    app = create_app(service)
    unauthenticated = asyncio.run(
        _request(
            app, "POST", "/api/v1/jobs", token="bad", json_body=_job_document(), request_id="u1"
        )
    )
    viewer_submit = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/jobs",
            token="viewer-token",
            json_body=_job_document(),
            request_id="u2",
        )
    )
    operator_maintenance = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/recovery-actions/maintenance-inspection",
            token="operator-token",
            json_body={
                "fault_id": "laser-1:laser.timeout",
                "confirmation": "ENTER MAINTENANCE",
            },
            request_id="u3",
        )
    )
    assert [
        unauthenticated.status_code,
        viewer_submit.status_code,
        operator_maintenance.status_code,
    ] == [
        401,
        403,
        403,
    ]
    assert runtime.calls == []
    assert audit.query(request_id="u1")[0].principal_id == "anonymous"
    assert audit.query(request_id="u2")[0].outcome == "DENIED"
    assert audit.query(request_id="u3")[0].code == "operator.auth.forbidden"
    audit.close()


@pytest.mark.parametrize(
    "body",
    [b"not-json", json.dumps(_job_document(timeout_seconds=-1)).encode(), b"[]"],
)
def test_invalid_job_input_is_rejected_and_audited(tmp_path: Path, body: bytes) -> None:
    service, runtime, audit = _service(tmp_path)
    response = asyncio.run(
        _request(
            create_app(service),
            "POST",
            "/api/v1/jobs",
            token="operator-token",
            raw_body=body,
            request_id="invalid-request",
        )
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "operator.input.invalid"
    assert runtime.calls == []
    assert audit.query(request_id="invalid-request")[0].outcome == "DENIED"
    audit.close()


def test_unapproved_or_inapplicable_recovery_never_reaches_runtime(tmp_path: Path) -> None:
    service, runtime, audit = _service(tmp_path)
    app = create_app(service)
    response = asyncio.run(
        _request(
            app,
            "POST",
            "/api/v1/recovery-actions/arbitrary",
            token="maintainer-token",
            json_body={"fault_id": "laser-1:laser.timeout"},
            request_id="recovery-denied",
        )
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "operator.recovery.not_approved"
    assert runtime.calls == []
    assert audit.query(request_id="recovery-denied")[0].outcome == "DENIED"
    audit.close()


def test_runtime_failure_is_sanitized_and_audited(tmp_path: Path) -> None:
    service, runtime, audit = _service(tmp_path)

    async def fail(_submission: JobSubmission, _cancel: asyncio.Event) -> OperationResult:
        raise RuntimeError("vendor secret and implementation detail")

    runtime.submit_job = fail  # type: ignore[assignment]
    principal = service.authenticate("operator-token")
    result = asyncio.run(
        service.submit(principal, JobSubmission.from_document(_job_document()), "failure-request")
    )
    assert result.code == "operator.runtime.failure"
    assert "vendor secret" not in result.message
    assert [event.outcome for event in audit.query(request_id="failure-request")] == [
        "REQUESTED",
        "FAILED",
    ]
    audit.close()


def test_timeout_requests_cancellation_and_records_uncertain_outcome(tmp_path: Path) -> None:
    service, runtime, audit = _service(tmp_path)
    runtime.delay = 0.2
    principal = service.authenticate("operator-token")
    document = _job_document(timeout_seconds=0.05)
    result = asyncio.run(
        service.submit(principal, JobSubmission.from_document(document), "timeout-request")
    )
    assert result.code == "operator.action.timeout"
    assert not result.outcome_certain
    assert audit.query(request_id="timeout-request")[-1].outcome == "TIMED_OUT"
    audit.close()


def test_caller_cancellation_propagates_and_is_audited(tmp_path: Path) -> None:
    service, runtime, audit = _service(tmp_path)
    runtime.delay = 10.0
    principal = service.authenticate("operator-token")

    async def scenario() -> None:
        task = asyncio.create_task(
            service.submit(
                principal, JobSubmission.from_document(_job_document()), "cancelled-request"
            )
        )
        await runtime.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert audit.query(request_id="cancelled-request")[-1].outcome == "CANCELLED"
    audit.close()


def test_audit_failure_refuses_dispatch(tmp_path: Path) -> None:
    service, runtime, audit = _service(tmp_path)
    audit.close()
    with pytest.raises(OperatorError, match="operator.audit.unavailable"):
        asyncio.run(
            service.submit(
                service.authenticate("operator-token"),
                JobSubmission.from_document(_job_document()),
                "audit-failure",
            )
        )
    assert runtime.calls == []


def test_operator_api_has_no_platform_dependency_or_dynamic_ros_endpoint() -> None:
    package_files = list((PACKAGE_ROOT / "cellforge_operator_api").glob("*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in package_files)
    assert "platform_url" not in source.lower()
    assert "requests." not in source
    runtime_source = (PACKAGE_ROOT / "cellforge_operator_api" / "runtime.py").read_text(
        encoding="utf-8"
    )
    assert 'RUN_JOB_ACTION = "/cell/run_job"' in runtime_source
    assert 'OPERATOR_ACTION_SERVICE = "/cell/operator_action"' in runtime_source
    assert "service_name" not in runtime_source
