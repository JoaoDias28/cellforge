"""Deterministic, preview-first readiness guidance for Cell Studio.

The readiness report is derived from canonical project sources and existing pure validators.  It
is intentionally a diagnostic application service: it does not become a compiler/runtime
authority, does not implement a safety function, and does not write project files.  Candidate
buffers may be previewed and are persisted only after an explicit confirmation through the
existing :class:`ProjectCommandService` transaction.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import yaml
from cellforge_cli.projects import resolve_project_schema_directory
from cellforge_domain import (
    CellProject,
    ExecutionMode,
    FilesystemComponentRegistry,
    SchemaDocumentKind,
    SchemaRegistry,
    resolve_cell,
)
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from cellforge.studio.application import (
    BackendResult,
    ProjectContents,
    ValidationItem,
)
from cellforge.studio.project_service import ProjectCommandService, ProjectSaveError

READINESS_SCHEMA_VERSION = "0.1.0"
SAFETY_REVIEW_DISCLAIMER = (
    "Readiness is engineering guidance only. It is not functional-safety validation and cannot "
    "authorize physical operation; rated safety hardware and independent safety processes remain "
    "the authority."
)
_STATUS_ORDER = {"blocked": 0, "unavailable": 1, "advisory": 2, "pass": 3}
_FIDELITY_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
_TRANSIENT_NAMES = {".git", ".venv", "__pycache__", ".pytest_cache", ".pytest_tmp"}


class ReadinessStatus(StrEnum):
    """Stable status values rendered by the readiness panel."""

    PASS = "pass"
    BLOCKED = "blocked"
    ADVISORY = "advisory"
    UNAVAILABLE = "unavailable"


class ReadinessSeverity(StrEnum):
    """Presentation-neutral severity associated with one readiness check."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ReadinessCategory(StrEnum):
    """Deterministic check groups used by the report and Studio panel."""

    CANONICAL = "canonical"
    SCHEMA = "schema"
    COMPONENTS = "components"
    PORTS = "ports"
    ASSETS = "assets"
    TASKS = "tasks"
    RECIPES = "recipes"
    SCENARIOS = "scenarios"
    ADAPTERS = "adapters"
    FIDELITY = "fidelity"
    CALIBRATION = "calibration"
    EVIDENCE = "evidence"
    DEPLOYMENT = "deployment"
    SAFETY_REVIEW = "safety_review"
    BACKEND = "backend"


@dataclass(frozen=True, slots=True)
class StudioProjectIdentity:
    """Stable identity and source digests for the selected project."""

    path: str
    cell_id: str | None
    name: str | None
    scene_path: str | None
    source_hashes: Mapping[str, str] = field(default_factory=dict)

    @property
    def cell_sha256(self) -> str | None:
        """Return the canonical cell digest when it is present."""

        return self.source_hashes.get("cell.yaml")

    @property
    def scene_sha256(self) -> str | None:
        """Return the canonical scene digest when it is present."""

        if self.scene_path is None:
            return None
        return self.source_hashes.get(self.scene_path)

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "cell_id": self.cell_id,
            "name": self.name,
            "scene_path": self.scene_path,
            "source_hashes": dict(sorted(self.source_hashes.items())),
        }


@dataclass(frozen=True, slots=True)
class StudioReadinessCheck:
    """One source-linked deterministic readiness result."""

    check_id: str
    category: str
    status: ReadinessStatus | str
    severity: ReadinessSeverity | str
    source_reference: str
    message: str
    remediation_id: str | None = None
    evidence_references: tuple[str, ...] = ()
    validator_link: str | None = None
    finding_id: str | None = None

    @property
    def source(self) -> str:
        """Compatibility alias used by panel and report consumers."""

        return self.source_reference

    @property
    def remediation(self) -> str | None:
        """Compatibility alias for the stable remediation identifier."""

        return self.remediation_id

    @property
    def status_value(self) -> str:
        return str(self.status)

    @property
    def severity_value(self) -> str:
        return str(self.severity)

    def as_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "category": str(self.category),
            "status": self.status_value,
            "severity": self.severity_value,
            "source_reference": self.source_reference,
            "message": self.message,
            "remediation_id": self.remediation_id,
            "evidence_references": list(self.evidence_references),
            "validator_link": self.validator_link,
            "finding_id": self.finding_id,
        }


@dataclass(frozen=True, slots=True)
class StudioReadinessSummary:
    """Normalized counts and the engineering-guidance outcome."""

    overall_status: ReadinessStatus | str
    total: int
    pass_count: int
    blocked_count: int
    advisory_count: int
    unavailable_count: int
    ready_for_simulation: bool
    safety_disclaimer: str = SAFETY_REVIEW_DISCLAIMER

    @property
    def is_ready(self) -> bool:
        """Return whether no required software prerequisite is blocked or unavailable."""

        return self.ready_for_simulation

    def as_dict(self) -> dict[str, object]:
        return {
            "overall_status": str(self.overall_status),
            "total": self.total,
            "pass_count": self.pass_count,
            "blocked_count": self.blocked_count,
            "advisory_count": self.advisory_count,
            "unavailable_count": self.unavailable_count,
            "ready_for_simulation": self.ready_for_simulation,
            "safety_disclaimer": self.safety_disclaimer,
        }


