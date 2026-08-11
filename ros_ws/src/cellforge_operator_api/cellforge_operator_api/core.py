"""Pure authorization, recovery, audit, and operator-service contracts."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import sqlite3
import threading
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

JsonObject = dict[str, Any]
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_RECOVERY_KEYS = {
    "action_name",
    "command",
    "executable",
    "package",
    "service",
    "service_name",
    "topic",
}


class OperatorError(Exception):
    """Stable, sanitized operator API error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class Role(IntEnum):
    VIEWER = 10
    OPERATOR = 20
    MAINTAINER = 30
    ADMINISTRATOR = 40

    @classmethod
    def parse(cls, value: object) -> Role:
        if not isinstance(value, str):
            raise OperatorError("operator.auth.config_invalid", "Role must be a string.")
        try:
            return cls[value.strip().upper().replace(" ", "_")]
        except KeyError:
            raise OperatorError("operator.auth.config_invalid", "Role is not recognized.") from None

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True, slots=True)
class Principal:
    principal_id: str
    display_name: str
    role: Role


@dataclass(frozen=True, slots=True)
class _TokenEntry:
    token_sha256: str
    principal: Principal


class TokenAuthorizer:
    """Authenticate bearer tokens against cell-local SHA-256 digests."""

    def __init__(self, entries: tuple[_TokenEntry, ...]) -> None:
        if not entries:
            raise OperatorError("operator.auth.config_invalid", "At least one token is required.")
        self._entries = entries

    @classmethod
    def from_file(cls, path: str | Path) -> TokenAuthorizer:
        try:
            document: object = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise OperatorError(
                "operator.auth.config_invalid", "Local authorization configuration is unavailable."
            ) from None
        if not isinstance(document, dict) or document.get("schema_version") != "0.1.0":
            raise OperatorError(
                "operator.auth.config_invalid", "Authorization schema version is invalid."
            )
        raw_entries = document.get("tokens")
        if not isinstance(raw_entries, list):
            raise OperatorError("operator.auth.config_invalid", "Token list is invalid.")
        entries: list[_TokenEntry] = []
        seen_tokens: set[str] = set()
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise OperatorError("operator.auth.config_invalid", "Token entry is invalid.")
            digest = raw.get("token_sha256")
            principal_id = raw.get("principal_id")
            display_name = raw.get("display_name")
            if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
                raise OperatorError("operator.auth.config_invalid", "Token digest is invalid.")
            if digest in seen_tokens:
                raise OperatorError("operator.auth.config_invalid", "Token digest is duplicated.")
            if not isinstance(principal_id, str) or _ID.fullmatch(principal_id) is None:
                raise OperatorError("operator.auth.config_invalid", "Principal ID is invalid.")
            if not isinstance(display_name, str) or not display_name.strip():
                raise OperatorError("operator.auth.config_invalid", "Display name is invalid.")
            seen_tokens.add(digest)
            entries.append(
                _TokenEntry(
                    digest,
                    Principal(principal_id, display_name.strip(), Role.parse(raw.get("role"))),
                )
            )
        return cls(tuple(entries))

    def authenticate(self, token: str) -> Principal:
        if not token:
            raise OperatorError("operator.auth.required", "A local bearer token is required.")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        matched: Principal | None = None
        for entry in self._entries:
            if hmac.compare_digest(digest, entry.token_sha256):
                matched = entry.principal
        if matched is None:
            raise OperatorError("operator.auth.invalid", "The local bearer token is invalid.")
        return matched


class RecoveryKind(StrEnum):
    ACKNOWLEDGE_FAULT = "acknowledge_fault"
    REQUEST_SUPERVISOR_RECOVERY = "request_supervisor_recovery"
    ENTER_MAINTENANCE = "enter_maintenance"


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    action_id: str
    fault_codes: tuple[str, ...]
    kind: RecoveryKind
    label: str
    instructions: str
    required_role: Role
    confirmation: str

    def to_document(self) -> JsonObject:
        return {
            "action_id": self.action_id,
            "fault_codes": list(self.fault_codes),
            "kind": self.kind.value,
            "label": self.label,
            "instructions": self.instructions,
            "required_role": self.required_role.label,
            "confirmation": self.confirmation,
            "confirmation_required": bool(self.confirmation),
        }


