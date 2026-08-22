"""Deterministic, preview-first Studio project launcher services.

The launcher is deliberately independent of Kit.  It inventories the canonical example trees,
renders an in-memory candidate, validates that candidate through the existing project service,
and only materializes it after an explicit confirmation command.  The preview is diagnostic
data; ``cell.yaml`` and the referenced USD/BehaviorTree/recipe/scenario files remain the only
canonical project sources.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import yaml
from cellforge_cli.projects import initialize_project
from jsonschema import Draft202012Validator

from cellforge.studio.application import (
    BackendProject,
    ProjectContents,
    ValidationItem,
)
from cellforge.studio.project_service import ProjectCommandService, ProjectSaveError

GUIDED_PREVIEW_SCHEMA_VERSION = "0.1.0"
SUPPORTED_PROJECT_SCHEMA_VERSIONS = ("0.1.0",)
_STABLE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_SKIPPED_DIRECTORIES = {".git", ".venv", "__pycache__", ".pytest_cache", ".pytest_tmp"}


@dataclass(frozen=True, slots=True)
class GuidedFinding:
    """A deterministic launcher finding suitable for a panel or JSON report."""

    code: str
    severity: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        """Return the stable JSON representation of the finding."""

        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class RequiredChoice:
    """An explicit user choice required before a candidate can be saved."""

    key: str
    prompt: str
    options: tuple[str, ...]
    reason: str
    source: str = "launcher"

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible choice description."""

        return {
            "key": self.key,
            "prompt": self.prompt,
            "options": list(self.options),
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ProjectTemplateDescriptor:
    """Read-only metadata for one supported guided-project starting point."""

    template_id: str
    name: str
    description: str
    source_directory: Path | None
    supported_schema_versions: tuple[str, ...] = SUPPORTED_PROJECT_SCHEMA_VERSIONS
    starting_mode: str = "simulation"
    simulation_only: bool = True

    @property
    def source_path(self) -> Path | None:
        """Compatibility alias used by callers that treat descriptors as file records."""

        return self.source_directory

    def as_dict(self) -> dict[str, object]:
        """Return the descriptor without exposing mutable service state."""

        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "source_directory": (
                self.source_directory.as_posix() if self.source_directory is not None else None
            ),
            "supported_schema_versions": list(self.supported_schema_versions),
            "starting_mode": self.starting_mode,
            "simulation_only": self.simulation_only,
        }