@dataclass(frozen=True, slots=True)
class StudioReadinessReport:
    """Machine-readable diagnostic readiness report without wall-clock fields."""

    project_identity: StudioProjectIdentity
    checks: tuple[StudioReadinessCheck, ...]
    summary: StudioReadinessSummary
    requested_fidelity: str
    observed_fidelity: str

    @property
    def status(self) -> ReadinessStatus | str:
        """Return the aggregate report status."""

        return self.summary.overall_status

    @property
    def is_ready(self) -> bool:
        return self.summary.ready_for_simulation

    @property
    def blocked(self) -> tuple[StudioReadinessCheck, ...]:
        return tuple(check for check in self.checks if str(check.status) == "blocked")

    @property
    def unavailable(self) -> tuple[StudioReadinessCheck, ...]:
        return tuple(check for check in self.checks if str(check.status) == "unavailable")

    def as_dict(self) -> dict[str, object]:
        """Return a recursively sorted, schema-compatible JSON document."""

        return {
            "report_schema_version": READINESS_SCHEMA_VERSION,
            "project_identity": self.project_identity.as_dict(),
            "checks": [check.as_dict() for check in self.checks],
            "summary": self.summary.as_dict(),
            "requested_fidelity": self.requested_fidelity,
            "observed_fidelity": self.observed_fidelity,
        }

    def normalized(self) -> dict[str, object]:
        """Return the deterministic report mapping used for replay comparisons."""

        return cast(dict[str, object], _sorted_json_value(self.as_dict()))

    def to_dict(self) -> dict[str, object]:
        return self.normalized()

    def to_json(self) -> str:
        return json.dumps(self.normalized(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class ReadinessBackendProbe:
    """Explicit observation supplied by a simulation/backend adapter.

    The default observation is the deterministic CPU/L0 path.  Higher fidelity is accepted only
    when the caller proves the corresponding runtime, GPU, and actual PhysX execution facts.
    """

    available: bool = True
    observed_fidelity: str = "L0"
    isaac_sim_available: bool = False
    cuda_gpu_available: bool = False
    actual_physx_executed: bool = False
    detail: str = "Deterministic CPU adapter observation (L0)."

    @property
    def fidelity(self) -> str:
        """Compatibility alias for adapters that call this field ``fidelity``."""

        return self.observed_fidelity


@dataclass(frozen=True, slots=True)
class ReadinessRemediation:
    """Safe next action linked from a check; actions are preview-only by construction."""

    remediation_id: str
    title: str
    description: str
    action: str
    source_reference: str

    @property
    def id(self) -> str:
        return self.remediation_id

    def as_dict(self) -> dict[str, str]:
        return {
            "remediation_id": self.remediation_id,
            "title": self.title,
            "description": self.description,
            "action": self.action,
            "source_reference": self.source_reference,
        }


@dataclass(frozen=True, slots=True)
class ReadinessCandidatePreview:
    """In-memory remediation candidate and its explicit Save token."""

    project_path: str
    remediation_id: str
    linked_check_ids: tuple[str, ...]
    candidate_contents: ProjectContents
    report: StudioReadinessReport
    source_hashes_before: Mapping[str, str]
    candidate_hashes: Mapping[str, str]
    confirmation_token: str
    can_save: bool

    @property
    def contents(self) -> ProjectContents:
        """Compatibility alias for the staged candidate buffers."""

        return self.candidate_contents

    @property
    def save_token(self) -> str:
        return self.confirmation_token

    @property
    def findings(self) -> tuple[StudioReadinessCheck, ...]:
        return self.report.checks

    def as_dict(self) -> dict[str, object]:
        return {
            "project_path": self.project_path,
            "remediation_id": self.remediation_id,
            "linked_check_ids": list(self.linked_check_ids),
            "report": self.report.normalized(),
            "source_hashes_before": dict(sorted(self.source_hashes_before.items())),
            "candidate_hashes": dict(sorted(self.candidate_hashes.items())),
            "confirmation_token": self.confirmation_token,
            "can_save": self.can_save,
        }

    def to_json(self) -> str:
        return json.dumps(_sorted_json_value(self.as_dict()), sort_keys=True, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class ReadinessSaveResult:
    """Explicit Save-after-preview outcome."""

    success: bool
    report: StudioReadinessReport
    validation: tuple[ValidationItem, ...] = ()
    message: str = ""
    source_hashes_before: Mapping[str, str] = field(default_factory=dict)
    source_hashes_after: Mapping[str, str] = field(default_factory=dict)

    @property
    def findings(self) -> tuple[ValidationItem, ...]:
        return self.validation


class EvaluateStudioReadiness:
    """Pure readiness command over canonical or in-memory Studio project sources."""

    def __init__(
        self,
        canonical_schema_directory: Path,
        *,
        project_service: ProjectCommandService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._schemas = canonical_schema_directory.resolve()
        self._project_service = project_service or ProjectCommandService(self._schemas)
        self._clock = clock or (lambda: datetime.now(UTC))

    def EvaluateStudioReadiness(
        self,
        project_path: str | Path,
        *,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
        contents: ProjectContents | None = None,
        candidate_contents: ProjectContents | None = None,
    ) -> StudioReadinessReport:
        """Evaluate a project without modifying canonical or diagnostic files."""

        root = Path(project_path).expanduser().resolve()
        candidate = candidate_contents if candidate_contents is not None else contents
        requested = _fidelity_name(requested_fidelity)
        probe = backend_probe or ReadinessBackendProbe()
        with self._candidate_root(root, candidate) as service_root:
            effective_contents = candidate
            try:
                result = self._inspect(service_root, candidate is not None)
                if effective_contents is None:
                    effective_contents = result.contents
                return self._build_report(
                    root,
                    service_root,
                    effective_contents,
                    result,
                    requested,
                    probe,
                )
            except Exception as error:  # Keep the diagnostic panel responsive on adapter errors.
                return self._backend_failure_report(
                    root,
                    effective_contents,
                    requested,
                    probe,
                    error,
                )

    def evaluate(self, project_path: str | Path, **kwargs: Any) -> StudioReadinessReport:
        """Snake-case command alias."""

        return self.EvaluateStudioReadiness(project_path, **kwargs)

    def __call__(self, project_path: str | Path, **kwargs: Any) -> StudioReadinessReport:
        return self.EvaluateStudioReadiness(project_path, **kwargs)

    def PreviewStudioReadinessRemediation(
        self,
        project_path: str | Path,
        remediation_id: str,
        *,
        candidate_contents: ProjectContents | None = None,
        contents: ProjectContents | None = None,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
        linked_check_ids: Sequence[str] = (),
    ) -> ReadinessCandidatePreview:
        """Stage and evaluate an explicit candidate without writing any source file."""

        root = Path(project_path).expanduser().resolve()
        current_result = self._project_service.inspect(root)
        source_contents = current_result.contents
        candidate = candidate_contents if candidate_contents is not None else contents
        if candidate is None:
            candidate = source_contents
        if candidate is None:
            candidate = ProjectContents(cell_yaml="", scene_usda="")
        before = _source_hashes(root, source_contents)
        candidate_hashes = _content_hashes(candidate)
        report = self.EvaluateStudioReadiness(
            root,
            requested_fidelity=requested_fidelity,
            backend_probe=backend_probe,
            candidate_contents=candidate,
        )
        linked = tuple(sorted(set(linked_check_ids)))
        if not linked:
            linked = tuple(
                check.check_id for check in report.checks if check.remediation_id == remediation_id
            )
        token = _preview_token(root, remediation_id, before, candidate_hashes, report)
        can_save = (
            bool(candidate_contents is not None or contents is not None)
            and bool(report.summary.blocked_count == 0)
            and bool(report.summary.unavailable_count == 0)
        )
        return ReadinessCandidatePreview(
            project_path=str(root),
            remediation_id=remediation_id,
            linked_check_ids=linked,
            candidate_contents=candidate,
            report=report,
            source_hashes_before=before,
            candidate_hashes=candidate_hashes,
            confirmation_token=token,
            can_save=can_save,
        )

    def preview_remediation(
        self, project_path: str | Path, remediation_id: str, **kwargs: Any
    ) -> ReadinessCandidatePreview:
        """Snake-case remediation preview alias."""

        return self.PreviewStudioReadinessRemediation(project_path, remediation_id, **kwargs)

    def SaveStudioReadiness(
        self,
        preview: ReadinessCandidatePreview,
        confirmation_token: str | None = None,
        *,
        confirmed: bool = False,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
    ) -> ReadinessSaveResult:
        """Persist a confirmed candidate through the existing transactional project service."""

        root = Path(preview.project_path).expanduser().resolve()
        try:
            current = self._project_service.inspect(root)
            current_contents = current.contents
        except Exception:
            current_contents = None
        before = _source_hashes(root, current_contents)
        invalid = self._save_guard(preview, before, confirmation_token, confirmed)
        if invalid is not None:
            report = self.EvaluateStudioReadiness(
                root,
                requested_fidelity=requested_fidelity,
                backend_probe=backend_probe,
            )
            return ReadinessSaveResult(
                success=False,
                report=report,
                validation=(invalid,),
                message=invalid.message,
                source_hashes_before=before,
                source_hashes_after=_source_hashes(root, current_contents),
            )
        current_report = self.EvaluateStudioReadiness(
            root,
            requested_fidelity=requested_fidelity,
            backend_probe=backend_probe,
            candidate_contents=preview.candidate_contents,
        )
        if current_report.summary.blocked_count or current_report.summary.unavailable_count:
            finding = ValidationItem(
                code="studio.readiness.save-blocked",
                severity="error",
                path=f"{root}#",
                message="Save-after-preview is blocked until the complete candidate is ready.",
            )
            return ReadinessSaveResult(
                success=False,
                report=current_report,
                validation=(finding,),
                message=finding.message,
                source_hashes_before=before,
                source_hashes_after=_source_hashes(root, current_contents),
            )
        try:
            result = self._project_service.save(root, preview.candidate_contents)
        except (OSError, ProjectSaveError, RuntimeError) as error:
            finding = ValidationItem(
                code="studio.readiness.save-failed",
                severity="error",
                path=f"{root}#",
                message=(
                    f"Save-after-preview failed ({type(error).__name__}); the transactional "
                    "project service was asked to preserve the previous sources."
                ),
            )
            after = _source_hashes(root, current_contents)
            return ReadinessSaveResult(
                success=False,
                report=self.EvaluateStudioReadiness(root, requested_fidelity=requested_fidelity),
                validation=(finding,),
                message=finding.message,
                source_hashes_before=before,
                source_hashes_after=after,
            )
        if result.project is None or result.contents is None or result.validation:
            validation = tuple(result.validation) or (
                ValidationItem(
                    code="studio.readiness.save-rejected",
                    severity="error",
                    path=f"{root}#",
                    message="The existing project transaction rejected the candidate.",
                ),
            )
            return ReadinessSaveResult(
                success=False,
                report=self.EvaluateStudioReadiness(root, requested_fidelity=requested_fidelity),
                validation=validation,
                message="Save-after-preview was rejected; canonical files were not accepted.",
                source_hashes_before=before,
                source_hashes_after=_source_hashes(root, current_contents),
            )
        after = _source_hashes(root, result.contents)
        return ReadinessSaveResult(
            success=True,
            report=self.EvaluateStudioReadiness(
                root,
                requested_fidelity=requested_fidelity,
                backend_probe=backend_probe,
            ),
            message="Save-after-preview committed through the existing transactional boundary.",
            source_hashes_before=before,
            source_hashes_after=after,
        )

    def save_after_preview(
        self, preview: ReadinessCandidatePreview, **kwargs: Any
    ) -> ReadinessSaveResult:
        """Snake-case explicit Save alias."""

        return self.SaveStudioReadiness(preview, **kwargs)

    def remediations(self, report: StudioReadinessReport) -> tuple[ReadinessRemediation, ...]:
        """Return stable, preview-only next actions represented by a report."""

        unique: dict[str, ReadinessRemediation] = {}
        for check in report.checks:
            if not check.remediation_id:
                continue
            remediation_id = check.remediation_id
            unique.setdefault(
                remediation_id,
                ReadinessRemediation(
                    remediation_id=remediation_id,
                    title=_remediation_title(remediation_id),
                    description=_remediation_description(remediation_id),
                    action="preview_only",
                    source_reference=check.source_reference,
                ),
            )
        return tuple(unique[key] for key in sorted(unique))

    def _inspect(self, root: Path, candidate: bool) -> BackendResult:
        # Readiness owns the task-service check below.  Reuse the project service's isolated
        # canonical inspection while deliberately omitting only its Studio plugin-manifest gate;
        # Task 038's kitting runtime contract is valid without an editor plugin, and malformed
        # XML/ports still come from ``browse_tasks`` as blocking findings.
        inspect_candidate = getattr(self._project_service, "inspect_candidate", None)
        if callable(inspect_candidate):
            return cast(
                BackendResult,
                inspect_candidate(root, validate_studio_extensions=False),
            )
        return self._project_service.inspect(root)

    @contextmanager
    def _candidate_root(self, root: Path, candidate: ProjectContents | None) -> Iterator[Path]:
        if candidate is None:
            yield root
            return
        with tempfile.TemporaryDirectory(prefix="cellforge-readiness-") as temporary:
            temporary_root = Path(temporary)
            try:
                relative_root = root.relative_to(self._schemas.parent)
                staged = temporary_root / relative_root
            except ValueError:
                staged = temporary_root / root.name
            staged.parent.mkdir(parents=True, exist_ok=True)
            if root.is_dir():
                shutil.copytree(
                    root,
                    staged,
                    ignore=shutil.ignore_patterns(
                        *_TRANSIENT_NAMES,
                        ".cellforge-save-recovery.json",
                    ),
                )
            else:
                staged.mkdir(parents=True)
            # Example recipe bindings intentionally use a repository-relative ../../schemas
            # reference. Recreate that dependency inside the isolated candidate tree so
            # validation sees the same registered schema without touching the workspace.
            staged_schema_root = temporary_root / "schemas"
            if not staged_schema_root.exists():
                shutil.copytree(self._schemas, staged_schema_root)
            staged_cell_yaml = _normalize_candidate_schema_references(
                candidate.cell_yaml, staged, self._schemas
            )
            (staged / "cell.yaml").write_text(staged_cell_yaml, encoding="utf-8", newline="\n")
            scene_path = _scene_path_from_yaml(candidate.cell_yaml) or "scene.usda"
            scene_target = (staged / scene_path).resolve()
            if scene_target.is_relative_to(staged):
                scene_target.parent.mkdir(parents=True, exist_ok=True)
                scene_target.write_text(candidate.scene_usda, encoding="utf-8", newline="\n")
            for relative, content in sorted(candidate.artifacts.items()):
                target = (staged / relative).resolve()
                if not target.is_relative_to(staged) or Path(relative).is_absolute():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            yield staged

    def _build_report(
        self,
        original_root: Path,
        service_root: Path,
        contents: ProjectContents | None,
        result: BackendResult,
        requested: str,
        probe: ReadinessBackendProbe,
    ) -> StudioReadinessReport:
        if contents is None:
            contents = _read_project_contents(service_root)
        identity = _project_identity(original_root, service_root, contents)
        checks: list[StudioReadinessCheck] = []
        if result.project is None:
            checks.extend(
                _finding_checks(
                    result.validation,
                    original_root,
                    default_category=ReadinessCategory.CANONICAL,
                    service_root=service_root,
                )
            )
            if not checks:
                checks.append(
                    _check(
                        "readiness.canonical.project",
                        ReadinessCategory.CANONICAL,
                        ReadinessStatus.BLOCKED,
                        ReadinessSeverity.ERROR,
                        f"{original_root}#",
                        "The project did not produce a complete canonical source pair.",
                        "readiness.open_validator",
                        validator_link="project-service.inspect",
                    )
                )
            if contents is not None:
                raw, cell, schema_registry, parse_findings = _load_cell(
                    service_root, contents.cell_yaml, self._schemas
                )
                checks.extend(
                    _finding_checks(
                        parse_findings,
                        original_root,
                        default_category=ReadinessCategory.SCHEMA,
                        service_root=service_root,
                    )
                )
                if raw is not None and cell is not None and schema_registry is not None:
                    checks.extend(
                        self._component_checks(
                            original_root, service_root, contents, cell, schema_registry
                        )
                    )
                    checks.extend(self._task_checks(original_root, service_root, contents, cell))
                    checks.extend(self._recipe_checks(original_root, service_root, contents, cell))
                    checks.extend(
                        self._scenario_checks(original_root, service_root, contents, cell)
                    )
                    checks.extend(
                        self._deployment_checks(original_root, service_root, contents, requested)
                    )
                    checks.extend(
                        self._calibration_checks(original_root, result.validation, service_root)
                    )
                    checks.extend(
                        self._evidence_checks(original_root, service_root, cell, identity)
                    )
                checks.extend(self._fidelity_checks(original_root, requested, probe))
                checks.append(
                    _check(
                        "readiness.safety-review.independent",
                        ReadinessCategory.SAFETY_REVIEW,
                        ReadinessStatus.ADVISORY,
                        ReadinessSeverity.WARNING,
                        f"{original_root / 'cell.yaml'}#/connections",
                        SAFETY_REVIEW_DISCLAIMER,
                        "readiness.review-independent-safety",
                        evidence_references=("independent-rated-hardware",),
                        validator_link="safety.independent-boundary",
                    )
                )
            return self._finish(identity, checks, requested, "unavailable")

        assert contents is not None

        checks.append(
            _check(
                "readiness.canonical.cell-scene-pair",
                ReadinessCategory.CANONICAL,
                ReadinessStatus.PASS,
                ReadinessSeverity.INFO,
                f"{original_root / 'cell.yaml'}#",
                "cell.yaml and its referenced USDA scene are readable as a synchronized pair.",
                validator_link="project-service.inspect",
            )
        )
        raw, cell, schema_registry, parse_findings = _load_cell(
            service_root, contents.cell_yaml, self._schemas
        )
        checks.extend(
            _finding_checks(
                parse_findings,
                original_root,
                default_category=ReadinessCategory.SCHEMA,
                service_root=service_root,
            )
        )
        if raw is not None and cell is not None and schema_registry is not None:
            checks.append(
                _check(
                    "readiness.schema.versions",
                    ReadinessCategory.SCHEMA,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'cell.yaml'}#/schema_version",
                    f"Canonical schema version '{cell.schema_version}' is registered.",
                    validator_link="SchemaRegistry.validate",
                )
            )
            checks.extend(
                self._component_checks(original_root, service_root, contents, cell, schema_registry)
            )
            checks.extend(self._task_checks(original_root, service_root, contents, cell))
            checks.extend(self._recipe_checks(original_root, service_root, contents, cell))
            checks.extend(self._scenario_checks(original_root, service_root, contents, cell))
            checks.extend(self._deployment_checks(original_root, service_root, contents, requested))
            checks.extend(self._calibration_checks(original_root, result.validation, service_root))
            checks.extend(self._evidence_checks(original_root, service_root, cell, identity))
        else:
            checks.append(
                _check(
                    "readiness.schema.document",
                    ReadinessCategory.SCHEMA,
                    ReadinessStatus.BLOCKED,
                    ReadinessSeverity.ERROR,
                    f"{original_root / 'cell.yaml'}#",
                    "cell.yaml could not be loaded as a valid CellProject.",
                    "readiness.open_validator",
                    validator_link="SchemaRegistry.validate",
                )
            )
        checks.extend(self._fidelity_checks(original_root, requested, probe))
        checks.append(
            _check(
                "readiness.safety-review.independent",
                ReadinessCategory.SAFETY_REVIEW,
                ReadinessStatus.ADVISORY,
                ReadinessSeverity.WARNING,
                f"{original_root / 'cell.yaml'}#/connections",
                SAFETY_REVIEW_DISCLAIMER,
                "readiness.review-independent-safety",
                evidence_references=("independent-rated-hardware",),
                validator_link="safety.independent-boundary",
            )
        )
        return self._finish(identity, checks, requested, _observed_fidelity(probe))

    def _component_checks(
        self,
        original_root: Path,
        service_root: Path,
        contents: ProjectContents,
        cell: CellProject,
        schema_registry: SchemaRegistry,
    ) -> list[StudioReadinessCheck]:
        registry = FilesystemComponentRegistry.from_directory(
            service_root / "components", schema_registry=schema_registry
        )
        resolution = resolve_cell(
            cell,
            registry,
            ExecutionMode.SIMULATION,
            source_name=str(original_root / "cell.yaml"),
        )
        checks: list[StudioReadinessCheck] = []
        modeled_safety_indices = {
            index
            for index, instance in enumerate(cell.components)
            if bool(instance.config.get("modeled_only")) and instance.id.startswith("safety-")
        }
        resolver_items = tuple(
            item
            for item in (_validation_item(finding) for finding in resolution.findings)
            if not (
                item.code == "resolver.adapter-missing"
                and any(f"/components/{index}/" in item.path for index in modeled_safety_indices)
            )
        )
        checks.extend(
            _finding_checks(
                resolver_items,
                original_root,
                default_category=ReadinessCategory.COMPONENTS,
                service_root=service_root,
            )
        )
        if not any(item.code.startswith("resolver.component") for item in resolver_items):
            checks.append(
                _check(
                    "readiness.components.registry-resolution",
                    ReadinessCategory.COMPONENTS,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'components'}#",
                    "All selected component IDs and exact versions resolve in the filesystem "
                    "registry.",
                    validator_link="resolve_cell",
                )
            )
        connection_items = tuple(
            item
            for item in resolver_items
            if _category_for_code(item.code) == ReadinessCategory.PORTS
        )
        if not connection_items:
            checks.append(
                _check(
                    "readiness.ports.capability-resolution",
                    ReadinessCategory.PORTS,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'cell.yaml'}#/connections",
                    "Declared ports, connections, capabilities, and simulation mode are resolved.",
                    validator_link="resolve_cell",
                )
            )
        assets: list[ValidationItem] = []
        for instance in sorted(cell.components, key=lambda item: item.id):
            package = registry.get(instance.component, instance.version)
            if package is None:
                continue
            manifest_root = package.source_path.parent
            for label, relative in (
                ("visual asset", package.manifest.assets.visual_usd),
                ("collision asset", package.manifest.assets.collision_usd),
            ):
                asset = (manifest_root / relative).resolve()
                if not asset.is_file():
                    assets.append(
                        ValidationItem(
                            code="readiness.asset-missing",
                            severity="error",
                            path=f"{package.package_path}/component.yaml#/assets",
                            message=f"Component '{instance.component}' {label} is missing.",
                        )
                    )
            if not package.manifest.frames:
                assets.append(
                    ValidationItem(
                        code="readiness.frame-missing",
                        severity="error",
                        path=f"{package.package_path}/component.yaml#/frames",
                        message=f"Component '{instance.component}' declares no usable frames.",
                    )
                )
        checks.extend(
            _finding_checks(
                assets,
                original_root,
                default_category=ReadinessCategory.ASSETS,
                service_root=service_root,
            )
        )
        if not assets:
            checks.append(
                _check(
                    "readiness.assets.frames",
                    ReadinessCategory.ASSETS,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'components'}#",
                    "Selected component visual/collision assets and declared frames are available.",
                    validator_link="FilesystemComponentRegistry",
                )
            )
        return checks

    def _task_checks(
        self, original_root: Path, service_root: Path, contents: ProjectContents, cell: CellProject
    ) -> list[StudioReadinessCheck]:
        try:
            result = self._project_service.browse_tasks(service_root, contents)
            items = result.validation
            # Task 038's reusable kitting contract intentionally has no Studio plugin manifest.
            # Its runtime adapter owns those immutable node types, so preserve the existing
            # validator finding as an advisory rather than turning a valid L0 contract into a
            # blocked Studio authoring result.  Syntax, ports, mappings, and all other validator
            # failures remain blocking.
            if items and all(item.code == "compiler.behavior-tree-node-unknown" for item in items):
                first = items[0]
                items = (
                    ValidationItem(
                        code="readiness.task-runtime-contract-only",
                        severity="warning",
                        path=first.path,
                        message=(
                            "The reusable simulation task uses immutable runtime node types "
                            "without a Studio editor plugin manifest; canonical runtime "
                            "validation remains the source of truth."
                        ),
                    ),
                )
            if not items and not result.tasks:
                items = (
                    ValidationItem(
                        code="readiness.task-missing",
                        severity="error",
                        path=f"{original_root / 'cell.yaml'}#/tasks",
                        message="The cell declares no executable BehaviorTree task.",
                    ),
                )
        except Exception as error:
            items = (
                ValidationItem(
                    code="studio.backend.task-check-failed",
                    severity="error",
                    path=f"{original_root / 'cell.yaml'}#/tasks",
                    message=f"Task readiness check failed ({type(error).__name__}).",
                ),
            )
        checks = _finding_checks(
            items, original_root, ReadinessCategory.TASKS, service_root=service_root
        )
        if not items:
            checks.append(
                _check(
                    "readiness.tasks.references",
                    ReadinessCategory.TASKS,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'cell.yaml'}#/tasks",
                    "BehaviorTree.CPP task files and referenced node specifications are available.",
                    validator_link="TaskAuthoringService.browse",
                )
            )
        return checks

    def _recipe_checks(
        self, original_root: Path, service_root: Path, contents: ProjectContents, cell: CellProject
    ) -> list[StudioReadinessCheck]:
        try:
            result = self._project_service.browse_recipes(service_root, contents)
            items = result.validation
            if not items and not result.recipes:
                items = (
                    ValidationItem(
                        code="readiness.recipe-missing",
                        severity="error",
                        path=f"{original_root / 'cell.yaml'}#/recipes",
                        message="The cell declares no recipe reference for simulation readiness.",
                    ),
                )
        except Exception as error:
            items = (
                ValidationItem(
                    code="studio.backend.recipe-check-failed",
                    severity="error",
                    path=f"{original_root / 'cell.yaml'}#/recipes",
                    message=f"Recipe readiness check failed ({type(error).__name__}).",
                ),
            )
        checks = _finding_checks(
            items, original_root, ReadinessCategory.RECIPES, service_root=service_root
        )
        if not items:
            checks.append(
                _check(
                    "readiness.recipes.references",
                    ReadinessCategory.RECIPES,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'cell.yaml'}#/recipes",
                    "Recipe schemas, references, and cell/capability compatibility are valid.",
                    validator_link="RecipeAuthoringService.browse",
                )
            )
        return checks

    def _scenario_checks(
        self, original_root: Path, service_root: Path, contents: ProjectContents, cell: CellProject
    ) -> list[StudioReadinessCheck]:
        try:
            result = self._project_service.browse_scenarios(service_root, contents)
            items = result.validation
            if not items and not result.scenarios:
                items = (
                    ValidationItem(
                        code="readiness.scenario-missing",
                        severity="error",
                        path=f"{original_root / 'cell.yaml'}#/scenarios",
                        message="No scenario is available for deterministic simulation replay.",
                    ),
                )
        except Exception as error:
            items = (
                ValidationItem(
                    code="studio.backend.scenario-check-failed",
                    severity="error",
                    path=f"{original_root / 'cell.yaml'}#/scenarios",
                    message=f"Scenario readiness check failed ({type(error).__name__}).",
                ),
            )
        checks = _finding_checks(
            items, original_root, ReadinessCategory.SCENARIOS, service_root=service_root
        )
        if not items:
            checks.append(
                _check(
                    "readiness.scenarios.availability",
                    ReadinessCategory.SCENARIOS,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'cell.yaml'}#/scenarios",
                    "At least one declared scenario is available for the selected project.",
                    validator_link="ScenarioEvidenceService.browse_scenarios",
                )
            )
        return checks

    def _deployment_checks(
        self,
        original_root: Path,
        service_root: Path,
        contents: ProjectContents,
        requested: str,
    ) -> list[StudioReadinessCheck]:
        try:
            result = self._project_service.browse_deployment_profiles(service_root, contents)
            items = list(result.validation)
            profiles = _profile_documents(service_root, contents)
            matching = [profile for profile in profiles if profile[1] == requested]
            if not items and not matching:
                items.append(
                    ValidationItem(
                        code="readiness.adapter-profile-unavailable",
                        severity="error",
                        path=f"{original_root / 'cell.yaml'}#/deployment_profiles",
                        message=(
                            "No deployment profile declares requested simulation fidelity "
                            f"{requested}."
                        ),
                    )
                )
            for relative, fidelity, data in matching:
                runtime = (
                    data.get("runtime", {}) if isinstance(data.get("runtime"), Mapping) else {}
                )
                config = runtime.get("adapter_configuration")
                if not isinstance(config, str) or not config.strip():
                    items.append(
                        ValidationItem(
                            code="readiness.adapter-configuration-missing",
                            severity="error",
                            path=f"{original_root / relative}#/runtime/adapter_configuration",
                            message=(
                                "Matching deployment profile does not declare adapter "
                                "configuration."
                            ),
                        )
                    )
                    continue
                config_path = (service_root / relative).parent / config
                if not config_path.is_file():
                    items.append(
                        ValidationItem(
                            code="readiness.adapter-configuration-unavailable",
                            severity="error",
                            path=f"{original_root / relative}#/runtime/adapter_configuration",
                            message=f"Adapter configuration '{config}' is unavailable.",
                        )
                    )
                    continue
                try:
                    adapter_document = json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    adapter_document = None
                if not isinstance(adapter_document, Mapping):
                    items.append(
                        ValidationItem(
                            code="readiness.adapter-configuration-malformed",
                            severity="error",
                            path=f"{original_root / relative}#/runtime/adapter_configuration",
                            message="Adapter configuration is not valid JSON.",
                        )
                    )
                elif not adapter_document.get("nodes"):
                    items.append(
                        ValidationItem(
                            code="readiness.adapter-configuration-empty",
                            severity="error",
                            path=f"{original_root / relative}#/runtime/adapter_configuration",
                            message="Adapter configuration contains no device nodes.",
                        )
                    )
        except Exception as error:
            items = [
                ValidationItem(
                    code="studio.backend.deployment-check-failed",
                    severity="error",
                    path=f"{original_root / 'cell.yaml'}#/deployment_profiles",
                    message=f"Deployment readiness check failed ({type(error).__name__}).",
                )
            ]
        checks = _finding_checks(
            items, original_root, ReadinessCategory.ADAPTERS, service_root=service_root
        )
        if not items:
            checks.append(
                _check(
                    "readiness.adapters.configuration",
                    ReadinessCategory.ADAPTERS,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'cell.yaml'}#/deployment_profiles",
                    "A deployment adapter configuration is available for requested fidelity "
                    f"{requested}.",
                    validator_link="DeploymentService.browse_deployment_profiles",
                )
            )
        return checks

    def _calibration_checks(
        self,
        original_root: Path,
        validation: Sequence[ValidationItem],
        service_root: Path | None = None,
    ) -> list[StudioReadinessCheck]:
        items = tuple(
            item
            for item in validation
            if _category_for_code(item.code) == ReadinessCategory.CALIBRATION
        )
        checks = _finding_checks(
            items, original_root, ReadinessCategory.CALIBRATION, service_root=service_root
        )
        if not items:
            checks.append(
                _check(
                    "readiness.calibration.freshness",
                    ReadinessCategory.CALIBRATION,
                    ReadinessStatus.ADVISORY,
                    ReadinessSeverity.WARNING,
                    f"{original_root / 'cell.yaml'}#/calibrations",
                    "No stale calibration finding was reported; add or review calibration "
                    "records before higher-fidelity work.",
                    "readiness.review-calibration",
                    validator_link="SpatialConfigurationService.validate_calibrations",
                )
            )
        return checks

    def _evidence_checks(
        self,
        original_root: Path,
        service_root: Path,
        cell: CellProject,
        identity: StudioProjectIdentity,
    ) -> list[StudioReadinessCheck]:
        try:
            records = self._project_service.browse_evidence(service_root)
        except Exception as error:
            return _finding_checks(
                (
                    ValidationItem(
                        code="studio.backend.evidence-check-failed",
                        severity="error",
                        path=f"{original_root / 'evidence'}#",
                        message=f"Evidence readiness check failed ({type(error).__name__}).",
                    ),
                ),
                original_root,
                ReadinessCategory.EVIDENCE,
                service_root=service_root,
            )
        if not records:
            return [
                _check(
                    "readiness.evidence.prerequisites",
                    ReadinessCategory.EVIDENCE,
                    ReadinessStatus.ADVISORY,
                    ReadinessSeverity.WARNING,
                    f"{original_root / 'evidence'}#",
                    "No replayable simulation evidence is present; run and record a scenario "
                    "before relying on evidence.",
                    "readiness.run-scenario-evidence",
                    validator_link="ScenarioEvidenceService.browse_evidence",
                )
            ]
        stale: list[ValidationItem] = []
        for record in records:
            detail = self._project_service.inspect_evidence(service_root, evidence_path=record.path)
            if detail is None:
                stale.append(
                    ValidationItem(
                        code="evidence.record-unreadable",
                        severity="error",
                        path=f"{original_root / record.path}#",
                        message="Evidence record could not be inspected for replay prerequisites.",
                    )
                )
                continue
            if (
                detail.project_cell_sha256
                and identity.cell_sha256
                and detail.project_cell_sha256 != identity.cell_sha256
            ):
                stale.append(
                    ValidationItem(
                        code="evidence.source-stale",
                        severity="error",
                        path=f"{original_root / record.path}#/canonical_project/cell_yaml",
                        message="Evidence refers to a different canonical cell source hash.",
                    )
                )
        checks = _finding_checks(
            stale, original_root, ReadinessCategory.EVIDENCE, service_root=service_root
        )
        if not stale:
            checks.append(
                _check(
                    "readiness.evidence.prerequisites",
                    ReadinessCategory.EVIDENCE,
                    ReadinessStatus.PASS,
                    ReadinessSeverity.INFO,
                    f"{original_root / 'evidence'}#",
                    "Stored evidence records are available for source-linked inspection.",
                    validator_link="ScenarioEvidenceService.inspect_evidence",
                )
            )
        return checks

    def _fidelity_checks(
        self, original_root: Path, requested: str, probe: ReadinessBackendProbe
    ) -> list[StudioReadinessCheck]:
        observed = _observed_fidelity(probe)
        requested_rank = _FIDELITY_ORDER.get(requested, 0)
        observed_rank = _FIDELITY_ORDER.get(observed, -1)
        if not probe.available:
            status = ReadinessStatus.UNAVAILABLE
            message = (
                "The selected simulation backend is unavailable; no fidelity pass is inferred."
            )
        elif requested_rank > observed_rank:
            status = ReadinessStatus.UNAVAILABLE
            message = (
                f"Requested {requested} fidelity is unavailable; the observed backend is "
                f"{observed}. "
                "No synthetic higher-fidelity result is reported."
            )
        elif requested_rank >= 2 and not (
            probe.isaac_sim_available and probe.cuda_gpu_available and probe.actual_physx_executed
        ):
            status = ReadinessStatus.UNAVAILABLE
            message = (
                f"Requested {requested} fidelity cannot be proven without Isaac Sim, a compatible "
                "GPU, and actual PhysX execution."
            )
        else:
            status = ReadinessStatus.PASS
            message = (
                f"Requested {requested} fidelity is observed as {observed}. L0 remains CPU-only."
            )
        return [
            _check(
                "readiness.fidelity.target",
                ReadinessCategory.FIDELITY,
                status,
                ReadinessSeverity.INFO
                if status == ReadinessStatus.PASS
                else ReadinessSeverity.ERROR,
                f"{original_root / 'deployment_profiles'}#",
                message,
                "readiness.configure-simulation-backend"
                if status != ReadinessStatus.PASS
                else None,
                evidence_references=(probe.detail,) if probe.detail else (),
                validator_link="SimulationControlService.fidelity",
            )
        ]

    def _finish(
        self,
        identity: StudioProjectIdentity,
        checks: Sequence[StudioReadinessCheck],
        requested: str,
        observed: str,
    ) -> StudioReadinessReport:
        normalized_checks = tuple(sorted(checks, key=lambda check: check.check_id))
        counts = {status.value: 0 for status in ReadinessStatus}
        for check in normalized_checks:
            counts[str(check.status)] = counts.get(str(check.status), 0) + 1
        if counts[ReadinessStatus.BLOCKED.value]:
            overall: ReadinessStatus = ReadinessStatus.BLOCKED
        elif counts[ReadinessStatus.UNAVAILABLE.value]:
            overall = ReadinessStatus.UNAVAILABLE
        elif counts[ReadinessStatus.ADVISORY.value]:
            overall = ReadinessStatus.ADVISORY
        else:
            overall = ReadinessStatus.PASS
        summary = StudioReadinessSummary(
            overall_status=overall,
            total=len(normalized_checks),
            pass_count=counts[ReadinessStatus.PASS.value],
            blocked_count=counts[ReadinessStatus.BLOCKED.value],
            advisory_count=counts[ReadinessStatus.ADVISORY.value],
            unavailable_count=counts[ReadinessStatus.UNAVAILABLE.value],
            ready_for_simulation=(
                counts[ReadinessStatus.BLOCKED.value] == 0
                and counts[ReadinessStatus.UNAVAILABLE.value] == 0
            ),
        )
        return StudioReadinessReport(
            project_identity=identity,
            checks=normalized_checks,
            summary=summary,
            requested_fidelity=requested,
            observed_fidelity=observed,
        )

    def _backend_failure_report(
        self,
        root: Path,
        contents: ProjectContents | None,
        requested: str,
        probe: ReadinessBackendProbe,
        error: Exception,
    ) -> StudioReadinessReport:
        identity = _project_identity(root, root, contents)
        check = _check(
            "readiness.backend.failure",
            ReadinessCategory.BACKEND,
            ReadinessStatus.UNAVAILABLE,
            ReadinessSeverity.ERROR,
            f"{root}#",
            f"Readiness backend failed ({type(error).__name__}); no readiness pass was inferred.",
            "readiness.retry-backend",
            validator_link="EvaluateStudioReadiness",
        )
        return self._finish(identity, (check,), requested, _observed_fidelity(probe))

    def _save_guard(
        self,
        preview: ReadinessCandidatePreview,
        before: Mapping[str, str],
        confirmation_token: str | None,
        confirmed: bool,
    ) -> ValidationItem | None:
        if not confirmed:
            return ValidationItem(
                code="studio.readiness.confirmation-required",
                severity="error",
                path=f"{preview.project_path}#",
                message=(
                    "Explicit Save-after-preview confirmation is required; no files were changed."
                ),
            )
        if confirmation_token != preview.confirmation_token:
            return ValidationItem(
                code="studio.readiness.confirmation-token-invalid",
                severity="error",
                path=f"{preview.project_path}#",
                message=(
                    "The readiness preview confirmation token is invalid or stale; no files "
                    "were changed."
                ),
            )
        if dict(before) != dict(preview.source_hashes_before):
            return ValidationItem(
                code="studio.readiness.preview-stale",
                severity="error",
                path=f"{preview.project_path}#",
                message="Canonical sources changed after preview; refresh readiness before Save.",
            )
        if not preview.can_save:
            return ValidationItem(
                code="studio.readiness.preview-blocked",
                severity="error",
                path=f"{preview.project_path}#",
                message="The readiness preview is blocked or unavailable and cannot be saved.",
            )
        return None


