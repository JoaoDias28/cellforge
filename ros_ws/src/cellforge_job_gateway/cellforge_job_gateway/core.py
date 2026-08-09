"""Pure, durable job-freezing and idempotency contracts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

JsonObject = dict[str, Any]
_EXECUTION_MODES = {"simulation", "commissioning", "production"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODE_RECIPE_STATUSES = {
    "simulation": {"DRAFT", "VALIDATED", "TESTED", "APPROVED"},
    "commissioning": {"TESTED", "APPROVED"},
    "production": {"APPROVED"},
}


class GatewayError(Exception):
    """A stable, sanitized gateway rejection."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class JobRequest:
    job_id: str
    cell_id: str
    recipe_id: str
    recipe_version: int
    task_id: str
    input_payload_json: str
    execution_mode: str
    idempotency_key: str

    def validated_payload(self) -> JsonObject:
        for field_name in (
            "job_id",
            "cell_id",
            "recipe_id",
            "task_id",
            "idempotency_key",
        ):
            if not getattr(self, field_name).strip():
                raise GatewayError("gateway.job.invalid", f"{field_name} must not be empty.")
        if self.recipe_version < 1:
            raise GatewayError("gateway.job.invalid", "recipe_version must be at least one.")
        if self.execution_mode not in _EXECUTION_MODES:
            raise GatewayError(
                "gateway.mode.invalid",
                f"Unsupported execution mode '{self.execution_mode}'.",
            )
        try:
            payload: object = json.loads(self.input_payload_json)
        except (json.JSONDecodeError, TypeError):
            raise GatewayError(
                "gateway.payload.invalid", "input_payload_json must contain valid JSON."
            ) from None
        if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
            raise GatewayError(
                "gateway.payload.invalid", "input_payload_json must contain a JSON object."
            )
        return payload

    def canonical_document(self) -> JsonObject:
        document = asdict(self)
        document["input_payload"] = self.validated_payload()
        del document["input_payload_json"]
        return document

    @property
    def request_hash(self) -> str:
        return _sha256(_canonical_bytes(self.canonical_document()))


@dataclass(frozen=True, slots=True)
class FrozenJob:
    request: JobRequest
    request_hash: str
    trace_id: str
    bundle_id: str
    recipe_sha256: str
    task_sha256: str
    recipe: JsonObject

    def to_document(self) -> JsonObject:
        return {
            "schema_version": "0.1.0",
            "job": self.request.canonical_document(),
            "request_hash": self.request_hash,
            "trace_id": self.trace_id,
            "bundle_id": self.bundle_id,
            "recipe_sha256": self.recipe_sha256,
            "task_sha256": self.task_sha256,
            "recipe": self.recipe,
        }


@dataclass(frozen=True, slots=True)
class JobResult:
    success: bool
    result_code: str
    result_message: str
    output_payload_json: str
    trace_id: str

    def to_document(self) -> JsonObject:
        return asdict(self)

    @classmethod
    def from_document(cls, document: JsonObject) -> JobResult:
        return cls(
            success=bool(document["success"]),
            result_code=str(document["result_code"]),
            result_message=str(document["result_message"]),
            output_payload_json=str(document["output_payload_json"]),
            trace_id=str(document["trace_id"]),
        )


class PrepareKind(StrEnum):
    NEW = "new"
    REPLAY = "replay"


@dataclass(frozen=True, slots=True)
class PrepareDecision:
    kind: PrepareKind
    frozen_job: FrozenJob | None = None
    result: JobResult | None = None