@dataclass(frozen=True, slots=True)
class CreateProjectRequest:
    """Inputs for deterministic Create/Review project allocation."""

    template_id: str
    destination_directory: str | Path
    cell_display_name: str
    requested_schema_version: str = GUIDED_PREVIEW_SCHEMA_VERSION
    explicit_choices: Mapping[str, str] = field(default_factory=dict)
    seed: int = 0

    @property
    def destination(self) -> Path:
        """Resolve the destination without using the display name as a path."""

        return Path(self.destination_directory).expanduser().resolve()

    @property
    def choices(self) -> Mapping[str, str]:
        """Short alias for UI callers."""

        return self.explicit_choices

    def as_dict(self) -> dict[str, object]:
        """Return stable request data used for draft identity and diagnostics."""

        return {
            "template_id": self.template_id,
            "destination_directory": self.destination.as_posix(),
            "cell_display_name": self.cell_display_name,
            "requested_schema_version": self.requested_schema_version,
            "explicit_choices": {
                str(key): str(value) for key, value in sorted(self.explicit_choices.items())
            },
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class ProjectPreview:
    """Complete deterministic in-memory skeleton preview.

    ``candidate_hashes`` contains one SHA-256 digest per generated relative path and
    ``candidate_hash`` hashes that sorted digest inventory.  The candidate bytes themselves are
    retained only by the launcher draft and are never a second canonical source.
    """

    preview_schema_version: str
    draft_id: str
    template_id: str
    destination_directory: str
    starting_mode: str
    simulation_only: bool
    schema_versions: Mapping[str, str]
    cell_id: str | None
    component_instance_ids: tuple[str, ...]
    aliases: Mapping[str, str]
    defaults: Mapping[str, object]
    generated_paths: tuple[str, ...]
    candidate_hashes: Mapping[str, str]
    candidate_hash: str
    findings: tuple[GuidedFinding, ...]
    required_choices: tuple[RequiredChoice, ...]
    can_save: bool
    confirmation_token: str

    @property
    def generated_relative_paths(self) -> tuple[str, ...]:
        """Name used by the public task contract."""

        return self.generated_paths

    @property
    def unresolved_choices(self) -> tuple[RequiredChoice, ...]:
        """Name used by review panels for choices that block Save."""

        return self.required_choices

    @property
    def exact_candidate_hashes(self) -> Mapping[str, str]:
        """Return the per-file candidate digests."""

        return self.candidate_hashes

    @property
    def candidate_digest(self) -> str:
        """Compatibility alias for the complete candidate digest."""

        return self.candidate_hash

    def as_dict(self) -> dict[str, object]:
        """Serialize the preview for optional, explicit diagnostic export."""

        return {
            "preview_schema_version": self.preview_schema_version,
            "draft_id": self.draft_id,
            "template_id": self.template_id,
            "destination_directory": self.destination_directory,
            "starting_mode": self.starting_mode,
            "simulation_only": self.simulation_only,
            "schema_versions": dict(sorted(self.schema_versions.items())),
            "cell_id": self.cell_id,
            "component_instance_ids": list(self.component_instance_ids),
            "aliases": dict(sorted(self.aliases.items())),
            "defaults": _json_value(self.defaults),
            "generated_paths": list(self.generated_paths),
            "candidate_hashes": dict(sorted(self.candidate_hashes.items())),
            "candidate_hash": self.candidate_hash,
            "findings": [finding.as_dict() for finding in self.findings],
            "required_choices": [choice.as_dict() for choice in self.required_choices],
            "can_save": self.can_save,
            "confirmation_token": self.confirmation_token,
        }

    def to_json(self) -> str:
        """Return deterministic JSON without writing any file."""

        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class OpenProjectResult:
    """Read-only result of the guided Open command."""

    project: BackendProject | None
    contents: ProjectContents | None
    findings: tuple[GuidedFinding, ...]
    source_hashes: Mapping[str, str]
    dirty: bool = False

    @property
    def validation(self) -> tuple[GuidedFinding, ...]:
        """Compatibility alias for application-service consumers."""

        return self.findings

    @property
    def is_valid(self) -> bool:
        """Whether the existing project passed the canonical validator."""

        return self.project is not None and not self.findings


@dataclass(frozen=True, slots=True)
class ProjectSaveResult:
    """Result of explicit confirmed persistence."""

    success: bool
    project: BackendProject | None
    contents: ProjectContents | None
    preview: ProjectPreview
    findings: tuple[GuidedFinding, ...] = ()
    recovery_journal: str | None = None

    @property
    def validation(self) -> tuple[GuidedFinding, ...]:
        """Compatibility alias for save-panel consumers."""

        return self.findings


@dataclass(frozen=True, slots=True)
class CancelProjectDraftResult:
    """Result of cancelling an in-memory draft."""

    cancelled: bool
    draft_id: str
    findings: tuple[GuidedFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class _Candidate:
    files: Mapping[str, bytes]
    cell_id: str | None
    component_instance_ids: tuple[str, ...]
    aliases: Mapping[str, str]
    schema_versions: Mapping[str, str]
    defaults: Mapping[str, object]
    findings: tuple[GuidedFinding, ...]
    required_choices: tuple[RequiredChoice, ...]


@dataclass(frozen=True, slots=True)
class _Draft:
    request: CreateProjectRequest
    preview: ProjectPreview
    candidate: _Candidate


class GuidedProjectService:
    """Pure application service for deterministic guided project creation and review."""

    def __init__(
        self,
        canonical_schema_directory: Path,
        *,
        repository_root: Path | None = None,
        project_service: ProjectCommandService | None = None,
        template_descriptors: Sequence[ProjectTemplateDescriptor] | None = None,
        templates: Sequence[ProjectTemplateDescriptor] | None = None,
    ) -> None:
        self._schemas = canonical_schema_directory.resolve()
        self._repository_root = (repository_root or self._schemas.parent).resolve()
        self._project_service = project_service or ProjectCommandService(self._schemas)
        supplied = template_descriptors if template_descriptors is not None else templates
        self._templates = tuple(supplied or self._default_templates())
        self._drafts: dict[str, _Draft] = {}

    @property
    def templates(self) -> tuple[ProjectTemplateDescriptor, ...]:
        """Return the read-only supported template inventory."""

        return self._templates

    def list_templates(self) -> tuple[ProjectTemplateDescriptor, ...]:
        """Return templates in stable ID order."""

        return tuple(sorted(self._templates, key=lambda item: item.template_id))

    def CreateProject(self, request: CreateProjectRequest) -> ProjectPreview:
        """Create an in-memory draft and return its complete preview."""

        draft_id = _draft_id(request)
        candidate = self._build_candidate(request)
        preview = self._preview(request, draft_id, candidate)
        self._drafts[draft_id] = _Draft(request=request, preview=preview, candidate=candidate)
        return preview

    def create_project(self, request: CreateProjectRequest) -> ProjectPreview:
        """Snake-case alias for Python callers."""

        return self.CreateProject(request)

    def PreviewProject(self, draft: str | ProjectPreview | CreateProjectRequest) -> ProjectPreview:
        """Recompute a draft preview without writing canonical or diagnostic files."""

        if isinstance(draft, CreateProjectRequest):
            return self.CreateProject(draft)
        draft_id = draft if isinstance(draft, str) else draft.draft_id
        current = self._drafts.get(draft_id)
        if current is None:
            return self._missing_preview(draft_id)
        candidate = self._build_candidate(current.request)
        preview = self._preview(current.request, draft_id, candidate)
        self._drafts[draft_id] = _Draft(
            request=current.request,
            preview=preview,
            candidate=candidate,
        )
        return preview

    def preview_project(self, draft: str | ProjectPreview | CreateProjectRequest) -> ProjectPreview:
        """Snake-case alias for Python callers."""

        return self.PreviewProject(draft)

    def OpenProject(self, project_path: str | Path) -> OpenProjectResult:
        """Inspect an existing project read-only through Task 015's service boundary."""

        root = Path(project_path).expanduser().resolve()
        if not root.is_dir():
            return OpenProjectResult(
                project=None,
                contents=None,
                findings=(
                    _finding(
                        "studio.open-project-not-found",
                        root,
                        "Project directory does not exist or is not a directory.",
                    ),
                ),
                source_hashes={},
            )
        try:
            result = self._project_service.inspect_candidate(
                root,
                validate_studio_extensions=False,
            )
        except Exception as error:
            return OpenProjectResult(
                project=None,
                contents=None,
                findings=(
                    _finding(
                        "studio.open-project-failed",
                        root,
                        f"Project inspection failed ({type(error).__name__}).",
                    ),
                ),
                source_hashes=_hash_tree(root),
            )
        return OpenProjectResult(
            project=result.project,
            contents=result.contents,
            findings=tuple(_guided_finding(item) for item in result.validation),
            source_hashes=_hash_tree(root),
        )

    def open_project(self, project_path: str | Path) -> OpenProjectResult:
        """Snake-case alias for Python callers."""

        return self.OpenProject(project_path)

    def ConfirmProjectSave(
        self,
        draft: str | ProjectPreview,
        confirmation_token: str | None = None,
        *,
        confirmed: bool = False,
        confirm: bool | None = None,
    ) -> ProjectSaveResult:
        """Validate and explicitly persist a reviewed draft as one new project tree."""

        draft_id = draft if isinstance(draft, str) else draft.draft_id
        current = self._drafts.get(draft_id)
        preview = (
            current.preview
            if current is not None
            else (draft if isinstance(draft, ProjectPreview) else self._missing_preview(draft_id))
        )
        if current is None:
            return ProjectSaveResult(
                success=False,
                project=None,
                contents=None,
                preview=preview,
                findings=(
                    _finding(
                        "studio.draft-not-found",
                        Path(preview.destination_directory),
                        f"Guided draft '{draft_id}' is not available.",
                    ),
                ),
            )
        if confirm is not None:
            confirmed = confirm
        if not confirmed and confirmation_token != preview.confirmation_token:
            return ProjectSaveResult(
                success=False,
                project=None,
                contents=None,
                preview=preview,
                findings=(
                    _finding(
                        "studio.save-confirmation-required",
                        Path(preview.destination_directory),
                        "Explicit confirmation and the current preview token are required to save.",
                    ),
                ),
            )

        refreshed = self.PreviewProject(draft_id)
        current = self._drafts[draft_id]
        if refreshed.candidate_hash != preview.candidate_hash:
            return ProjectSaveResult(
                success=False,
                project=None,
                contents=None,
                preview=refreshed,
                findings=(
                    _finding(
                        "studio.preview-stale",
                        Path(refreshed.destination_directory),
                        "The candidate changed after review; preview it again before Save.",
                    ),
                ),
            )
        if not refreshed.can_save:
            return ProjectSaveResult(
                success=False,
                project=None,
                contents=None,
                preview=refreshed,
                findings=refreshed.findings
                + (
                    _finding(
                        "studio.save-blocked",
                        Path(refreshed.destination_directory),
                        "The reviewed candidate has unresolved choices or validation findings.",
                    ),
                ),
            )

        try:
            result = self._project_service.save_new_project(
                Path(refreshed.destination_directory),
                current.candidate.files,
                validate_studio_extensions=False,
            )
        except ProjectSaveError as error:
            journal = _recovery_path_from_error(error)
            return ProjectSaveResult(
                success=False,
                project=None,
                contents=None,
                preview=refreshed,
                findings=(
                    _finding(
                        "studio.save-transaction-failed",
                        Path(refreshed.destination_directory),
                        str(error),
                    ),
                ),
                recovery_journal=journal,
            )
        except Exception as error:
            return ProjectSaveResult(
                success=False,
                project=None,
                contents=None,
                preview=refreshed,
                findings=(
                    _finding(
                        "studio.save-failed",
                        Path(refreshed.destination_directory),
                        f"Save failed ({type(error).__name__}); no partial project was accepted.",
                    ),
                ),
            )

        if result.project is None or result.contents is None:
            findings = tuple(_guided_finding(item) for item in result.validation)
            return ProjectSaveResult(
                success=False,
                project=None,
                contents=None,
                preview=refreshed,
                findings=findings
                or (
                    _finding(
                        "studio.save-failed",
                        Path(refreshed.destination_directory),
                        "The candidate was not accepted by the canonical project validator.",
                    ),
                ),
            )

        self._drafts.pop(draft_id, None)
        reopened = self.OpenProject(refreshed.destination_directory)
        if not reopened.is_valid:
            return ProjectSaveResult(
                success=False,
                project=None,
                contents=None,
                preview=refreshed,
                findings=reopened.findings
                + (
                    _finding(
                        "studio.reopen-after-save-failed",
                        Path(refreshed.destination_directory),
                        "Saved project could not be reopened with the same canonical validation.",
                    ),
                ),
            )
        return ProjectSaveResult(
            success=True,
            project=reopened.project,
            contents=reopened.contents,
            preview=refreshed,
        )

    def confirm_project_save(
        self,
        draft: str | ProjectPreview,
        confirmation_token: str | None = None,
        *,
        confirmed: bool = False,
        confirm: bool | None = None,
    ) -> ProjectSaveResult:
        """Snake-case alias for the explicit Save command."""

        return self.ConfirmProjectSave(
            draft,
            confirmation_token,
            confirmed=confirmed,
            confirm=confirm,
        )

    def CancelProjectDraft(self, draft: str | ProjectPreview) -> CancelProjectDraftResult:
        """Discard only the in-memory draft; no canonical file is touched."""

        draft_id = draft if isinstance(draft, str) else draft.draft_id
        if self._drafts.pop(draft_id, None) is not None:
            return CancelProjectDraftResult(cancelled=True, draft_id=draft_id)
        return CancelProjectDraftResult(
            cancelled=False,
            draft_id=draft_id,
            findings=(
                _finding(
                    "studio.draft-not-found",
                    Path("."),
                    f"Guided draft '{draft_id}' is not available.",
                ),
            ),
        )

    def cancel_project_draft(self, draft: str | ProjectPreview) -> CancelProjectDraftResult:
        """Snake-case alias for the cancel command."""

        return self.CancelProjectDraft(draft)

    def export_preview(
        self,
        preview: str | ProjectPreview,
        destination: str | Path,
    ) -> Path:
        """Explicitly export validated diagnostic DTO data, never canonical project files."""

        resolved = self.PreviewProject(preview) if isinstance(preview, str) else preview
        validate_project_preview_document(resolved.as_dict())
        path = Path(destination).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(resolved.to_json(), encoding="utf-8", newline="\n")
        return path

    def _default_templates(self) -> tuple[ProjectTemplateDescriptor, ...]:
        examples = self._repository_root / "examples"
        return (
            ProjectTemplateDescriptor(
                template_id="blank",
                name="Blank simulation cell",
                description=(
                    "Capability-free engineering scaffold with a paired cell.yaml and USDA "
                    "workspace marker."
                ),
                source_directory=None,
            ),
            ProjectTemplateDescriptor(
                template_id="pen_engraving",
                name="Pen engraving reference cell",
                description="Canonical Task 013/027 pen workflow with L0/L2 evidence boundaries.",
                source_directory=examples / "pen_engraving",
            ),
            ProjectTemplateDescriptor(
                template_id="kitting",
                name="Two-part tray kitting cell",
                description="Canonical Task 038 reusable L0 kitting workflow.",
                source_directory=examples / "kitting",
            ),
        )

    def _build_candidate(self, request: CreateProjectRequest) -> _Candidate:
        findings: list[GuidedFinding] = []
        choices: list[RequiredChoice] = []
        destination = request.destination
        if not str(request.destination_directory).strip():
            findings.append(
                _finding(
                    "studio.destination-required",
                    destination,
                    "A destination directory is required.",
                )
            )
        if _contains_parent_segment(request.destination_directory):
            findings.append(
                _finding(
                    "studio.destination-path-escape",
                    destination,
                    "Destination paths containing parent traversal are not accepted.",
                )
            )

        template, template_findings, template_choices = self._resolve_template(request.template_id)
        findings.extend(template_findings)
        choices.extend(template_choices)
        if template is None:
            return _Candidate(
                files={},
                cell_id=None,
                component_instance_ids=(),
                aliases={},
                schema_versions={},
                defaults={"mode": "simulation", "simulation_only": True},
                findings=tuple(_sorted_findings(findings)),
                required_choices=tuple(choices),
            )

        if request.requested_schema_version not in template.supported_schema_versions:
            findings.append(
                _finding(
                    "studio.schema-version-unsupported",
                    destination / "cell.yaml",
                    (
                        f"Template '{template.template_id}' does not support schema version "
                        f"'{request.requested_schema_version}'."
                    ),
                )
            )
        if request.seed < 0:
            findings.append(
                _finding(
                    "studio.seed-invalid",
                    destination,
                    "The deterministic allocation seed must be non-negative.",
                )
            )
        if not request.cell_display_name.strip():
            choices.append(
                RequiredChoice(
                    key="cell_display_name",
                    prompt="Choose a cell display name",
                    options=(),
                    reason="A blank display name is ambiguous and is never generated from a path.",
                )
            )

        if destination.exists() or destination.is_symlink():
            findings.append(
                _finding(
                    "studio.destination-exists",
                    destination,
                    "The destination already exists; Save will not overwrite it.",
                )
            )
        if template.source_directory is not None:
            source = template.source_directory.resolve()
            if not source.is_dir():
                findings.append(
                    _finding(
                        "studio.template-source-missing",
                        source,
                        f"Template source '{source}' is unavailable.",
                    )
                )
            elif destination == source or destination.is_relative_to(source):
                findings.append(
                    _finding(
                        "studio.destination-inside-template",
                        destination,
                        "A template cannot be saved over or inside its canonical source tree.",
                    )
                )

        source_files: dict[str, bytes] = {}
        if not any(item.severity == "error" for item in findings) and (
            template.source_directory is None or template.source_directory.is_dir()
        ):
            if template.source_directory is None:
                source_files, starter_findings = self._blank_files()
            else:
                source_files, starter_findings = self._source_files(template.source_directory)
            findings.extend(starter_findings)

        if not source_files:
            return _Candidate(
                files={},
                cell_id=None,
                component_instance_ids=(),
                aliases={},
                schema_versions={},
                defaults={"mode": template.starting_mode, "simulation_only": True},
                findings=tuple(_sorted_findings(findings)),
                required_choices=tuple(choices),
            )

        cell_text = _decode_text(source_files, "cell.yaml", findings, destination)
        if cell_text is None:
            return _Candidate(
                files=source_files,
                cell_id=None,
                component_instance_ids=(),
                aliases={},
                schema_versions={},
                defaults={"mode": template.starting_mode, "simulation_only": True},
                findings=tuple(_sorted_findings(findings)),
                required_choices=tuple(choices),
            )

        try:
            raw_cell = yaml.safe_load(cell_text)
        except yaml.YAMLError:
            raw_cell = None
        if not isinstance(raw_cell, Mapping):
            findings.append(
                _finding(
                    "studio.cell-document-invalid",
                    destination / "cell.yaml",
                    "Template cell.yaml must contain an object before it can be previewed.",
                )
            )
            return _Candidate(
                files=source_files,
                cell_id=None,
                component_instance_ids=(),
                aliases={},
                schema_versions={},
                defaults={"mode": template.starting_mode, "simulation_only": True},
                findings=tuple(_sorted_findings(findings)),
                required_choices=tuple(choices),
            )

        cell_record = raw_cell.get("cell")
        raw_components = raw_cell.get("components")
        if not isinstance(cell_record, Mapping) or not isinstance(raw_components, Sequence):
            findings.append(
                _finding(
                    "studio.cell-document-invalid",
                    destination / "cell.yaml",
                    "Template cell.yaml is missing the cell identity or component list.",
                )
            )
            return _Candidate(
                files=source_files,
                cell_id=None,
                component_instance_ids=(),
                aliases={},
                schema_versions={},
                defaults={"mode": template.starting_mode, "simulation_only": True},
                findings=tuple(_sorted_findings(findings)),
                required_choices=tuple(choices),
            )

        old_cell_id = str(cell_record.get("id", ""))
        cell_id = old_cell_id
        if template.template_id == "blank":
            cell_id = _choice(request.explicit_choices, "cell_id") or str(
                uuid5(NAMESPACE_URL, f"cellforge-guided/{request.seed}/blank/cell")
            )
            if not _UUID.fullmatch(cell_id):
                findings.append(
                    _finding(
                        "studio.cell-id-invalid",
                        destination / "cell.yaml#/cell/id",
                        "Allocated cell ID is not a UUID.",
                    )
                )
        elif _choice(request.explicit_choices, "cell_id") not in (None, old_cell_id):
            findings.append(
                _finding(
                    "studio.choice-immutable",
                    destination / "cell.yaml#/cell/id",
                    "Supported example templates retain their canonical cell ID "
                    "for simulation compatibility.",
                )
            )

        if not old_cell_id:
            findings.append(
                _finding(
                    "studio.cell-id-missing",
                    destination / "cell.yaml#/cell/id",
                    "Template cell identity is missing.",
                )
            )
        if not request.seed >= 0:
            cell_id = old_cell_id

        component_ids: list[str] = []
        aliases: dict[str, str] = {}
        replacements: dict[str, str] = {}
        for index, component in enumerate(raw_components):
            if not isinstance(component, Mapping):
                findings.append(
                    _finding(
                        "studio.component-invalid",
                        destination / f"cell.yaml#/components/{index}",
                        "Component entries must be objects.",
                    )
                )
                continue
            old_id = str(component.get("id", ""))
            allocated_id = _choice(request.explicit_choices, f"component_id:{old_id}") or old_id
            alias = _choice(request.explicit_choices, f"alias:{old_id}") or str(
                component.get("alias", "")
            )
            if not _STABLE_ID.fullmatch(allocated_id):
                findings.append(
                    _finding(
                        "studio.component-id-invalid",
                        destination / f"cell.yaml#/components/{index}/id",
                        f"Component ID '{allocated_id}' is not a lowercase stable identifier.",
                    )
                )
            if not _STABLE_ID.fullmatch(alias):
                findings.append(
                    _finding(
                        "studio.alias-invalid",
                        destination / f"cell.yaml#/components/{index}/alias",
                        f"Alias '{alias}' is not a lowercase stable identifier.",
                    )
                )
            if allocated_id in component_ids:
                findings.append(
                    _finding(
                        "studio.component-id-duplicate",
                        destination / "cell.yaml#/components",
                        f"Component instance ID '{allocated_id}' is duplicated.",
                    )
                )
            component_ids.append(allocated_id)
            aliases[allocated_id] = alias
            if old_id and old_id != allocated_id:
                replacements[old_id] = allocated_id

        mode = _choice(request.explicit_choices, "mode") or template.starting_mode
        if mode != "simulation":
            findings.append(
                _finding(
                    "studio.simulation-mode-required",
                    destination,
                    "Guided starting projects are simulation-only; physical targets "
                    "are not selectable.",
                )
            )

        cell_text = _replace_cell_identity(
            cell_text,
            old_cell_id=old_cell_id,
            cell_id=cell_id,
            display_name=request.cell_display_name,
            replacements=replacements,
            aliases=aliases,
            original_components=raw_components,
        )
        cell_text = cell_text.replace(
            "../../schemas/recipe.schema.json", "schemas/recipe.schema.json"
        )
        source_files["cell.yaml"] = cell_text.encode("utf-8")
        if "scene.usda" in source_files:
            scene_text = _decode_text(source_files, "scene.usda", findings, destination)
            if scene_text is not None:
                for old_id, new_id in replacements.items():
                    scene_text = scene_text.replace(
                        f'cellforge:instanceId = "{old_id}"',
                        f'cellforge:instanceId = "{new_id}"',
                    )
                source_files["scene.usda"] = scene_text.encode("utf-8")

        for required in ("cell.yaml", "scene.usda", "behavior_tree.xml"):
            if required not in source_files:
                findings.append(
                    _finding(
                        "studio.canonical-file-missing",
                        destination / required,
                        f"Guided candidate is missing canonical file '{required}'.",
                    )
                )

        # The schema set is copied into every guided candidate so recipe references are local,
        # exact, and independently reopenable.  It is never edited by the launcher.
        for schema_path in sorted(self._schemas.glob("*.json")):
            if schema_path.name == "studio_project_preview.schema.json":
                continue
            relative = f"schemas/{schema_path.name}"
            try:
                source_files[relative] = schema_path.read_bytes()
            except OSError as error:
                findings.append(
                    _finding(
                        "studio.schema-copy-failed",
                        schema_path,
                        f"Could not read canonical schema ({type(error).__name__}).",
                    )
                )

        findings.extend(self._validate_candidate(source_files, destination))
        schema_versions = _schema_versions(source_files)
        defaults: dict[str, object] = {
            "mode": "simulation",
            "simulation_only": True,
            "cell_id": cell_id,
            "component_ids": dict(
                zip(
                    tuple(
                        str(item.get("id", ""))
                        for item in raw_components
                        if isinstance(item, Mapping)
                    ),
                    component_ids,
                    strict=False,
                )
            ),
            "aliases": dict(sorted(aliases.items())),
        }
        return _Candidate(
            files=source_files,
            cell_id=cell_id,
            component_instance_ids=tuple(component_ids),
            aliases=aliases,
            schema_versions=schema_versions,
            defaults=defaults,
            findings=tuple(_sorted_findings(findings)),
            required_choices=tuple(sorted(choices, key=lambda item: item.key)),
        )

    def _validate_candidate(
        self, files: Mapping[str, bytes], destination: Path
    ) -> tuple[GuidedFinding, ...]:
        """Run the existing project/scene/recipe/scenario validator on an isolated tree."""

        with tempfile.TemporaryDirectory(prefix="cellforge-guided-validation-") as temporary:
            staged = Path(temporary)
            try:
                for relative, content in files.items():
                    target = staged / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                result = self._project_service.inspect_candidate(
                    staged,
                    validate_studio_extensions=False,
                )
            except Exception as error:
                return (
                    _finding(
                        "studio.preview-validation-failed",
                        destination,
                        f"Candidate validation failed ({type(error).__name__}); Save is blocked.",
                    ),
                )
            source_prefix = str(staged.resolve())
            destination_prefix = str(destination.resolve())
            findings = tuple(
                GuidedFinding(
                    code=item.code,
                    severity=item.severity,
                    path=item.path.replace(source_prefix, destination_prefix, 1),
                    message=item.message,
                )
                for item in result.validation
            )
            if result.project is None and not findings:
                return (
                    _finding(
                        "studio.preview-validation-failed",
                        destination,
                        "Candidate validation returned no project and no diagnostic finding.",
                    ),
                )
            return findings

    def _source_files(self, source: Path) -> tuple[dict[str, bytes], tuple[GuidedFinding, ...]]:
        files: dict[str, bytes] = {}
        findings: list[GuidedFinding] = []
        try:
            paths = sorted(source.rglob("*"))
        except OSError as error:
            return {}, (
                _finding(
                    "studio.template-read-failed",
                    source,
                    f"Could not enumerate template source ({type(error).__name__}).",
                ),
            )
        for path in paths:
            relative_path = path.relative_to(source)
            if not path.is_file() or any(
                part in _SKIPPED_DIRECTORIES for part in relative_path.parts
            ):
                continue
            relative = relative_path.as_posix()
            if _unsafe_relative_path(relative) or relative.startswith("schemas/"):
                findings.append(
                    _finding(
                        "studio.template-path-invalid",
                        path,
                        f"Template file path '{relative}' is not a safe project-relative path.",
                    )
                )
                continue
            try:
                files[relative] = path.read_bytes()
            except OSError as error:
                findings.append(
                    _finding(
                        "studio.template-read-failed",
                        path,
                        f"Could not read template file ({type(error).__name__}).",
                    )
                )
        return files, tuple(findings)

    def _blank_files(self) -> tuple[dict[str, bytes], tuple[GuidedFinding, ...]]:
        """Render the existing CLI starter into an isolated temporary source tree."""

        with tempfile.TemporaryDirectory(prefix="cellforge-guided-starter-") as temporary:
            source = Path(temporary) / "starter"
            try:
                initialize_project(source)
            except Exception as error:
                return {}, (
                    _finding(
                        "studio.blank-template-failed",
                        source,
                        "The canonical blank starter could not be rendered "
                        f"({type(error).__name__}).",
                    ),
                )
            return self._source_files(source)

    def _resolve_template(
        self, template_id: str
    ) -> tuple[
        ProjectTemplateDescriptor | None,
        tuple[GuidedFinding, ...],
        tuple[RequiredChoice, ...],
    ]:
        normalized = template_id.strip().lower()
        exact = tuple(item for item in self._templates if item.template_id == normalized)
        if len(exact) == 1:
            return exact[0], (), ()
        matches = tuple(
            sorted(
                item.template_id
                for item in self._templates
                if normalized and item.template_id.startswith(normalized)
            )
        )
        if len(matches) > 1:
            return (
                None,
                (),
                (
                    RequiredChoice(
                        key="template_id",
                        prompt="Choose one guided project template",
                        options=matches,
                        reason="The supplied template selector matches multiple "
                        "supported templates.",
                    ),
                ),
            )
        return (
            None,
            (
                _finding(
                    "studio.template-not-found",
                    Path("."),
                    f"Supported guided template '{template_id}' was not found.",
                ),
            ),
            (),
        )

    def _preview(
        self,
        request: CreateProjectRequest,
        draft_id: str,
        candidate: _Candidate,
    ) -> ProjectPreview:
        destination = request.destination
        hashes = _file_hashes(candidate.files)
        candidate_hash = _candidate_hash(hashes)
        findings = tuple(_sorted_findings(candidate.findings))
        can_save = (
            bool(candidate.files)
            and not candidate.required_choices
            and not any(item.severity == "error" for item in findings)
            and not destination.exists()
            and not destination.is_symlink()
        )
        if candidate.files and not any(
            item.code.startswith("studio.destination") for item in findings
        ):
            findings = findings + (
                GuidedFinding(
                    code="studio.simulation-only-start",
                    severity="warning",
                    path=f"{destination}#",
                    message=(
                        "This guided project starts in simulation-only mode. It does not "
                        "implement or certify independent functional safety."
                    ),
                ),
            )
            findings = tuple(_sorted_findings(findings))
        token = hashlib.sha256(
            f"{draft_id}:{destination.as_posix()}:{candidate_hash}".encode()
        ).hexdigest()
        return ProjectPreview(
            preview_schema_version=GUIDED_PREVIEW_SCHEMA_VERSION,
            draft_id=draft_id,
            template_id=request.template_id.strip().lower(),
            destination_directory=destination.as_posix(),
            starting_mode="simulation",
            simulation_only=True,
            schema_versions=dict(sorted(candidate.schema_versions.items())),
            cell_id=candidate.cell_id,
            component_instance_ids=tuple(candidate.component_instance_ids),
            aliases=dict(sorted(candidate.aliases.items())),
            defaults=_json_value(candidate.defaults),
            generated_paths=tuple(sorted(candidate.files)),
            candidate_hashes=hashes,
            candidate_hash=candidate_hash,
            findings=findings,
            required_choices=tuple(candidate.required_choices),
            can_save=can_save,
            confirmation_token=token,
        )

    def _missing_preview(self, draft_id: str) -> ProjectPreview:
        finding = _finding(
            "studio.draft-not-found",
            Path("."),
            f"Guided draft '{draft_id}' is not available.",
        )
        return ProjectPreview(
            preview_schema_version=GUIDED_PREVIEW_SCHEMA_VERSION,
            draft_id=draft_id,
            template_id="unknown",
            destination_directory=".",
            starting_mode="simulation",
            simulation_only=True,
            schema_versions={},
            cell_id=None,
            component_instance_ids=(),
            aliases={},
            defaults={"mode": "simulation", "simulation_only": True},
            generated_paths=(),
            candidate_hashes={},
            candidate_hash=_candidate_hash({}),
            findings=(finding,),
            required_choices=(),
            can_save=False,
            confirmation_token="",
        )


# The task names these commands explicitly.  Aliases make the service easy to discover while
# keeping one implementation and one draft registry.
GuidedStudioService = GuidedProjectService
StudioProjectLauncher = GuidedProjectService
CreateProject = CreateProjectRequest
PreviewProject = ProjectPreview
ConfirmProjectSave = ProjectSaveResult
CancelProjectDraft = CancelProjectDraftResult
OpenProject = OpenProjectResult


def validate_project_preview_document(document: Mapping[str, object]) -> None:
    """Validate an exported preview DTO against the versioned preview schema."""

    schema_path = (
        Path(__file__).resolve().parents[5] / "schemas" / "studio_project_preview.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(dict(document)),
        key=lambda error: (tuple(str(item) for item in error.absolute_path), error.message),
    )
    if errors:
        first = errors[0]
        pointer = "/".join(str(item) for item in first.absolute_path)
        raise ValueError(f"Preview schema validation failed at '/{pointer}': {first.message}")


def _draft_id(request: CreateProjectRequest) -> str:
    encoded = json.dumps(
        request.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "draft-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _file_hashes(files: Mapping[str, bytes]) -> dict[str, str]:
    return {relative: hashlib.sha256(files[relative]).hexdigest() for relative in sorted(files)}


def _candidate_hash(hashes: Mapping[str, str]) -> str:
    manifest = json.dumps(dict(sorted(hashes.items())), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    try:
        paths = sorted(root.rglob("*"))
    except OSError:
        return hashes
    for path in paths:
        relative = path.relative_to(root)
        if path.is_file() and not any(part in _SKIPPED_DIRECTORIES for part in relative.parts):
            try:
                hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
    return hashes


def _schema_versions(files: Mapping[str, bytes]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for relative, content in sorted(files.items()):
        if not relative.lower().endswith((".yaml", ".yml", ".json")):
            continue
        try:
            document = yaml.safe_load(content.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError):
            continue
        if isinstance(document, Mapping) and isinstance(document.get("schema_version"), str):
            versions[relative] = str(document["schema_version"])
    return versions


def _guided_finding(item: ValidationItem) -> GuidedFinding:
    return GuidedFinding(
        code=item.code,
        severity=item.severity,
        path=item.path,
        message=item.message,
    )


def _finding(code: str, path: Path, message: str, *, severity: str = "error") -> GuidedFinding:
    return GuidedFinding(code=code, severity=severity, path=f"{path.resolve()}#", message=message)


def _sorted_findings(findings: Sequence[GuidedFinding]) -> list[GuidedFinding]:
    unique = {(item.code, item.severity, item.path, item.message): item for item in findings}
    return sorted(unique.values(), key=lambda item: (item.path, item.code, item.message))


def _choice(choices: Mapping[str, str], key: str) -> str | None:
    value = choices.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _unsafe_relative_path(relative: str) -> bool:
    path = Path(relative)
    return path.is_absolute() or ".." in path.parts or relative.startswith("/")


def _contains_parent_segment(value: str | Path) -> bool:
    return ".." in Path(value).parts


def _decode_text(
    files: Mapping[str, bytes], relative: str, findings: list[GuidedFinding], destination: Path
) -> str | None:
    content = files.get(relative)
    if content is None:
        findings.append(
            _finding(
                "studio.canonical-file-missing",
                destination / relative,
                f"Guided candidate is missing canonical file '{relative}'.",
            )
        )
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        findings.append(
            _finding(
                "studio.canonical-file-invalid-encoding",
                destination / relative,
                f"Canonical file '{relative}' is not valid UTF-8 text.",
            )
        )
        return None


def _replace_cell_identity(
    text: str,
    *,
    old_cell_id: str,
    cell_id: str,
    display_name: str,
    replacements: Mapping[str, str],
    aliases: Mapping[str, str],
    original_components: Sequence[object],
) -> str:
    lines = text.splitlines(keepends=True)
    in_cell = False
    cell_id_replaced = False
    name_replaced = False
    for index, line in enumerate(lines):
        if line.startswith("cell:"):
            in_cell = True
            continue
        if in_cell and line and not line.startswith(" "):
            in_cell = False
        if in_cell and line.startswith("  id:") and not cell_id_replaced:
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f"  id: {cell_id}{newline}"
            cell_id_replaced = True
        elif in_cell and line.startswith("  name:") and not name_replaced:
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f"  name: {json.dumps(display_name, ensure_ascii=False)}{newline}"
            name_replaced = True
    updated = "".join(lines)
    if old_cell_id and old_cell_id != cell_id:
        updated = updated.replace(old_cell_id, cell_id)
    for old_id, new_id in replacements.items():
        updated = updated.replace(f"id: {old_id}", f"id: {new_id}")
        updated = updated.replace(f"component: {old_id}", f"component: {new_id}")
        updated = updated.replace(f'component: "{old_id}"', f'component: "{new_id}"')
    for component in original_components:
        if not isinstance(component, Mapping):
            continue
        old_id = str(component.get("id", ""))
        new_id = replacements.get(old_id, old_id)
        alias = aliases.get(new_id)
        if alias is not None:
            updated = re.sub(
                rf"(?m)^(\s+alias:)\s*{re.escape(str(component.get('alias', '')))}\s*$",
                rf"\1 {alias}",
                updated,
                count=1,
            )
    return updated


def _json_value(value: object) -> Any:
    """Copy a diagnostic mapping into JSON-compatible immutable-ish values."""

    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _recovery_path_from_error(error: ProjectSaveError) -> str | None:
    match = re.search(r"at ([^.]*(?:\.cellforge-save-recovery\.json))", str(error))
    return match.group(1) if match else None