# A descriptive alias for callers that prefer the noun form used by the task plan.
StudioReadinessService = EvaluateStudioReadiness
ReadinessService = EvaluateStudioReadiness


def evaluate_studio_readiness(
    project_path: str | Path,
    canonical_schema_directory: Path,
    **kwargs: Any,
) -> StudioReadinessReport:
    """Construct and execute the pure readiness command in one call."""

    return EvaluateStudioReadiness(canonical_schema_directory).EvaluateStudioReadiness(
        project_path, **kwargs
    )


def validate_studio_readiness_report_document(
    document: Mapping[str, Any],
    schema_path: Path | None = None,
) -> tuple[ValidationItem, ...]:
    """Validate an exported diagnostic report against Draft 2020-12."""

    path = schema_path or _readiness_schema_path()
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return (
            ValidationItem(
                code="studio.readiness.schema-unavailable",
                severity="error",
                path=f"{path}#",
                message=f"Readiness report schema is unavailable ({type(error).__name__}).",
            ),
        )
    errors = sorted(
        validator.iter_errors(document),
        key=lambda item: (tuple(str(part) for part in item.absolute_path), item.message),
    )
    return tuple(
        ValidationItem(
            code=f"readiness.schema.{error.validator}",
            severity="error",
            path=f"{path}#/{'/'.join(str(part) for part in error.absolute_path)}",
            message=error.message,
        )
        for error in errors
    )