class BundleResolver:
    """Resolve exact immutable inputs from one active bundle."""

    def __init__(
        self, bundle_root: str | Path, manifest_path: str | Path = "manifest.json"
    ) -> None:
        self.bundle_root = Path(bundle_root).resolve()
        self.manifest_path = self._contained_path(str(manifest_path))
        self.manifest = self._load_manifest()

    def freeze(self, request: JobRequest, trace_id: str) -> FrozenJob:
        payload = request.validated_payload()
        del payload  # Validation is intentional; canonicalization happens in FrozenJob.
        manifest = self.manifest
        if str(manifest.get("cell_id", "")) != request.cell_id:
            raise GatewayError("gateway.compatibility.cell", "Job cell does not match the bundle.")
        bundle_mode = manifest.get("execution_mode")
        if bundle_mode != request.execution_mode:
            raise GatewayError(
                "gateway.compatibility.mode",
                "Requested execution mode does not match the active immutable bundle.",
            )

        recipe_ref = self._unique_reference(
            manifest.get("recipes"),
            lambda item: (
                item.get("id") == request.recipe_id
                and item.get("version") == request.recipe_version
            ),
            "gateway.recipe.not_found",
            "Exact recipe version is not present in the active bundle.",
        )
        task_ref = self._unique_reference(
            manifest.get("tasks"),
            lambda item: item.get("id") == request.task_id,
            "gateway.task.not_found",
            "Exact task version is not present in the active bundle.",
        )
        recipe_bytes = self._verified_file(recipe_ref, "recipe")
        task_bytes = self._verified_file(task_ref, "task")
        recipe = self._parse_recipe(recipe_bytes)
        self._validate_recipe(request, recipe, recipe_ref)
        self._validate_capabilities(request.task_id, recipe)
        bundle_id = str(manifest["bundle_id"])
        recipe_sha256 = _sha256(recipe_bytes)
        task_sha256 = _sha256(task_bytes)
        frozen_request_hash = _sha256(
            _canonical_bytes(
                {
                    "request": request.canonical_document(),
                    "bundle_id": bundle_id,
                    "recipe_sha256": recipe_sha256,
                    "task_sha256": task_sha256,
                }
            )
        )
        return FrozenJob(
            request=request,
            request_hash=frozen_request_hash,
            trace_id=trace_id,
            bundle_id=bundle_id,
            recipe_sha256=recipe_sha256,
            task_sha256=task_sha256,
            recipe=recipe,
        )

    def _load_manifest(self) -> JsonObject:
        try:
            raw = self.manifest_path.read_bytes()
            document: object = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            raise GatewayError(
                "gateway.bundle.invalid", "Active bundle manifest is missing or invalid."
            ) from None
        if not isinstance(document, dict):
            raise GatewayError("gateway.bundle.invalid", "Bundle manifest must be a JSON object.")
        bundle_id = document.get("bundle_id")
        if not isinstance(bundle_id, str) or _SHA256.fullmatch(bundle_id) is None:
            raise GatewayError("gateway.bundle.invalid", "Bundle manifest has no valid bundle ID.")
        hash_input = dict(document)
        del hash_input["bundle_id"]
        if _sha256(_canonical_bytes(hash_input)) != bundle_id:
            raise GatewayError(
                "gateway.bundle.digest_mismatch", "Bundle manifest content does not match its ID."
            )
        return document

    def _contained_path(self, relative_path: str) -> Path:
        candidate = (self.bundle_root / relative_path).resolve()
        try:
            candidate.relative_to(self.bundle_root)
        except ValueError:
            raise GatewayError(
                "gateway.bundle.path_invalid", "Bundle reference escapes the active bundle root."
            ) from None
        return candidate

    def _verified_file(self, reference: JsonObject, kind: str) -> bytes:
        path = reference.get("path")
        digest = reference.get("sha256")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
        ):
            raise GatewayError(f"gateway.{kind}.invalid", f"Bundle {kind} reference is incomplete.")
        source = self._contained_path(path)
        try:
            content = source.read_bytes()
        except OSError:
            raise GatewayError(
                f"gateway.{kind}.unavailable", f"Frozen {kind} content is unavailable."
            ) from None
        if _sha256(content) != digest:
            raise GatewayError(
                f"gateway.{kind}.digest_mismatch",
                f"Frozen {kind} content does not match the bundle manifest.",
            )
        return content

    @staticmethod
    def _unique_reference(
        references: object,
        predicate: Callable[[JsonObject], bool],
        code: str,
        message: str,
    ) -> JsonObject:
        if not isinstance(references, list):
            raise GatewayError("gateway.bundle.invalid", "Bundle reference list is invalid.")
        matches = [item for item in references if isinstance(item, dict) and predicate(item)]
        if len(matches) != 1:
            raise GatewayError(code, message)
        return matches[0]

    @staticmethod
    def _parse_recipe(content: bytes) -> JsonObject:
        try:
            document: object = yaml.safe_load(content)
        except (UnicodeDecodeError, yaml.YAMLError):
            raise GatewayError("gateway.recipe.invalid", "Frozen recipe is invalid YAML.") from None
        if not isinstance(document, dict):
            raise GatewayError("gateway.recipe.invalid", "Frozen recipe must be a mapping.")
        return document

    @staticmethod
    def _validate_recipe(request: JobRequest, recipe: JsonObject, reference: JsonObject) -> None:
        identity = recipe.get("recipe")
        compatibility = recipe.get("compatibility")
        if not isinstance(identity, dict) or not isinstance(compatibility, dict):
            raise GatewayError(
                "gateway.recipe.invalid", "Recipe identity or compatibility is invalid."
            )
        status = identity.get("status")
        if (
            identity.get("id") != request.recipe_id
            or identity.get("version") != request.recipe_version
            or reference.get("status") != status
        ):
            raise GatewayError(
                "gateway.recipe.identity_mismatch",
                "Recipe content does not match its frozen manifest reference.",
            )
        if status not in _MODE_RECIPE_STATUSES[request.execution_mode]:
            raise GatewayError(
                "gateway.recipe.status_not_allowed",
                f"Recipe status '{status}' is not allowed in {request.execution_mode} mode.",
            )
        if request.execution_mode != "simulation":
            product = recipe.get("product")
            material = product.get("material") if isinstance(product, dict) else None
            if not isinstance(material, str) or not material.strip() or material == "unknown":
                raise GatewayError(
                    "gateway.recipe.material_unknown",
                    "A known material classification is required for physical execution.",
                )
        cell_ids = compatibility.get("cell_ids")
        if not isinstance(cell_ids, list) or request.cell_id not in cell_ids:
            raise GatewayError(
                "gateway.recipe.cell_incompatible",
                "Recipe is not compatible with the requested cell.",
            )

    def _validate_capabilities(self, task_id: str, recipe: JsonObject) -> None:
        compatibility = recipe["compatibility"]
        assert isinstance(compatibility, dict)
        required = compatibility.get("required_capabilities")
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise GatewayError(
                "gateway.recipe.invalid", "Recipe required capabilities are invalid."
            )
        capabilities = self.manifest.get("capabilities")
        if not isinstance(capabilities, list):
            raise GatewayError("gateway.bundle.invalid", "Bundle capabilities are invalid.")
        provided = {
            str(item["contract"])
            for item in capabilities
            if isinstance(item, dict)
            and item.get("task_id") == task_id
            and isinstance(item.get("contract"), str)
        }
        missing = sorted(set(required) - provided)
        if missing:
            raise GatewayError(
                "gateway.recipe.capability_incompatible",
                "Recipe requires capabilities not frozen for the requested task: "
                + ", ".join(missing),
            )