class RecoveryCatalog:
    """Immutable semantic recovery allow-list with no ROS graph indirection."""

    def __init__(self, actions: tuple[RecoveryAction, ...]) -> None:
        if len({action.action_id for action in actions}) != len(actions):
            raise OperatorError(
                "operator.recovery.catalog_invalid", "Recovery action IDs must be unique."
            )
        self.actions = actions
        self._by_id = {action.action_id: action for action in actions}

    @classmethod
    def from_file(cls, path: str | Path) -> RecoveryCatalog:
        try:
            document: object = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise OperatorError(
                "operator.recovery.catalog_invalid", "Recovery catalog is unavailable or invalid."
            ) from None
        if not isinstance(document, dict) or document.get("schema_version") != "0.1.0":
            raise OperatorError(
                "operator.recovery.catalog_invalid", "Recovery catalog schema is invalid."
            )
        raw_actions = document.get("actions")
        if not isinstance(raw_actions, list):
            raise OperatorError(
                "operator.recovery.catalog_invalid", "Recovery action list is invalid."
            )
        actions: list[RecoveryAction] = []
        for raw in raw_actions:
            if not isinstance(raw, dict) or _FORBIDDEN_RECOVERY_KEYS.intersection(raw):
                raise OperatorError(
                    "operator.recovery.catalog_invalid",
                    "Recovery entries may contain only semantic allow-listed fields.",
                )
            action_id = raw.get("action_id")
            fault_codes = raw.get("fault_codes")
            label = raw.get("label")
            instructions = raw.get("instructions")
            confirmation = raw.get("confirmation", "")
            if not isinstance(action_id, str) or _ID.fullmatch(action_id) is None:
                raise OperatorError(
                    "operator.recovery.catalog_invalid", "Recovery action ID is invalid."
                )
            if (
                not isinstance(fault_codes, list)
                or not fault_codes
                or not all(isinstance(item, str) and _ID.fullmatch(item) for item in fault_codes)
            ):
                raise OperatorError(
                    "operator.recovery.catalog_invalid", "Recovery fault codes are invalid."
                )
            if not isinstance(label, str) or not label.strip():
                raise OperatorError(
                    "operator.recovery.catalog_invalid", "Recovery label is invalid."
                )
            if not isinstance(instructions, str) or not instructions.strip():
                raise OperatorError(
                    "operator.recovery.catalog_invalid", "Recovery instructions are invalid."
                )
            if not isinstance(confirmation, str):
                raise OperatorError(
                    "operator.recovery.catalog_invalid", "Recovery confirmation is invalid."
                )
            try:
                kind = RecoveryKind(str(raw.get("kind")))
            except ValueError:
                raise OperatorError(
                    "operator.recovery.catalog_invalid", "Recovery kind is invalid."
                ) from None
            required_role = Role.parse(raw.get("required_role"))
            if kind is RecoveryKind.ENTER_MAINTENANCE and required_role < Role.MAINTAINER:
                raise OperatorError(
                    "operator.recovery.catalog_invalid", "Maintenance requires maintainer role."
                )
            actions.append(
                RecoveryAction(
                    action_id,
                    tuple(fault_codes),
                    kind,
                    label.strip(),
                    instructions.strip(),
                    required_role,
                    confirmation,
                )
            )
        return cls(tuple(actions))

    def require(self, action_id: str) -> RecoveryAction:
        try:
            return self._by_id[action_id]
        except KeyError:
            raise OperatorError(
                "operator.recovery.not_approved", "Recovery action is not approved."
            ) from None


@dataclass(frozen=True, slots=True)
class ActiveJob:
    job_id: str
    trace_id: str
    recipe_id: str
    recipe_version: int
    task_id: str
    execution_mode: str
    active_step: str = ""
    progress: float = 0.0


