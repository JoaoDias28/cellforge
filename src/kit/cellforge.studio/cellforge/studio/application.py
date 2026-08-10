"""Pure, immutable application state for the Cell Studio extension shell."""

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
    """Complete result of one read-only backend inspection."""

    project: BackendProject | None
    validation: tuple[ValidationItem, ...]


class ProjectBackend(Protocol):
    """Read-only project query implemented outside UI callbacks."""

    def inspect(self, project_path: Path) -> BackendResult:
        """Validate and summarize a project without modifying it."""


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
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.NO_PROJECT,
                headline="No project open",
                detail="Enter a CellForge project directory to inspect it.",
                project=None,
                validation=(),
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

        if result.project is None:
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.PROJECT_INVALID,
                headline="Project is not ready",
                detail=f"Validation returned {len(result.validation)} finding(s).",
                project=None,
                validation=result.validation,
                logs=self._append_log(
                    LogLevel.WARNING,
                    f"Project validation failed for {resolved_path}.",
                ),
            )
            return self._snapshot

        project = result.project
        self._snapshot = replace(
            self._snapshot,
            status=StudioStatus.PROJECT_READY,
            headline=project.name,
            detail="Project inspected read-only; no project files were modified.",
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
            logs=self._append_log(LogLevel.INFO, f"Inspected project {project.name} read-only."),
        )
        return self._snapshot

    def _append_log(self, level: LogLevel, message: str) -> tuple[LogEntry, ...]:
        next_sequence = self._snapshot.logs[-1].sequence + 1 if self._snapshot.logs else 1
        entries = (*self._snapshot.logs, LogEntry(next_sequence, level, message))
        return entries[-200:]