def _check(
    check_id: str,
    category: ReadinessCategory | str,
    status: ReadinessStatus,
    severity: ReadinessSeverity,
    source_reference: str,
    message: str,
    remediation_id: str | None = None,
    *,
    evidence_references: Sequence[str] = (),
    validator_link: str | None = None,
    finding_id: str | None = None,
) -> StudioReadinessCheck:
    return StudioReadinessCheck(
        check_id=check_id,
        category=str(category),
        status=status,
        severity=severity,
        source_reference=source_reference,
        message=message,
        remediation_id=remediation_id,
        evidence_references=tuple(sorted(str(item) for item in evidence_references)),
        validator_link=validator_link,
        finding_id=finding_id,
    )


def _finding_checks(
    findings: Sequence[ValidationItem],
    original_root: Path,
    default_category: ReadinessCategory | str,
    *,
    service_root: Path | None = None,
) -> list[StudioReadinessCheck]:
    checks: list[StudioReadinessCheck] = []
    for finding in sorted(findings, key=lambda item: (item.path, item.code, item.message)):
        category = _category_for_code(finding.code, default_category)
        status, severity = _status_for_finding(finding.severity, finding.code)
        source = _remap_source(finding.path, original_root, service_root)
        finding_id = _stable_id(f"{category}|{finding.code}|{source}|{finding.message}")
        checks.append(
            _check(
                f"readiness.{category}.{finding_id}",
                category,
                status,
                severity,
                source,
                finding.message,
                _remediation_for(category, finding.code),
                validator_link=finding.code,
                finding_id=finding_id,
            )
        )
    return checks


