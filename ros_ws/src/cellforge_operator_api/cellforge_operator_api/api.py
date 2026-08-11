"""FastAPI transport for the pure operator service."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from cellforge_operator_api.core import (
    JobSubmission,
    OperatorError,
    OperatorService,
    Principal,
    RuntimeSnapshot,
)
from cellforge_operator_api.ui import OPERATOR_HTML


def create_app(service: OperatorService, *, bundle_id: str = "") -> FastAPI:
    """Create the local-only ASGI application around *service*."""

    app = FastAPI(
        title="CellForge Local Operator API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )

    @app.middleware("http")
    async def local_security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def operator_ui() -> str:
        return OPERATOR_HTML

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "bundle_id": bundle_id}

    @app.get("/api/v1/status")
    async def status(request: Request) -> Response:
        principal = _authenticate(service, request)
        if isinstance(principal, Response):
            return principal
        try:
            snapshot = await service.status(principal)
        except OperatorError as error:
            return _error(error)
        return JSONResponse(_snapshot_document(snapshot))

    @app.get("/api/v1/jobs/active")
    async def active_job(request: Request) -> Response:
        principal = _authenticate(service, request)
        if isinstance(principal, Response):
            return principal
        try:
            snapshot = await service.status(principal)
        except OperatorError as error:
            return _error(error)
        return JSONResponse(
            {"active_job": asdict(snapshot.active_job) if snapshot.active_job else None}
        )

    @app.get("/api/v1/faults")
    async def faults(request: Request) -> Response:
        principal = _authenticate(service, request)
        if isinstance(principal, Response):
            return principal
        try:
            snapshot = await service.status(principal)
        except OperatorError as error:
            return _error(error)
        return JSONResponse({"faults": [_fault_document(item) for item in snapshot.faults]})

    @app.get("/api/v1/identity")
    async def identity(request: Request) -> Response:
        principal = _authenticate(service, request)
        if isinstance(principal, Response):
            return principal
        try:
            snapshot = await service.status(principal)
        except OperatorError as error:
            return _error(error)
        return JSONResponse(asdict(snapshot.identity))

    @app.get("/api/v1/traces/{trace_id}/summary")
    async def trace_summary(trace_id: str, request: Request) -> Response:
        principal = _authenticate(service, request)
        if isinstance(principal, Response):
            return principal
        try:
            summary = await service.trace_summary(principal, trace_id)
        except OperatorError as error:
            return _error(error)
        if summary is None:
            return _error(
                OperatorError("operator.trace.not_found", "The local trace was not found."), 404
            )
        return JSONResponse(asdict(summary))

    @app.get("/api/v1/recovery-actions")
    async def recovery_actions(request: Request) -> Response:
        principal = _authenticate(service, request)
        if isinstance(principal, Response):
            return principal
        try:
            await service.status(principal)
        except OperatorError as error:
            return _error(error)
        return JSONResponse(
            {"actions": [action.to_document() for action in service.catalog.actions]}
        )

    @app.post("/api/v1/jobs")
    async def submit_job(request: Request) -> Response:
        request_id = _request_id(request)
        principal = _authenticate_mutation(service, request, "job.submit", request_id)
        if isinstance(principal, Response):
            return principal
        try:
            body = await _json_body(request)
            submission = JobSubmission.from_document(body)
            result = await service.submit(principal, submission, request_id)
        except OperatorError as error:
            return _audited_error(service, principal, "job.submit", "", request_id, error)
        return JSONResponse(
            result.to_document(), status_code=_result_status(result.success, result.code)
        )

    @app.post("/api/v1/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str, request: Request) -> Response:
        request_id = _request_id(request)
        principal = _authenticate_mutation(service, request, "job.cancel", request_id, job_id)
        if isinstance(principal, Response):
            return principal
        try:
            body = await _json_body(request, empty_allowed=True)
            timeout = _timeout_from_body(body, default=5.0)
            result = await service.cancel_job(
                principal, job_id, timeout_seconds=timeout, request_id=request_id
            )
        except OperatorError as error:
            return _audited_error(service, principal, "job.cancel", job_id, request_id, error)
        return JSONResponse(
            result.to_document(), status_code=_result_status(result.success, result.code)
        )

    @app.post("/api/v1/recovery-actions/{action_id}")
    async def recover(action_id: str, request: Request) -> Response:
        request_id = _request_id(request)
        principal = _authenticate_mutation(
            service, request, "recovery.request", request_id, action_id
        )
        if isinstance(principal, Response):
            return principal
        try:
            body = await _json_body(request)
            if not isinstance(body, dict):
                raise OperatorError("operator.input.invalid", "Request body must be an object.")
            allowed = {"fault_id", "confirmation", "timeout_seconds"}
            if set(body) - allowed or "fault_id" not in body:
                raise OperatorError(
                    "operator.input.invalid", "Recovery request fields are invalid."
                )
            fault_id = body["fault_id"]
            confirmation = body.get("confirmation", "")
            if not isinstance(fault_id, str) or not isinstance(confirmation, str):
                raise OperatorError(
                    "operator.input.invalid", "Recovery request values are invalid."
                )
            timeout = _timeout_from_body(body, default=10.0)
            result = await service.recover(
                principal,
                action_id,
                fault_id,
                confirmation,
                timeout_seconds=timeout,
                request_id=request_id,
            )
        except OperatorError as error:
            return _audited_error(
                service, principal, "recovery.request", action_id, request_id, error
            )
        return JSONResponse(
            result.to_document(), status_code=_result_status(result.success, result.code)
        )

    return app


def _authenticate(service: OperatorService, request: Request) -> Principal | Response:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        token = ""
    try:
        return service.authenticate(token.strip())
    except OperatorError as error:
        return _error(error, 401)


def _authenticate_mutation(
    service: OperatorService,
    request: Request,
    action: str,
    request_id: str,
    resource: str = "",
) -> Principal | Response:
    principal = _authenticate(service, request)
    if isinstance(principal, Response):
        try:
            service.audit_rejection(
                principal=None,
                action=action,
                resource=resource,
                code="operator.auth.invalid",
                request_id=request_id,
            )
        except OperatorError as audit_error:
            return _error(audit_error, 503)
    return principal


def _audited_error(
    service: OperatorService,
    principal: Principal,
    action: str,
    resource: str,
    request_id: str,
    error: OperatorError,
) -> Response:
    try:
        service.audit_rejection(
            principal=principal,
            action=action,
            resource=resource,
            code=error.code,
            request_id=request_id,
        )
    except OperatorError as audit_error:
        return _error(audit_error, 503)
    return _error(error)


async def _json_body(request: Request, *, empty_allowed: bool = False) -> object:
    raw = await request.body()
    if empty_allowed and not raw:
        return {}
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OperatorError(
            "operator.input.invalid", "Request body must contain valid JSON."
        ) from None


def _timeout_from_body(document: object, *, default: float) -> float:
    if not isinstance(document, dict):
        raise OperatorError("operator.input.invalid", "Request body must be an object.")
    value = document.get("timeout_seconds", default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise OperatorError("operator.input.invalid", "timeout_seconds must be numeric.")
    timeout = float(value)
    if not 0.05 <= timeout <= 300.0:
        raise OperatorError("operator.input.invalid", "timeout_seconds is outside allowed bounds.")
    return timeout


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "")
    if supplied and len(supplied) <= 128 and all(character.isprintable() for character in supplied):
        return supplied
    return str(uuid4())


def _snapshot_document(snapshot: RuntimeSnapshot) -> dict[str, object]:
    return {
        "cell_id": snapshot.cell_id,
        "state": snapshot.state,
        "safety_healthy": snapshot.safety_healthy,
        "all_required_devices_ready": snapshot.all_required_devices_ready,
        "identity": asdict(snapshot.identity),
        "active_job": asdict(snapshot.active_job) if snapshot.active_job else None,
        "faults": [_fault_document(item) for item in snapshot.faults],
        "observed_at": snapshot.observed_at.isoformat(),
        "stale": snapshot.stale,
        "safety_boundary": "display_only_independent_rated_hardware_remains_authoritative",
    }


def _fault_document(fault: Any) -> dict[str, object]:
    document = asdict(fault)
    document["recovery_action_ids"] = list(fault.recovery_action_ids)
    return document


def _result_status(success: bool, code: str) -> int:
    if success:
        return 202
    if "timeout" in code or "outcome_unknown" in code:
        return 504
    if "unavailable" in code or "failure" in code:
        return 503
    return 409


def _error(error: OperatorError, status_code: int | None = None) -> JSONResponse:
    if status_code is None:
        if error.code.startswith("operator.auth"):
            status_code = 403
        elif error.code.endswith("not_found"):
            status_code = 404
        elif "audit.unavailable" in error.code:
            status_code = 503
        else:
            status_code = 422
    return JSONResponse(
        {"error": {"code": error.code, "message": error.message}}, status_code=status_code
    )