@dataclass(frozen=True, slots=True)
class FaultView:
    fault_id: str
    code: str
    component_instance_id: str
    severity: str
    operator_message: str
    recovery_action_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IdentityView:
    bundle_id: str
    recipe_id: str = ""
    recipe_version: int = 0
    task_id: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    cell_id: str
    state: str
    safety_healthy: bool
    all_required_devices_ready: bool
    identity: IdentityView
    active_job: ActiveJob | None = None
    faults: tuple[FaultView, ...] = ()
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stale: bool = False


@dataclass(frozen=True, slots=True)
class TraceSummary:
    trace_id: str
    job_id: str
    event_count: int
    first_sequence: int
    last_sequence: int
    final_event_type: str
    final_severity: str
    fault_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JobSubmission:
    job_id: str
    cell_id: str
    recipe_id: str
    recipe_version: int
    task_id: str
    input_payload: JsonObject
    execution_mode: str
    idempotency_key: str
    timeout_seconds: float

    @classmethod
    def from_document(cls, document: object) -> JobSubmission:
        if not isinstance(document, dict):
            raise OperatorError("operator.input.invalid", "Request body must be a JSON object.")
        required = {
            "job_id",
            "cell_id",
            "recipe_id",
            "recipe_version",
            "task_id",
            "input_payload",
            "execution_mode",
            "idempotency_key",
            "timeout_seconds",
        }
        if set(document) != required:
            raise OperatorError(
                "operator.input.invalid", "Job request fields are missing or unexpected."
            )
        values = [
            document[name]
            for name in ("job_id", "cell_id", "recipe_id", "task_id", "idempotency_key")
        ]
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise OperatorError("operator.input.invalid", "Job identifiers must not be empty.")
        recipe_version = document["recipe_version"]
        timeout_seconds = document["timeout_seconds"]
        if (
            not isinstance(recipe_version, int)
            or isinstance(recipe_version, bool)
            or recipe_version < 1
        ):
            raise OperatorError(
                "operator.input.invalid", "recipe_version must be a positive integer."
            )
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
            raise OperatorError("operator.input.invalid", "timeout_seconds must be numeric.")
        timeout = float(timeout_seconds)
        if not 0.05 <= timeout <= 86400.0:
            raise OperatorError(
                "operator.input.invalid", "timeout_seconds is outside allowed bounds."
            )
        payload = document["input_payload"]
        if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
            raise OperatorError("operator.input.invalid", "input_payload must be a JSON object.")
        mode = document["execution_mode"]
        if mode not in {"simulation", "commissioning", "production"}:
            raise OperatorError("operator.input.invalid", "execution_mode is invalid.")
        return cls(
            str(document["job_id"]),
            str(document["cell_id"]),
            str(document["recipe_id"]),
            recipe_version,
            str(document["task_id"]),
            payload,
            str(mode),
            str(document["idempotency_key"]),
            timeout,
        )

    def to_document(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OperationResult:
    success: bool
    code: str
    message: str
    trace_id: str = ""
    outcome_certain: bool = True

    def to_document(self) -> JsonObject:
        return asdict(self)


class RuntimePort(Protocol):
    async def snapshot(self) -> RuntimeSnapshot: ...

    async def trace_summary(self, trace_id: str) -> TraceSummary | None: ...

    async def submit_job(
        self, submission: JobSubmission, cancel_event: asyncio.Event
    ) -> OperationResult: ...

    async def cancel_job(self, job_id: str, cancel_event: asyncio.Event) -> OperationResult: ...

    async def perform_recovery(
        self,
        action: RecoveryAction,
        fault_id: str,
        principal: Principal,
        cancel_event: asyncio.Event,
    ) -> OperationResult: ...


@dataclass(frozen=True, slots=True)
class AuditEvent:
    sequence: int
    request_id: str
    principal_id: str
    role: str
    action: str
    resource: str
    outcome: str
    code: str
    details: JsonObject
    recorded_at: datetime


class SqliteAuditStore:
    """Append-only cell-local audit journal."""

    def __init__(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(target, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS operator_audit (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL,
              principal_id TEXT NOT NULL,
              role TEXT NOT NULL,
              action TEXT NOT NULL,
              resource TEXT NOT NULL,
              outcome TEXT NOT NULL,
              code TEXT NOT NULL,
              details_json TEXT NOT NULL,
              recorded_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()
        self._lock = threading.Lock()

    def record(
        self,
        *,
        request_id: str,
        principal: Principal | None,
        action: str,
        resource: str,
        outcome: str,
        code: str,
        details: JsonObject | None = None,
    ) -> int:
        safe_details = details or {}
        try:
            encoded = json.dumps(safe_details, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            raise OperatorError(
                "operator.audit.invalid", "Audit details are not canonical JSON."
            ) from None
        with self._lock:
            try:
                cursor = self._connection.execute(
                    "INSERT INTO operator_audit (request_id, principal_id, role, action, resource, "
                    "outcome, code, details_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        request_id,
                        principal.principal_id if principal else "anonymous",
                        principal.role.label if principal else "anonymous",
                        action,
                        resource,
                        outcome,
                        code,
                        encoded,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                self._connection.commit()
            except sqlite3.Error:
                raise OperatorError(
                    "operator.audit.unavailable", "Operator audit journal is unavailable."
                ) from None
            if cursor.lastrowid is None:
                raise OperatorError(
                    "operator.audit.unavailable", "Operator audit journal returned no sequence."
                )
            return int(cursor.lastrowid)

    def query(self, *, request_id: str | None = None) -> list[AuditEvent]:
        sql = (
            "SELECT sequence, request_id, principal_id, role, action, resource, outcome, code, "
            "details_json, recorded_at FROM operator_audit"
        )
        params: tuple[str, ...] = ()
        if request_id is not None:
            sql += " WHERE request_id = ?"
            params = (request_id,)
        sql += " ORDER BY sequence"
        rows = self._connection.execute(sql, params).fetchall()
        return [
            AuditEvent(
                int(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
                str(row[5]),
                str(row[6]),
                str(row[7]),
                json.loads(row[8]),
                datetime.fromisoformat(row[9]),
            )
            for row in rows
        ]

    def close(self) -> None:
        self._connection.close()


class OperatorService:
    """Authorization and audit boundary around the typed runtime port."""

    def __init__(
        self,
        authorizer: TokenAuthorizer,
        catalog: RecoveryCatalog,
        audit: SqliteAuditStore,
        runtime: RuntimePort,
    ) -> None:
        self.authorizer = authorizer
        self.catalog = catalog
        self.audit = audit
        self.runtime = runtime

    def authenticate(self, token: str) -> Principal:
        return self.authorizer.authenticate(token)

    async def status(self, principal: Principal) -> RuntimeSnapshot:
        self._require_role(principal, Role.VIEWER)
        return await self.runtime.snapshot()

    async def trace_summary(self, principal: Principal, trace_id: str) -> TraceSummary | None:
        self._require_role(principal, Role.VIEWER)
        if not trace_id or len(trace_id) > 128:
            raise OperatorError("operator.input.invalid", "Trace ID is invalid.")
        return await self.runtime.trace_summary(trace_id)

    async def submit(
        self, principal: Principal, submission: JobSubmission, request_id: str | None = None
    ) -> OperationResult:
        self._require_role(principal, Role.OPERATOR)
        return await self._mutate(
            principal,
            "job.submit",
            submission.job_id,
            submission.timeout_seconds,
            lambda cancel: self.runtime.submit_job(submission, cancel),
            request_id,
            {"cell_id": submission.cell_id, "execution_mode": submission.execution_mode},
        )

    async def cancel_job(
        self,
        principal: Principal,
        job_id: str,
        *,
        timeout_seconds: float = 5.0,
        request_id: str | None = None,
    ) -> OperationResult:
        self._require_role(principal, Role.OPERATOR)
        if not job_id or len(job_id) > 128:
            raise OperatorError("operator.input.invalid", "Job ID is invalid.")
        return await self._mutate(
            principal,
            "job.cancel",
            job_id,
            timeout_seconds,
            lambda cancel: self.runtime.cancel_job(job_id, cancel),
            request_id,
        )

    async def recover(
        self,
        principal: Principal,
        action_id: str,
        fault_id: str,
        confirmation: str,
        *,
        timeout_seconds: float = 10.0,
        request_id: str | None = None,
    ) -> OperationResult:
        action = self.catalog.require(action_id)
        self._require_role(principal, action.required_role)
        snapshot = await self.runtime.snapshot()
        fault = next((item for item in snapshot.faults if item.fault_id == fault_id), None)
        if fault is None or fault.code not in action.fault_codes:
            raise OperatorError(
                "operator.recovery.not_applicable",
                "Recovery action is not approved for this fault.",
            )
        if action.action_id not in fault.recovery_action_ids:
            raise OperatorError(
                "operator.recovery.not_applicable", "Fault does not offer this recovery action."
            )
        if action.confirmation and not hmac.compare_digest(confirmation, action.confirmation):
            raise OperatorError(
                "operator.recovery.confirmation_invalid", "Recovery confirmation does not match."
            )
        return await self._mutate(
            principal,
            f"recovery.{action.kind.value}",
            fault_id,
            timeout_seconds,
            lambda cancel: self.runtime.perform_recovery(action, fault_id, principal, cancel),
            request_id,
            {"action_id": action.action_id, "fault_code": fault.code},
        )

    def audit_rejection(
        self,
        *,
        principal: Principal | None,
        action: str,
        resource: str,
        code: str,
        request_id: str | None = None,
    ) -> None:
        self.audit.record(
            request_id=request_id or str(uuid4()),
            principal=principal,
            action=action,
            resource=resource,
            outcome="DENIED",
            code=code,
        )

    @staticmethod
    def _require_role(principal: Principal, required: Role) -> None:
        if principal.role < required:
            raise OperatorError(
                "operator.auth.forbidden", f"The {required.label} role is required."
            )

    async def _mutate(
        self,
        principal: Principal,
        action: str,
        resource: str,
        timeout_seconds: float,
        operation: Callable[[asyncio.Event], Awaitable[OperationResult]],
        request_id: str | None,
        details: JsonObject | None = None,
    ) -> OperationResult:
        audit_id = request_id or str(uuid4())
        self.audit.record(
            request_id=audit_id,
            principal=principal,
            action=action,
            resource=resource,
            outcome="REQUESTED",
            code="operator.action.requested",
            details=details,
        )
        cancel_event = asyncio.Event()
        try:
            result = await asyncio.wait_for(operation(cancel_event), timeout=timeout_seconds)
        except TimeoutError:
            cancel_event.set()
            result = OperationResult(
                False,
                "operator.action.timeout",
                "The runtime did not complete before the local deadline; outcome may be uncertain.",
                outcome_certain=False,
            )
            outcome = "TIMED_OUT"
        except asyncio.CancelledError:
            cancel_event.set()
            self.audit.record(
                request_id=audit_id,
                principal=principal,
                action=action,
                resource=resource,
                outcome="CANCELLED",
                code="operator.action.cancelled",
            )
            raise
        except Exception:
            result = OperationResult(
                False,
                "operator.runtime.failure",
                "The local runtime operation failed.",
                outcome_certain=False,
            )
            outcome = "FAILED"
        else:
            outcome = "COMPLETED" if result.success else "FAILED"
        self.audit.record(
            request_id=audit_id,
            principal=principal,
            action=action,
            resource=resource,
            outcome=outcome,
            code=result.code,
            details={"outcome_certain": result.outcome_certain, "trace_id": result.trace_id},
        )
        return result