def _status_for_finding(severity: str, code: str = "") -> tuple[ReadinessStatus, ReadinessSeverity]:
    value = str(severity).lower()
    if value in {"warning", "warn"}:
        return ReadinessStatus.ADVISORY, ReadinessSeverity.WARNING
    if value in {"info", "notice"}:
        return ReadinessStatus.ADVISORY, ReadinessSeverity.INFO
    if str(code).lower() == "resolver.adapter-missing":
        return ReadinessStatus.BLOCKED, ReadinessSeverity.ERROR
    if "adapter" in str(code).lower() or "fidelity" in str(code).lower():
        return ReadinessStatus.UNAVAILABLE, ReadinessSeverity.ERROR
    return ReadinessStatus.BLOCKED, ReadinessSeverity.ERROR


def _category_for_code(
    code: str, default: ReadinessCategory | str = ReadinessCategory.CANONICAL
) -> ReadinessCategory:
    normalized = str(code).lower()
    if "schema" in normalized:
        return ReadinessCategory.SCHEMA
    if "asset" in normalized or "frame" in normalized or "spatial" in normalized:
        return ReadinessCategory.ASSETS
    if "recipe" in normalized:
        return ReadinessCategory.RECIPES
    if "resolver.port" in normalized or "connection" in normalized or "capability" in normalized:
        return ReadinessCategory.PORTS
    if "component" in normalized or "registry" in normalized or "support-level" in normalized:
        return ReadinessCategory.COMPONENTS
    if "adapter" in normalized:
        return ReadinessCategory.ADAPTERS
    if "task" in normalized or "behavior" in normalized or "plugin" in normalized:
        return ReadinessCategory.TASKS
    if "scenario" in normalized:
        return ReadinessCategory.SCENARIOS
    if "calibration" in normalized:
        return ReadinessCategory.CALIBRATION
    if "evidence" in normalized:
        return ReadinessCategory.EVIDENCE
    if "deployment" in normalized or "target" in normalized:
        return ReadinessCategory.DEPLOYMENT
    return ReadinessCategory(str(default))


