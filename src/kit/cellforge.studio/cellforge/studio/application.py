"""Pure, immutable application state for the Cell Studio extension shell."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class StudioStatus(StrEnum):
    """Stable top-level states rendered by the extension shell."""

    NO_PROJECT = "no_project"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    PROJECT_INVALID = "project_invalid"
    PROJECT_READY = "project_ready"
    OPERATION_FAILED = "operation_failed"


class LogLevel(StrEnum):
    """Small presentation-neutral log severity set."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ValidationItem:
    """One already-evaluated backend finding for display."""

    code: str
    severity: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class BackendProject:
    """Backend-owned project summary before presentation mapping."""

    path: Path
    cell_id: str
    name: str
    scene: str
    component_count: int
    connection_count: int
    task_count: int
    recipe_count: int
    scenario_count: int
    deployment_profile_count: int


@dataclass(frozen=True, slots=True)
class BackendResult:
    """Complete result of one backend project command."""

    project: BackendProject | None
    validation: tuple[ValidationItem, ...]
    contents: ProjectContents | None = None


@dataclass(frozen=True, slots=True)
class ProjectContents:
    """Exact canonical source buffers retained for lossless round trips."""

    cell_yaml: str
    scene_usda: str


class ProjectBackend(Protocol):
    """Project commands implemented outside UI callbacks."""

    def inspect(self, project_path: Path) -> BackendResult:
        """Validate and summarize a project without modifying it."""

    def create(self, project_path: Path) -> BackendResult:
        """Explicitly create, validate, and open a new project."""

    def save(self, project_path: Path, contents: ProjectContents) -> BackendResult:
        """Validate and transactionally save both canonical project artifacts."""


