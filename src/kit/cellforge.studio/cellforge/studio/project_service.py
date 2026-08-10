"""Pure project command service for synchronized CellForge YAML and USD sources."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from cellforge_cli.projects import (
    ProjectOperationError,
    ProjectSummary,
    initialize_project,
    inspect_project,
    resolve_project_schema_directory,
    validate_project,
)
from cellforge_domain import CellProject, SchemaRegistry, ValidationFinding
from cellforge_domain.schemas import SchemaDocumentKind
from pydantic import ValidationError

from cellforge.studio.application import (
    BackendProject,
    BackendResult,
    BrowserResult,
    ComponentEditResult,
    ComponentFilters,
    ProjectContents,
    ValidationItem,
)
from cellforge.studio.component_service import ComponentPlacementService
from cellforge.studio.scene import inspect_scene, validate_scene_cross_references

RECOVERY_FILE = ".cellforge-save-recovery.json"


class ProjectSaveError(Exception):
    """Sanitized project transaction failure returned to the application boundary."""


@dataclass(frozen=True, slots=True)
class _OpenedCandidate:
    contents: ProjectContents
    cell_data: Mapping[str, Any]
    scene_path: Path


@dataclass(frozen=True, slots=True)
class _ParsedCell:
    model: CellProject
    data: Mapping[str, Any]


class ProjectCommandService:
    """Create, open, validate, and explicitly save synchronized project sources."""

    def __init__(
        self,
        canonical_schema_directory: Path,
        *,
        replace_file: Callable[[str | Path, str | Path], None] = os.replace,
        component_service: ComponentPlacementService | None = None,
    ) -> None:
        self._canonical_schemas = canonical_schema_directory.resolve()
        self._replace_file = replace_file
        self._components = component_service or ComponentPlacementService(self._canonical_schemas)

    def create(self, project_path: Path) -> BackendResult:
        """Explicitly create a starter project and return its validated buffers."""

        initialize_project(project_path)
        return self.inspect(project_path)

    def inspect(self, project_path: Path) -> BackendResult:
        """Open and validate a project byte-for-byte without modifying any file."""

        root = project_path.resolve()
        try:
            registry = self._registry_for(root)
        except ProjectOperationError as error:
            return BackendResult(project=None, validation=(_validation_item(error.finding),))

        report = validate_project(root, registry)
        findings = [_validation_item(item) for item in report.findings]
        candidate = self._read_candidate(root)
        if isinstance(candidate, _OpenedCandidate):
            contents = candidate.contents
            scene, scene_findings = inspect_scene(contents.scene_usda, candidate.scene_path)
            findings.extend(scene_findings)
            if scene is not None:
                findings.extend(
                    validate_scene_cross_references(
                        candidate.cell_data,
                        scene,
                        cell_path=root / "cell.yaml",
                        scene_path=candidate.scene_path,
                    )
                )
        else:
            contents = None
            findings.extend(candidate)

        findings = list(_unique_findings(findings))
        if findings or contents is None:
            return BackendResult(project=None, validation=tuple(findings))
        summary = inspect_project(root, registry)
        return BackendResult(
            project=_backend_project(summary),
            validation=(),
            contents=contents,
        )

    def save(self, project_path: Path, contents: ProjectContents) -> BackendResult:
        """Validate candidates, journal previous bytes, and replace both files transactionally."""

        root = project_path.resolve()
        current = self.inspect(root)
        if current.project is None or current.contents is None:
            return current

        registry = self._registry_for(root)
        cell_path = root / "cell.yaml"
        candidate = _parse_cell_candidate(contents.cell_yaml, cell_path, registry)
        if isinstance(candidate, _ParsedCell):
            cell_model = candidate.model
            cell_data = candidate.data
        else:
            return BackendResult(project=None, validation=candidate)

        if cell_model.scene.usd != current.project.scene:
            return BackendResult(
                project=None,
                validation=(
                    ValidationItem(
                        code="studio.scene-reference-change-unsupported",
                        severity="error",
                        path=f"{cell_path}#/scene/usd",
                        message=(
                            "Task 015 does not rename the canonical scene during save; "
                            "keep the existing scene reference."
                        ),
                    ),
                ),
            )
        scene_path = _contained_scene_path(root, cell_model.scene.usd)
        if scene_path is None:
            return BackendResult(
                project=None,
                validation=(
                    ValidationItem(
                        code="studio.scene-reference-outside-project",
                        severity="error",
                        path=f"{cell_path}#/scene/usd",
                        message="The canonical scene reference must remain inside the project.",
                    ),
                ),
            )

        project_findings = self._validate_candidate_tree(
            root,
            contents,
            cell_model.scene.usd,
        )
        if project_findings:
            return BackendResult(project=None, validation=project_findings)

        scene, scene_findings = inspect_scene(contents.scene_usda, scene_path)
        findings = list(scene_findings)
        if scene is not None:
            findings.extend(
                validate_scene_cross_references(
                    cell_data,
                    scene,
                    cell_path=cell_path,
                    scene_path=scene_path,
                )
            )
        if findings:
            return BackendResult(project=None, validation=tuple(findings))

        self._resolve_recovery(root)
        self._transactional_replace(
            root,
            {
                cell_path: contents.cell_yaml.encode("utf-8"),
                scene_path: contents.scene_usda.encode("utf-8"),
            },
        )
        summary = _summary_from_model(root, cell_model)
        return BackendResult(
            project=summary,
            validation=(),
            contents=contents,
        )

    def recover(self, project_path: Path) -> None:
        """Explicitly resolve a retained recovery journal after an interrupted process."""

        self._resolve_recovery(project_path.resolve())

    def browse_components(
        self, project_path: Path, filters: ComponentFilters = ComponentFilters()
    ) -> BrowserResult:
        """Delegate registry filtering and compatibility details to the pure component service."""

        return self._components.browse(project_path, filters)

    def place_component(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        component: str,
        version: str,
        alias: str,
        variants: Mapping[str, str],
    ) -> ComponentEditResult:
        """Return an in-memory linked YAML/USD placement without writing project files."""

        return self._components.place(
            project_path,
            contents,
            component=component,
            version=version,
            alias=alias,
            variants=variants,
        )

    def remove_component(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        remove_connections: bool,
    ) -> ComponentEditResult:
        """Return an in-memory linked removal with explicit connection resolution."""

        return self._components.remove(
            project_path,
            contents,
            instance_id=instance_id,
            remove_connections=remove_connections,
        )

    def _registry_for(self, project_path: Path) -> SchemaRegistry:
        directory = resolve_project_schema_directory(project_path, self._canonical_schemas)
        return SchemaRegistry.from_directory(directory)

    def _read_candidate(self, root: Path) -> _OpenedCandidate | tuple[ValidationItem, ...]:
        cell_path = root / "cell.yaml"
        try:
            cell_text = cell_path.read_text(encoding="utf-8")
            raw = yaml.safe_load(cell_text)
        except (OSError, UnicodeError, yaml.YAMLError):
            return (
                ValidationItem(
                    code="studio.cell-read-failed",
                    severity="error",
                    path=f"{cell_path}#",
                    message="Could not read a valid UTF-8 cell.yaml document.",
                ),
            )
        if not isinstance(raw, Mapping):
            return (
                ValidationItem(
                    code="studio.cell-root-invalid",
                    severity="error",
                    path=f"{cell_path}#",
                    message="cell.yaml must contain an object at its document root.",
                ),
            )
        scene_reference = _scene_reference(raw)
        scene_path = _contained_scene_path(root, scene_reference) if scene_reference else None
        if scene_path is None:
            return (
                ValidationItem(
                    code="studio.scene-reference-invalid",
                    severity="error",
                    path=f"{cell_path}#/scene/usd",
                    message="cell.yaml must reference a scene inside the project.",
                ),
            )
        if scene_path.suffix.lower() != ".usda":
            return (
                ValidationItem(
                    code="studio.scene-openusd-required",
                    severity="error",
                    path=f"{scene_path}#",
                    message=(
                        "This headless host can round-trip text USDA stages; binary USD requires "
                        "the Isaac Sim 6 OpenUSD runtime."
                    ),
                ),
            )
        try:
            scene_text = scene_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return (
                ValidationItem(
                    code="studio.scene-read-failed",
                    severity="error",
                    path=f"{scene_path}#",
                    message="Could not read the canonical USDA scene.",
                ),
            )
        return _OpenedCandidate(
            contents=ProjectContents(cell_yaml=cell_text, scene_usda=scene_text),
            cell_data=raw,
            scene_path=scene_path,
        )

    def _transactional_replace(self, root: Path, candidates: Mapping[Path, bytes]) -> None:
        journal_path = root / RECOVERY_FILE
        originals = {path: path.read_bytes() for path in candidates}
        journal = {
            "version": 1,
            "files": {
                path.relative_to(root).as_posix(): {
                    "before": base64.b64encode(originals[path]).decode("ascii"),
                    "candidate_sha256": hashlib.sha256(content).hexdigest(),
                }
                for path, content in candidates.items()
            },
        }
        temporary: list[Path] = []
        try:
            _write_temporary(journal_path, _json_bytes(journal), temporary, os.replace)
            prepared: dict[Path, Path] = {}
            for target, content in candidates.items():
                prepared[target] = _prepare_temporary(target, content, temporary)
            for target, source in prepared.items():
                self._replace_file(source, target)
                temporary.remove(source)
            journal_path.unlink(missing_ok=True)
        except Exception as error:
            try:
                for target, content in originals.items():
                    _write_temporary(target, content, temporary, os.replace)
                journal_path.unlink(missing_ok=True)
            except Exception as rollback_error:
                raise ProjectSaveError(
                    f"Project save failed and requires explicit recovery from {journal_path}."
                ) from rollback_error
            raise ProjectSaveError(
                "Project save failed; the previous cell.yaml and USD scene were restored."
            ) from error
        finally:
            for path in temporary:
                path.unlink(missing_ok=True)

    def _validate_candidate_tree(
        self,
        root: Path,
        contents: ProjectContents,
        scene_reference: str,
    ) -> tuple[ValidationItem, ...]:
        with tempfile.TemporaryDirectory(prefix="cellforge-studio-validation-") as temporary:
            staged = Path(temporary) / "project"
            shutil.copytree(
                root,
                staged,
                ignore=shutil.ignore_patterns(RECOVERY_FILE, ".git", "__pycache__"),
            )
            (staged / "cell.yaml").write_text(
                contents.cell_yaml,
                encoding="utf-8",
                newline="\n",
            )
            staged_scene = _contained_scene_path(staged, scene_reference)
            if staged_scene is None:
                return (
                    ValidationItem(
                        code="studio.scene-reference-outside-project",
                        severity="error",
                        path=f"{root / 'cell.yaml'}#/scene/usd",
                        message="The canonical scene reference must remain inside the project.",
                    ),
                )
            staged_scene.write_text(contents.scene_usda, encoding="utf-8", newline="\n")
            report = validate_project(staged, self._registry_for(staged))
            staged_prefix = str(staged.resolve())
            root_prefix = str(root.resolve())
            return tuple(
                ValidationItem(
                    code=str(finding.code),
                    severity=finding.severity.value,
                    path=finding.path.replace(staged_prefix, root_prefix, 1),
                    message=finding.message,
                )
                for finding in report.findings
            )

    def _resolve_recovery(self, root: Path) -> None:
        journal_path = root / RECOVERY_FILE
        if not journal_path.exists():
            return
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            files = journal["files"]
            if not isinstance(files, Mapping):
                raise ValueError
            candidates_complete = len(files) == 2
            for relative, metadata in files.items():
                if not isinstance(relative, str) or not isinstance(metadata, Mapping):
                    raise ValueError
                target = (root / relative).resolve()
                if not target.is_relative_to(root):
                    raise ValueError
                try:
                    matches = hashlib.sha256(target.read_bytes()).hexdigest() == str(
                        metadata["candidate_sha256"]
                    )
                except OSError:
                    matches = False
                candidates_complete = candidates_complete and matches
            if candidates_complete:
                journal_path.unlink()
                return
            for relative, metadata in files.items():
                if not isinstance(relative, str) or not isinstance(metadata, Mapping):
                    raise ValueError
                target = (root / relative).resolve()
                if not target.is_relative_to(root):
                    raise ValueError
                before = base64.b64decode(str(metadata["before"]), validate=True)
                temporary: list[Path] = []
                _write_temporary(target, before, temporary, os.replace)
            journal_path.unlink()
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ProjectSaveError(
                f"Could not resolve the project recovery journal at {journal_path}."
            ) from error


def _parse_cell_candidate(
    text: str,
    cell_path: Path,
    registry: SchemaRegistry,
) -> _ParsedCell | tuple[ValidationItem, ...]:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError:
        return (
            ValidationItem(
                code="source.parse-failed",
                severity="error",
                path=f"{cell_path}#",
                message="Document syntax is invalid.",
            ),
        )
    if not isinstance(raw, Mapping):
        return (
            ValidationItem(
                code="source.root-not-object",
                severity="error",
                path=f"{cell_path}#",
                message="Document root must be an object.",
            ),
        )
    document = dict(raw)
    schema_findings = registry.validate(SchemaDocumentKind.CELL, document, cell_path)
    if schema_findings:
        return tuple(_validation_item(item) for item in schema_findings)
    try:
        model = CellProject.model_validate(document)
    except ValidationError as error:
        return tuple(
            ValidationItem(
                code=f"model.{str(item['type']).replace('_', '-')}",
                severity="error",
                path=f"{cell_path}#/{'/'.join(str(part) for part in item['loc'])}",
                message=str(item["msg"]),
            )
            for item in error.errors(
                include_context=False,
                include_input=False,
                include_url=False,
            )
        )
    return _ParsedCell(model=model, data=raw)


def _scene_reference(cell: Mapping[str, Any]) -> str | None:
    scene = cell.get("scene")
    if not isinstance(scene, Mapping):
        return None
    reference = scene.get("usd")
    return reference if isinstance(reference, str) else None


def _contained_scene_path(root: Path, reference: str | None) -> Path | None:
    if reference is None:
        return None
    raw = Path(reference)
    target = (root / raw).resolve()
    if raw.is_absolute() or not target.is_relative_to(root):
        return None
    return target


def _backend_project(summary: ProjectSummary) -> BackendProject:
    return BackendProject(
        path=summary.path,
        cell_id=str(summary.cell_id),
        name=summary.name,
        scene=summary.scene,
        component_count=summary.component_count,
        connection_count=summary.connection_count,
        task_count=summary.task_count,
        recipe_count=summary.recipe_count,
        scenario_count=summary.scenario_count,
        deployment_profile_count=summary.deployment_profile_count,
    )


def _summary_from_model(root: Path, cell: CellProject) -> BackendProject:
    return BackendProject(
        path=root,
        cell_id=str(cell.cell.id),
        name=cell.cell.name,
        scene=cell.scene.usd,
        component_count=len(cell.components),
        connection_count=len(cell.connections),
        task_count=len(cell.tasks),
        recipe_count=len(cell.recipes),
        scenario_count=len(cell.scenarios),
        deployment_profile_count=len(cell.deployment_profiles),
    )


def _validation_item(finding: ValidationFinding) -> ValidationItem:
    return ValidationItem(
        code=str(finding.code),
        severity=finding.severity.value,
        path=finding.path,
        message=finding.message,
    )


def _unique_findings(findings: list[ValidationItem]) -> tuple[ValidationItem, ...]:
    unique = {(item.code, item.severity, item.path, item.message): item for item in findings}
    return tuple(sorted(unique.values(), key=lambda item: (item.path, item.code, item.message)))


def _prepare_temporary(target: Path, content: bytes, tracked: list[Path]) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.cellforge-", dir=target.parent)
    temporary = Path(name)
    tracked.append(temporary)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return temporary


def _write_temporary(
    target: Path,
    content: bytes,
    tracked: list[Path],
    replace: Callable[[str | Path, str | Path], None],
) -> None:
    temporary = _prepare_temporary(target, content, tracked)
    replace(temporary, target)
    tracked.remove(temporary)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