def _remediation_for(category: ReadinessCategory, code: str) -> str:
    normalized = str(code).lower()
    if category == ReadinessCategory.TASKS:
        return "readiness.open-task-authoring"
    if category == ReadinessCategory.RECIPES:
        return "readiness.open-recipe-authoring"
    if category == ReadinessCategory.SCENARIOS:
        return "readiness.open-scenario-authoring"
    if category == ReadinessCategory.CALIBRATION:
        return "readiness.review-calibration"
    if category == ReadinessCategory.FIDELITY or "adapter" in normalized:
        return "readiness.configure-simulation-backend"
    if category == ReadinessCategory.EVIDENCE:
        return "readiness.run-scenario-evidence"
    if category == ReadinessCategory.SAFETY_REVIEW:
        return "readiness.review-independent-safety"
    return "readiness.open-validator"


def _validation_item(finding: Any) -> ValidationItem:
    severity = getattr(finding, "severity", "error")
    return ValidationItem(
        code=str(getattr(finding, "code", "readiness.finding")),
        severity=str(getattr(severity, "value", severity)),
        path=str(getattr(finding, "path", "cell.yaml#")),
        message=str(getattr(finding, "message", "Readiness prerequisite failed.")),
    )


def _load_cell(
    root: Path,
    cell_yaml: str,
    canonical_schemas: Path,
) -> tuple[
    Mapping[str, Any] | None, CellProject | None, SchemaRegistry | None, tuple[ValidationItem, ...]
]:
    source = root / "cell.yaml"
    try:
        raw = yaml.safe_load(cell_yaml)
    except yaml.YAMLError as error:
        return (
            None,
            None,
            None,
            (
                ValidationItem(
                    code="schema.cell.yaml-malformed",
                    severity="error",
                    path=f"{source}#",
                    message=f"cell.yaml is malformed ({type(error).__name__}).",
                ),
            ),
        )
    if not isinstance(raw, Mapping):
        return (
            None,
            None,
            None,
            (
                ValidationItem(
                    code="schema.cell.root-invalid",
                    severity="error",
                    path=f"{source}#",
                    message="cell.yaml must contain an object at its document root.",
                ),
            ),
        )
    try:
        registry = SchemaRegistry.from_directory(
            resolve_project_schema_directory(root, canonical_schemas)
        )
        findings = registry.validate(SchemaDocumentKind.CELL, raw, source)
        cell = CellProject.model_validate(raw) if not findings else None
    except (OSError, ValueError, ValidationError) as error:
        return (
            raw,
            None,
            None,
            (
                ValidationItem(
                    code="schema.cell.invalid",
                    severity="error",
                    path=f"{source}#",
                    message=f"cell.yaml failed canonical validation ({type(error).__name__}).",
                ),
            ),
        )
    return raw, cell, registry, tuple(_validation_item(item) for item in findings)