@dataclass(frozen=True, slots=True)
class ProjectView:
    """Project-panel values detached from domain and Kit types."""

    path: str
    cell_id: str
    name: str
    scene: str
    component_count: int
    connection_count: int
    task_count: int
    recipe_count: int
    scenario_count: int
    deployment_profile_count: int


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One deterministic in-memory shell event."""

    sequence: int
    level: LogLevel
    message: str


@dataclass(frozen=True, slots=True)
class StudioSnapshot:
    """All state needed to render the three shell panels."""

    status: StudioStatus
    headline: str
    detail: str
    project: ProjectView | None = None
    validation: tuple[ValidationItem, ...] = ()
    logs: tuple[LogEntry, ...] = ()
    dirty: bool = False


class StudioApplication:
    """Coordinate read-only backend queries and expose immutable UI state."""

    def __init__(
        self,
        backend: ProjectBackend | None,
        *,
        backend_unavailable_message: str = "CellForge project services are unavailable.",
    ) -> None:
        self._backend = backend
        if backend is None:
            self._snapshot = StudioSnapshot(
                status=StudioStatus.BACKEND_UNAVAILABLE,
                headline="Project backend unavailable",
                detail=backend_unavailable_message,
                logs=(
                    LogEntry(
                        sequence=1,
                        level=LogLevel.ERROR,
                        message="Project backend is unavailable; no project was opened.",
                    ),
                ),
            )
        else:
            self._snapshot = StudioSnapshot(
                status=StudioStatus.NO_PROJECT,
                headline="No project open",
                detail="Enter a CellForge project directory to inspect it.",
                logs=(
                    LogEntry(
                        sequence=1,
                        level=LogLevel.INFO,
                        message="Cell Studio started without opening or modifying a project.",
                    ),
                ),
            )
        self._saved_contents: ProjectContents | None = None
        self._working_contents: ProjectContents | None = None

    @property
    def snapshot(self) -> StudioSnapshot:
        """Return the current immutable view state."""

        return self._snapshot

    def open_project(self, project_path: str | Path) -> StudioSnapshot:
        """Run the backend's read-only inspect command and map its result for display."""

        if self._backend is None:
            return self._snapshot

        raw_path = str(project_path).strip()
        if not raw_path:
            self._saved_contents = None
            self._working_contents = None
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.NO_PROJECT,
                headline="No project open",
                detail="Enter a CellForge project directory to inspect it.",
                project=None,
                validation=(),
                dirty=False,
                logs=self._append_log(LogLevel.WARNING, "Project path was empty."),
            )
            return self._snapshot

        resolved_path = Path(raw_path).expanduser().resolve()
        try:
            result = self._backend.inspect(resolved_path)
        except Exception as error:  # UI boundary must remain responsive to backend failures.
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.OPERATION_FAILED,
                headline="Project inspection failed",
                detail="The backend could not inspect this project. See the log panel.",
                project=None,
                validation=(),
                logs=self._append_log(
                    LogLevel.ERROR,
                    f"Project inspection failed ({type(error).__name__}); no files were changed.",
                ),
            )
            return self._snapshot

        return self._apply_result(result, resolved_path, operation="Opened")

    def create_project(self, project_path: str | Path) -> StudioSnapshot:
        """Explicitly create a project through the backend command service."""

        if self._backend is None:
            return self._snapshot
        raw_path = str(project_path).strip()
        if not raw_path:
            return self.open_project("")
        resolved_path = Path(raw_path).expanduser().resolve()
        try:
            result = self._backend.create(resolved_path)
        except Exception as error:
            return self._operation_failure("Project creation", error)
        return self._apply_result(result, resolved_path, operation="Created")

    def edit_cell_yaml(self, text: str) -> StudioSnapshot:
        """Replace the in-memory operational graph without touching project files."""

        if self._working_contents is None:
            return self._no_open_project("Cannot edit cell.yaml because no valid project is open.")
        self._working_contents = replace(self._working_contents, cell_yaml=text)
        return self._update_dirty_state("Edited cell.yaml in memory; save explicitly to write it.")

    def edit_scene_usda(self, text: str) -> StudioSnapshot:
        """Replace the in-memory spatial scene without touching project files."""

        if self._working_contents is None:
            return self._no_open_project("Cannot edit the scene because no valid project is open.")
        self._working_contents = replace(self._working_contents, scene_usda=text)
        return self._update_dirty_state(
            "Edited the USD scene in memory; save explicitly to write it."
        )

    def save_project(self) -> StudioSnapshot:
        """Explicitly validate and save the current canonical source buffers."""

        if self._backend is None:
            return self._snapshot
        project = self._snapshot.project
        contents = self._working_contents
        if project is None or contents is None:
            return self._no_open_project("Cannot save because no valid project is open.")
        if not self._snapshot.dirty:
            self._snapshot = replace(
                self._snapshot,
                detail="Project is clean; save made no filesystem changes.",
                logs=self._append_log(LogLevel.INFO, "Save skipped because the project is clean."),
            )
            return self._snapshot
        try:
            result = self._backend.save(Path(project.path), contents)
        except Exception as error:
            return self._operation_failure("Project save", error, preserve_project=True)
        if result.project is None or result.contents is None:
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.PROJECT_INVALID,
                headline="Unsaved project is invalid",
                detail=f"Save was blocked by {len(result.validation)} validation finding(s).",
                validation=result.validation,
                dirty=True,
                logs=self._append_log(
                    LogLevel.WARNING,
                    "Save validation failed; canonical project files were not changed.",
                ),
            )
            return self._snapshot
        return self._apply_result(result, Path(project.path), operation="Saved")

    def _apply_result(
        self,
        result: BackendResult,
        resolved_path: Path,
        *,
        operation: str,
    ) -> StudioSnapshot:
        if result.project is None or result.contents is None:
            self._saved_contents = None
            self._working_contents = None
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.PROJECT_INVALID,
                headline="Project is not ready",
                detail=f"Validation returned {len(result.validation)} finding(s).",
                project=None,
                validation=result.validation,
                dirty=False,
                logs=self._append_log(
                    LogLevel.WARNING,
                    f"Project validation failed for {resolved_path}; no files were changed.",
                ),
            )
            return self._snapshot

        project = result.project
        self._saved_contents = result.contents
        self._working_contents = result.contents
        self._snapshot = replace(
            self._snapshot,
            status=StudioStatus.PROJECT_READY,
            headline=project.name,
            detail=f"{operation} project with synchronized cell.yaml and USD instance IDs.",
            project=ProjectView(
                path=str(project.path),
                cell_id=project.cell_id,
                name=project.name,
                scene=project.scene,
                component_count=project.component_count,
                connection_count=project.connection_count,
                task_count=project.task_count,
                recipe_count=project.recipe_count,
                scenario_count=project.scenario_count,
                deployment_profile_count=project.deployment_profile_count,
            ),
            validation=result.validation,
            dirty=False,
            logs=self._append_log(LogLevel.INFO, f"{operation} project {project.name}."),
        )
        return self._snapshot

    def _update_dirty_state(self, message: str) -> StudioSnapshot:
        dirty = self._working_contents != self._saved_contents
        self._snapshot = replace(
            self._snapshot,
            dirty=dirty,
            detail=(
                "Project has unsaved in-memory changes."
                if dirty
                else "Project matches the last opened or saved canonical files."
            ),
            logs=self._append_log(LogLevel.INFO, message),
        )
        return self._snapshot

    def _no_open_project(self, message: str) -> StudioSnapshot:
        self._snapshot = replace(
            self._snapshot,
            detail=message,
            logs=self._append_log(LogLevel.WARNING, message),
        )
        return self._snapshot

    def _operation_failure(
        self,
        operation: str,
        error: Exception,
        *,
        preserve_project: bool = False,
    ) -> StudioSnapshot:
        self._snapshot = replace(
            self._snapshot,
            status=StudioStatus.OPERATION_FAILED,
            headline=f"{operation} failed",
            detail=f"{operation} did not complete. See the log panel.",
            project=self._snapshot.project if preserve_project else None,
            validation=self._snapshot.validation if preserve_project else (),
            dirty=self._snapshot.dirty if preserve_project else False,
            logs=self._append_log(
                LogLevel.ERROR,
                f"{operation} failed ({type(error).__name__}); no partial save was accepted.",
            ),
        )
        return self._snapshot

    def _append_log(self, level: LogLevel, message: str) -> tuple[LogEntry, ...]:
        next_sequence = self._snapshot.logs[-1].sequence + 1 if self._snapshot.logs else 1
        entries = (*self._snapshot.logs, LogEntry(next_sequence, level, message))
        return entries[-200:]