class SqliteJobStore:
    """Durable idempotency and frozen-result store."""

    def __init__(self, database: str | Path) -> None:
        path = Path(database)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              idempotency_key TEXT PRIMARY KEY,
              request_hash TEXT NOT NULL,
              status TEXT NOT NULL,
              frozen_json TEXT NOT NULL,
              result_json TEXT
            )
            """
        )
        self._reconcile_restart()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def prepare(self, frozen: FrozenJob) -> PrepareDecision:
        frozen_json = _canonical_text(frozen.to_document())
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT request_hash, status, result_json FROM jobs WHERE idempotency_key = ?",
                    (frozen.request.idempotency_key,),
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        "INSERT INTO jobs VALUES (?, ?, 'PREPARED', ?, NULL)",
                        (frozen.request.idempotency_key, frozen.request_hash, frozen_json),
                    )
                    self._connection.execute("COMMIT")
                    return PrepareDecision(PrepareKind.NEW, frozen_job=frozen)
                request_hash, status, result_json = row
                if request_hash != frozen.request_hash:
                    raise GatewayError(
                        "gateway.idempotency.conflict",
                        "Idempotency key was already used with a different job payload.",
                    )
                if result_json is not None:
                    result_doc: object = json.loads(result_json)
                    if not isinstance(result_doc, dict):
                        raise GatewayError(
                            "gateway.store.corrupt", "Persisted result record is invalid."
                        )
                    self._connection.execute("COMMIT")
                    return PrepareDecision(
                        PrepareKind.REPLAY, result=JobResult.from_document(result_doc)
                    )
                raise GatewayError(
                    "gateway.idempotency.active",
                    f"The matching job is already in nonterminal state {status}.",
                )
            except BaseException:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def mark_running(self, idempotency_key: str) -> None:
        self._set_status(idempotency_key, "RUNNING")

    def finish(self, idempotency_key: str, result: JobResult) -> None:
        result_json = _canonical_text(result.to_document())
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE jobs SET status = 'TERMINAL', result_json = ? "
                "WHERE idempotency_key = ? AND result_json IS NULL",
                (result_json, idempotency_key),
            )
            if cursor.rowcount != 1:
                raise GatewayError("gateway.store.missing", "Frozen job record is missing.")

    def read(self, idempotency_key: str) -> tuple[str, JsonObject, JobResult | None]:
        with self._lock:
            row = self._connection.execute(
                "SELECT status, frozen_json, result_json FROM jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            raise GatewayError("gateway.store.missing", "Frozen job record is missing.")
        status, frozen_json, result_json = row
        frozen_doc: object = json.loads(frozen_json)
        if not isinstance(frozen_doc, dict):
            raise GatewayError("gateway.store.corrupt", "Persisted frozen record is invalid.")
        result: JobResult | None = None
        if result_json is not None:
            result_doc: object = json.loads(result_json)
            if not isinstance(result_doc, dict):
                raise GatewayError("gateway.store.corrupt", "Persisted result record is invalid.")
            result = JobResult.from_document(result_doc)
        return str(status), frozen_doc, result

    def _set_status(self, idempotency_key: str, status: str) -> None:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE jobs SET status = ? WHERE idempotency_key = ? AND result_json IS NULL",
                (status, idempotency_key),
            )
            if cursor.rowcount != 1:
                raise GatewayError("gateway.store.missing", "Mutable frozen job record is missing.")

    def _reconcile_restart(self) -> None:
        with self._lock:
            rows = self._connection.execute(
                "SELECT idempotency_key, frozen_json FROM jobs "
                "WHERE status IN ('PREPARED', 'RUNNING') AND result_json IS NULL"
            ).fetchall()
            for key, frozen_json in rows:
                frozen: object = json.loads(frozen_json)
                trace_id = str(frozen.get("trace_id", "")) if isinstance(frozen, dict) else ""
                result = JobResult(
                    success=False,
                    result_code="gateway.restart.outcome_unknown",
                    result_message=(
                        "Gateway restarted before durable completion; job will not be replayed "
                        "automatically."
                    ),
                    output_payload_json="{}",
                    trace_id=trace_id,
                )
                self._connection.execute(
                    "UPDATE jobs SET status = 'OUTCOME_UNKNOWN', result_json = ? "
                    "WHERE idempotency_key = ?",
                    (_canonical_text(result.to_document()), key),
                )


def _canonical_bytes(document: JsonObject) -> bytes:
    return _canonical_text(document).encode("utf-8")


def _canonical_text(document: JsonObject) -> str:
    try:
        return json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        raise GatewayError("gateway.payload.invalid", "Document is not canonical JSON.") from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