def _project_identity(
    original_root: Path, service_root: Path, contents: ProjectContents | None
) -> StudioProjectIdentity:
    if contents is None:
        source_hashes = _source_hashes(original_root, None)
        cell_yaml = _read_text(original_root / "cell.yaml")
        scene_path = _scene_path_from_yaml(cell_yaml or "")
        source_name = None
        name = None
        cell_id = None
    else:
        source_hashes = (
            _source_hashes(original_root, contents)
            if service_root == original_root
            else _content_hashes(contents)
        )
        cell_yaml = contents.cell_yaml
        scene_path = _scene_path_from_yaml(cell_yaml)
        source_name = None
        name = None
        cell_id = None
    try:
        raw = yaml.safe_load(cell_yaml or "")
        if isinstance(raw, Mapping) and isinstance(raw.get("cell"), Mapping):
            cell_id = str(raw["cell"].get("id")) if raw["cell"].get("id") else None
            name = str(raw["cell"].get("name")) if raw["cell"].get("name") else None
    except yaml.YAMLError:
        pass
    if scene_path:
        source_name = scene_path
        if source_name not in source_hashes and contents is None:
            source_hashes = dict(source_hashes)
            source_hashes[source_name] = _sha256_file(original_root / scene_path)
    return StudioProjectIdentity(
        path=str(original_root),
        cell_id=cell_id,
        name=name,
        scene_path=source_name,
        source_hashes=source_hashes,
    )


def _read_project_contents(root: Path) -> ProjectContents | None:
    """Read canonical display buffers even when the project validator found other failures."""

    cell_yaml = _read_text(root / "cell.yaml")
    if cell_yaml is None:
        return None
    scene_reference = _scene_path_from_yaml(cell_yaml)
    if scene_reference is None:
        return ProjectContents(cell_yaml=cell_yaml, scene_usda="")
    scene_usda = _read_text(root / scene_reference)
    if scene_usda is None:
        scene_usda = ""
    return ProjectContents(cell_yaml=cell_yaml, scene_usda=scene_usda)


def _source_hashes(root: Path, contents: ProjectContents | None) -> dict[str, str]:
    if contents is not None:
        candidate_hashes = _content_hashes(contents)
        return {relative: _sha256_file(root / relative) for relative in sorted(candidate_hashes)}
    values: dict[str, str] = {}
    cell = root / "cell.yaml"
    if cell.is_file():
        values["cell.yaml"] = _sha256_file(cell)
        reference = _scene_path_from_yaml(_read_text(cell) or "")
        if reference:
            values[reference] = _sha256_file(root / reference)
    return dict(sorted(values.items()))


def _content_hashes(contents: ProjectContents) -> dict[str, str]:
    values = {"cell.yaml": _sha256_bytes(contents.cell_yaml.encode("utf-8"))}
    scene = _scene_path_from_yaml(contents.cell_yaml) or "scene.usda"
    values[scene] = _sha256_bytes(contents.scene_usda.encode("utf-8"))
    values.update(
        {
            Path(relative).as_posix(): _sha256_bytes(content)
            for relative, content in sorted(contents.artifacts.items())
            if not Path(relative).is_absolute()
        }
    )
    return dict(sorted(values.items()))


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return "missing"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _scene_path_from_yaml(cell_yaml: str) -> str | None:
    try:
        raw = yaml.safe_load(cell_yaml)
    except yaml.YAMLError:
        return None
    scene = raw.get("scene") if isinstance(raw, Mapping) else None
    reference = scene.get("usd") if isinstance(scene, Mapping) else None
    return Path(reference).as_posix() if isinstance(reference, str) and reference.strip() else None


def _normalize_candidate_schema_references(
    cell_yaml: str, staged_root: Path, canonical_schemas: Path
) -> str:
    """Make external example schema references resolve inside isolated validation only."""

    try:
        raw = yaml.safe_load(cell_yaml)
    except yaml.YAMLError:
        return cell_yaml
    if not isinstance(raw, Mapping):
        return cell_yaml
    recipes = raw.get("recipes")
    if not isinstance(recipes, list):
        return cell_yaml
    changed = False
    mutable = dict(raw)
    mutable_recipes: list[object] = []
    for item in recipes:
        if not isinstance(item, Mapping):
            mutable_recipes.append(item)
            continue
        binding = dict(item)
        schema_ref = binding.get("schema")
        if isinstance(schema_ref, str) and schema_ref.strip():
            resolved = (staged_root / schema_ref).resolve()
            candidate = canonical_schemas / Path(schema_ref).name
            if candidate.is_file() and not resolved.is_relative_to(staged_root):
                binding["schema"] = str(candidate)
                changed = True
        mutable_recipes.append(binding)
    if not changed:
        return cell_yaml
    mutable["recipes"] = mutable_recipes
    return yaml.safe_dump(mutable, sort_keys=False)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _remap_source(path: str, root: Path, service_root: Path | None = None) -> str:
    normalized = str(path)
    normalized = normalized.replace("\\", "/")
    if service_root is not None:
        service_prefix = service_root.resolve().as_posix().rstrip("/")
        if normalized == service_prefix or normalized.startswith(f"{service_prefix}/"):
            suffix = normalized[len(service_prefix) :].lstrip("/")
            root_prefix = root.resolve().as_posix().rstrip("/")
            return f"{root_prefix}/{suffix}" if suffix else root_prefix
    return normalized


def _fidelity_name(value: str | Any) -> str:
    normalized = str(getattr(value, "value", value)).upper()
    return normalized if normalized in _FIDELITY_ORDER else "L0"


def _observed_fidelity(probe: ReadinessBackendProbe) -> str:
    if not probe.available:
        return "unavailable"
    observed = _fidelity_name(probe.observed_fidelity)
    if observed not in _FIDELITY_ORDER:
        return "L0"
    return observed


def _preview_token(
    root: Path,
    remediation_id: str,
    before: Mapping[str, str],
    candidate: Mapping[str, str],
    report: StudioReadinessReport,
) -> str:
    payload = {
        "path": str(root),
        "remediation_id": remediation_id,
        "before": dict(sorted(before.items())),
        "candidate": dict(sorted(candidate.items())),
        "report": report.normalized(),
    }
    return _stable_id(json.dumps(payload, sort_keys=True, separators=(",", ":")), length=32)


def _stable_id(value: str, *, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _sorted_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sorted_json_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list)):
        return [_sorted_json_value(item) for item in value]
    if isinstance(value, StrEnum):
        return str(value)
    return value


def _profile_documents(
    root: Path, contents: ProjectContents
) -> list[tuple[str, str, Mapping[str, Any]]]:
    try:
        raw = yaml.safe_load(contents.cell_yaml)
    except yaml.YAMLError:
        return []
    declared = raw.get("deployment_profiles", []) if isinstance(raw, Mapping) else []
    result: list[tuple[str, str, Mapping[str, Any]]] = []
    if not isinstance(declared, list):
        return result
    for item in declared:
        if not isinstance(item, str) or not item.strip():
            continue
        relative = Path(item).as_posix()
        text: str | None = None
        if relative in contents.artifacts:
            try:
                text = contents.artifacts[relative].decode("utf-8")
            except UnicodeDecodeError:
                continue
        else:
            text = _read_text(root / relative)
        if text is None:
            continue
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        if not isinstance(data, Mapping):
            continue
        runtime = data.get("runtime", {})
        fidelity = runtime.get("simulation_fidelity") if isinstance(runtime, Mapping) else None
        result.append((relative, _fidelity_name(fidelity or "L0"), data))
    return result


def _remediation_title(remediation_id: str) -> str:
    return remediation_id.removeprefix("readiness.").replace("-", " ").replace("_", " ").title()


def _remediation_description(remediation_id: str) -> str:
    if remediation_id == "readiness.configure-simulation-backend":
        return (
            "Review the selected deployment profile and backend capability, then preview the "
            "change."
        )
    if remediation_id == "readiness.review-independent-safety":
        return (
            "Open the independent rated-hardware safety review; no software readiness result "
            "authorizes operation."
        )
    if remediation_id == "readiness.run-scenario-evidence":
        return (
            "Run a declared scenario through the existing simulation service and review its "
            "evidence."
        )
    return (
        "Open the linked existing validator or authoring service and stage a candidate for review."
    )


def _readiness_schema_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "schemas" / "studio_readiness_report.schema.json"
        if candidate.is_file():
            return candidate
    return current.parent / "studio_readiness_report.schema.json"


__all__ = [
    "EvaluateStudioReadiness",
    "ReadinessBackendProbe",
    "ReadinessCandidatePreview",
    "ReadinessCategory",
    "ReadinessRemediation",
    "ReadinessSaveResult",
    "ReadinessService",
    "ReadinessSeverity",
    "ReadinessStatus",
    "SAFETY_REVIEW_DISCLAIMER",
    "StudioProjectIdentity",
    "StudioReadinessCheck",
    "StudioReadinessReport",
    "StudioReadinessService",
    "StudioReadinessSummary",
    "evaluate_studio_readiness",
    "validate_studio_readiness_report_document",
]
