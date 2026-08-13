"""Pure, immutable application state for the Cell Studio extension shell."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
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
    artifacts: Mapping[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ComponentFilters:
    """Conjunctive registry browser filters; empty fields match every component."""

    kind: str | None = None
    capability: str | None = None
    support_level: str | None = None
    simulation_level: str | None = None


@dataclass(frozen=True, slots=True)
class ComponentVariant:
    """One declared USD/component variant set and its allowed selections."""

    name: str
    selections: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BrowserComponent:
    """Presentation-neutral component detail and compatibility record."""

    component: str
    version: str
    kind: str
    name: str
    manufacturer: str | None
    model: str | None
    description: str | None
    license: str | None
    package_path: str
    capabilities: tuple[str, ...]
    support_level: str
    simulation_level: str
    compatible_modes: tuple[str, ...]
    warnings: tuple[str, ...]
    variants: tuple[ComponentVariant, ...]


@dataclass(frozen=True, slots=True)
class BrowserResult:
    """Deterministic browser query result plus registry findings."""

    components: tuple[BrowserComponent, ...]
    validation: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ComponentEditResult:
    """Atomic paired-buffer transformation result."""

    contents: ProjectContents | None
    validation: tuple[ValidationItem, ...] = ()
    instance_id: str | None = None
    removed_connections: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConnectionPort:
    """One declared instance port displayed in the typed connection browser."""

    component_instance: str
    component_alias: str
    kind: str
    port: str
    direction: str
    port_type: str
    frame: str | None
    required: bool
    modeled_only: bool


@dataclass(frozen=True, slots=True)
class ConnectionEdge:
    """One persisted edge with explicit execution and safety semantics."""

    connection_id: str
    kind: str
    from_component: str
    from_port: str
    to_component: str
    to_port: str
    port_type: str
    modeled_only: bool
    executable: bool


@dataclass(frozen=True, slots=True)
class MechanicalSnapPreview:
    """Validated spatial edit proposed for a compatible mechanical connection."""

    connection_id: str
    source_prim: str
    current_target_prim: str
    snapped_target_prim: str
    source_frame: str
    target_frame: str
    transform: tuple[float, ...]
    adapter_required: bool


@dataclass(frozen=True, slots=True)
class ConnectionBrowserResult:
    """Typed port graph and validation findings returned by the backend."""

    ports: tuple[ConnectionPort, ...]
    edges: tuple[ConnectionEdge, ...]
    validation: tuple[ValidationItem, ...] = ()
    safety_disclaimer: str = ""


@dataclass(frozen=True, slots=True)
class ConnectionEditResult:
    """Connection preview or atomic source transformation result."""

    contents: ProjectContents | None
    validation: tuple[ValidationItem, ...] = ()
    connection_id: str | None = None
    edge: ConnectionEdge | None = None
    preview: MechanicalSnapPreview | None = None


@dataclass(frozen=True, slots=True)
class SpatialEditResult:
    """Result of an undoable spatial/configuration/calibration paired edit."""

    contents: ProjectContents | None
    validation: tuple[ValidationItem, ...] = ()
    calibration_path: str | None = None


class ProjectBackend(Protocol):
    """Project commands implemented outside UI callbacks."""

    def inspect(self, project_path: Path) -> BackendResult:
        """Validate and summarize a project without modifying it."""

    def create(self, project_path: Path) -> BackendResult:
        """Explicitly create, validate, and open a new project."""

    def save(self, project_path: Path, contents: ProjectContents) -> BackendResult:
        """Validate and transactionally save both canonical project artifacts."""

    def browse_components(
        self, project_path: Path, filters: ComponentFilters = ComponentFilters()
    ) -> BrowserResult:
        """Return filtered registry details without changing the project."""

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
        """Create linked operational and spatial records in memory."""

    def remove_component(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        remove_connections: bool,
    ) -> ComponentEditResult:
        """Remove linked records, requiring explicit connection resolution."""

    def browse_connections(
        self, project_path: Path, contents: ProjectContents
    ) -> ConnectionBrowserResult:
        """Return the typed port graph for the current in-memory sources."""

    def preview_mechanical_connection(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        connection_id: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
    ) -> ConnectionEditResult:
        """Validate a mechanical edge and return its spatial snap preview."""

    def connect_ports(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        connection_id: str,
        kind: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
    ) -> ConnectionEditResult:
        """Create a validated logical or paired mechanical connection edit."""

    def set_component_transform(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        matrix: tuple[float, ...],
    ) -> SpatialEditResult:
        """Edit one component transform in the paired in-memory sources."""

    def set_component_configuration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        configuration: Mapping[str, object],
    ) -> SpatialEditResult:
        """Edit one schema-validated instance configuration in memory."""

    def set_component_variants(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        variants: Mapping[str, str],
    ) -> SpatialEditResult:
        """Edit one component's declared variant selections in memory."""

    def create_calibration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        kind: str,
        valid_until: str,
        data: Mapping[str, object],
    ) -> SpatialEditResult:
        """Stage and bind one immutable calibration artifact in memory."""


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
    browser: tuple[BrowserComponent, ...] = ()
    connection_ports: tuple[ConnectionPort, ...] = ()
    connection_edges: tuple[ConnectionEdge, ...] = ()
    safety_disclaimer: str = ""
    mechanical_preview: MechanicalSnapPreview | None = None
    can_undo: bool = False
    can_redo: bool = False


@dataclass(frozen=True, slots=True)
class _EditState:
    contents: ProjectContents
    project: ProjectView
    connection_ports: tuple[ConnectionPort, ...]
    connection_edges: tuple[ConnectionEdge, ...]
    safety_disclaimer: str
    mechanical_preview: MechanicalSnapPreview | None


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
        self._undo_stack: list[_EditState] = []
        self._redo_stack: list[_EditState] = []

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
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.NO_PROJECT,
                headline="No project open",
                detail="Enter a CellForge project directory to inspect it.",
                project=None,
                validation=(),
                dirty=False,
                browser=(),
                connection_ports=(),
                connection_edges=(),
                safety_disclaimer="",
                mechanical_preview=None,
                can_undo=False,
                can_redo=False,
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

        snapshot = self._apply_result(result, resolved_path, operation="Opened")
        if snapshot.project is None:
            return snapshot
        self.refresh_components()
        return self.refresh_connections()

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
        snapshot = self._apply_result(result, resolved_path, operation="Created")
        if snapshot.project is None:
            return snapshot
        self.refresh_components()
        return self.refresh_connections()

    def refresh_components(self, filters: ComponentFilters = ComponentFilters()) -> StudioSnapshot:
        """Query the project registry through the pure backend browser service."""

        if self._backend is None:
            return self._snapshot
        project = self._snapshot.project
        if project is None:
            return self._no_open_project(
                "Cannot browse components because no valid project is open."
            )
        try:
            result = self._backend.browse_components(Path(project.path), filters)
        except Exception as error:
            return self._operation_failure(
                "Component browser refresh", error, preserve_project=True
            )
        self._snapshot = replace(
            self._snapshot,
            browser=result.components,
            validation=result.validation,
            detail=f"Component browser contains {len(result.components)} matching package(s).",
            logs=self._append_log(
                LogLevel.INFO,
                f"Refreshed component browser with {len(result.components)} match(es).",
            ),
        )
        return self._snapshot

    def place_component(
        self,
        component: str,
        version: str,
        alias: str,
        variants: Mapping[str, str] | None = None,
    ) -> StudioSnapshot:
        """Apply one linked YAML/USD placement to the in-memory project buffers."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot place a component without a valid open project.")
        try:
            result = self._backend.place_component(
                Path(project.path),
                contents,
                component=component,
                version=version,
                alias=alias,
                variants=variants or {},
            )
        except Exception as error:
            return self._operation_failure("Component placement", error, preserve_project=True)
        if result.contents is None:
            return self._edit_rejected("Component placement", result.validation)
        self._record_edit(contents, project)
        self._working_contents = result.contents
        connection_graph = self._connection_graph(Path(project.path), self._working_contents)
        self._snapshot = replace(
            self._snapshot,
            status=StudioStatus.PROJECT_READY,
            headline=project.name,
            detail=(
                f"Placed component instance {result.instance_id}; save to commit both artifacts."
            ),
            project=replace(project, component_count=project.component_count + 1),
            validation=(),
            dirty=self._working_contents != self._saved_contents,
            connection_ports=connection_graph.ports,
            connection_edges=connection_graph.edges,
            safety_disclaimer=connection_graph.safety_disclaimer,
            mechanical_preview=None,
            can_undo=True,
            can_redo=False,
            logs=self._append_log(
                LogLevel.INFO, f"Placed component instance {result.instance_id} in memory."
            ),
        )
        return self._snapshot

    def refresh_connections(self) -> StudioSnapshot:
        """Refresh the typed graph from current in-memory sources through the backend."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot browse connections without a valid open project.")
        try:
            result = self._backend.browse_connections(Path(project.path), contents)
        except Exception as error:
            return self._operation_failure(
                "Connection browser refresh", error, preserve_project=True
            )
        self._snapshot = replace(
            self._snapshot,
            connection_ports=result.ports,
            connection_edges=result.edges,
            safety_disclaimer=result.safety_disclaimer,
            validation=result.validation,
            mechanical_preview=None,
            logs=self._append_log(
                LogLevel.INFO,
                f"Refreshed connection graph with {len(result.edges)} edge(s).",
            ),
        )
        return self._snapshot

    def preview_mechanical_connection(
        self,
        connection_id: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
    ) -> StudioSnapshot:
        """Preview one validated mechanical snap without mutating project buffers."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot preview a connection without a valid project.")
        try:
            result = self._backend.preview_mechanical_connection(
                Path(project.path),
                contents,
                connection_id=connection_id,
                from_component=from_component,
                from_port=from_port,
                to_component=to_component,
                to_port=to_port,
            )
        except Exception as error:
            return self._operation_failure("Mechanical snap preview", error, preserve_project=True)
        if result.preview is None:
            return self._edit_rejected("Mechanical snap preview", result.validation)
        self._snapshot = replace(
            self._snapshot,
            validation=(),
            mechanical_preview=result.preview,
            detail=(
                f"Preview: snap {result.preview.current_target_prim} to "
                f"{result.preview.snapped_target_prim}."
            ),
            logs=self._append_log(
                LogLevel.INFO,
                f"Previewed mechanical connection {connection_id}; no sources changed.",
            ),
        )
        return self._snapshot

    def connect_ports(
        self,
        connection_id: str,
        kind: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
    ) -> StudioSnapshot:
        """Apply one validated connection edit to the in-memory canonical sources."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot create a connection without a valid project.")
        try:
            result = self._backend.connect_ports(
                Path(project.path),
                contents,
                connection_id=connection_id,
                kind=kind,
                from_component=from_component,
                from_port=from_port,
                to_component=to_component,
                to_port=to_port,
            )
        except Exception as error:
            return self._operation_failure("Connection creation", error, preserve_project=True)
        if result.contents is None or result.edge is None:
            return self._edit_rejected("Connection creation", result.validation)
        self._record_edit(contents, project)
        self._working_contents = result.contents
        self._snapshot = replace(
            self._snapshot,
            status=StudioStatus.PROJECT_READY,
            headline=project.name,
            detail=f"Created connection {connection_id}; save to commit canonical sources.",
            project=replace(project, connection_count=project.connection_count + 1),
            validation=(),
            dirty=self._working_contents != self._saved_contents,
            connection_edges=(*self._snapshot.connection_edges, result.edge),
            mechanical_preview=result.preview,
            can_undo=True,
            can_redo=False,
            logs=self._append_log(
                LogLevel.INFO,
                (
                    f"Created modeled-only safety dependency {connection_id}."
                    if result.edge.modeled_only
                    else f"Created {result.edge.kind} connection {connection_id}."
                ),
            ),
        )
        return self._snapshot

    def remove_component(
        self, instance_id: str, *, remove_connections: bool = False
    ) -> StudioSnapshot:
        """Remove one linked instance, with an explicit connection-cascade decision."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot remove a component without a valid open project.")
        try:
            result = self._backend.remove_component(
                Path(project.path),
                contents,
                instance_id=instance_id,
                remove_connections=remove_connections,
            )
        except Exception as error:
            return self._operation_failure("Component removal", error, preserve_project=True)
        if result.contents is None:
            return self._edit_rejected("Component removal", result.validation)
        self._record_edit(contents, project)
        self._working_contents = result.contents
        connection_graph = self._connection_graph(Path(project.path), self._working_contents)
        self._snapshot = replace(
            self._snapshot,
            status=StudioStatus.PROJECT_READY,
            headline=project.name,
            detail=f"Removed {instance_id}; save to commit both artifacts.",
            project=replace(
                project,
                component_count=project.component_count - 1,
                connection_count=project.connection_count - len(result.removed_connections),
            ),
            validation=(),
            dirty=self._working_contents != self._saved_contents,
            connection_ports=connection_graph.ports,
            connection_edges=connection_graph.edges,
            safety_disclaimer=connection_graph.safety_disclaimer,
            mechanical_preview=None,
            can_undo=True,
            can_redo=False,
            logs=self._append_log(
                LogLevel.INFO,
                f"Removed {instance_id} and {len(result.removed_connections)} connection(s).",
            ),
        )
        return self._snapshot

    def set_component_transform(
        self, instance_id: str, matrix: tuple[float, ...]
    ) -> StudioSnapshot:
        """Apply a validated spatial transform as a whole-pair undoable edit."""

        return self._spatial_edit(
            "Spatial transform",
            lambda backend, path, contents: backend.set_component_transform(
                path, contents, instance_id=instance_id, matrix=matrix
            ),
        )

    def set_component_configuration(
        self, instance_id: str, configuration: Mapping[str, object]
    ) -> StudioSnapshot:
        """Apply a schema-backed component configuration edit."""

        return self._spatial_edit(
            "Component configuration",
            lambda backend, path, contents: backend.set_component_configuration(
                path, contents, instance_id=instance_id, configuration=configuration
            ),
        )

    def set_component_variants(
        self, instance_id: str, variants: Mapping[str, str]
    ) -> StudioSnapshot:
        """Apply declared component variant selections without direct YAML editing."""

        return self._spatial_edit(
            "Component variants",
            lambda backend, path, contents: backend.set_component_variants(
                path, contents, instance_id=instance_id, variants=variants
            ),
        )

    def create_calibration(
        self, instance_id: str, kind: str, valid_until: str, data: Mapping[str, object]
    ) -> StudioSnapshot:
        """Create and bind an immutable calibration, staged until explicit save."""

        return self._spatial_edit(
            "Calibration creation",
            lambda backend, path, contents: backend.create_calibration(
                path,
                contents,
                instance_id=instance_id,
                kind=kind,
                valid_until=valid_until,
                data=data,
            ),
        )

    def undo(self) -> StudioSnapshot:
        """Undo one complete paired-buffer placement/removal edit."""

        project = self._snapshot.project
        contents = self._working_contents
        if project is None or contents is None or not self._undo_stack:
            return self._no_open_project("No component edit is available to undo.")
        previous = self._undo_stack.pop()
        self._redo_stack.append(self._edit_state(contents, project))
        self._working_contents = previous.contents
        self._snapshot = replace(
            self._snapshot,
            project=previous.project,
            validation=(),
            dirty=previous.contents != self._saved_contents,
            connection_ports=previous.connection_ports,
            connection_edges=previous.connection_edges,
            safety_disclaimer=previous.safety_disclaimer,
            mechanical_preview=previous.mechanical_preview,
            can_undo=bool(self._undo_stack),
            can_redo=True,
            detail="Undid one linked component edit in memory.",
            logs=self._append_log(LogLevel.INFO, "Undid one component edit."),
        )
        return self._snapshot

    def redo(self) -> StudioSnapshot:
        """Redo one complete paired-buffer placement/removal edit."""

        project = self._snapshot.project
        contents = self._working_contents
        if project is None or contents is None or not self._redo_stack:
            return self._no_open_project("No component edit is available to redo.")
        next_state = self._redo_stack.pop()
        self._undo_stack.append(self._edit_state(contents, project))
        self._working_contents = next_state.contents
        self._snapshot = replace(
            self._snapshot,
            project=next_state.project,
            validation=(),
            dirty=next_state.contents != self._saved_contents,
            connection_ports=next_state.connection_ports,
            connection_edges=next_state.connection_edges,
            safety_disclaimer=next_state.safety_disclaimer,
            mechanical_preview=next_state.mechanical_preview,
            can_undo=True,
            can_redo=bool(self._redo_stack),
            detail="Redid one linked component edit in memory.",
            logs=self._append_log(LogLevel.INFO, "Redid one component edit."),
        )
        return self._snapshot

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
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.PROJECT_INVALID,
                headline="Project is not ready",
                detail=f"Validation returned {len(result.validation)} finding(s).",
                project=None,
                validation=result.validation,
                dirty=False,
                browser=(),
                connection_ports=(),
                connection_edges=(),
                safety_disclaimer="",
                mechanical_preview=None,
                can_undo=False,
                can_redo=False,
                logs=self._append_log(
                    LogLevel.WARNING,
                    f"Project validation failed for {resolved_path}; no files were changed.",
                ),
            )
            return self._snapshot

        project = result.project
        self._saved_contents = result.contents
        self._working_contents = result.contents
        self._undo_stack.clear()
        self._redo_stack.clear()
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
            mechanical_preview=None,
            can_undo=False,
            can_redo=False,
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

    def _record_edit(self, contents: ProjectContents, project: ProjectView) -> None:
        self._undo_stack.append(self._edit_state(contents, project))
        self._undo_stack = self._undo_stack[-100:]
        self._redo_stack.clear()

    def _spatial_edit(
        self,
        operation: str,
        command: Callable[[ProjectBackend, Path, ProjectContents], SpatialEditResult],
    ) -> StudioSnapshot:
        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project(
                "Cannot edit spatial configuration without a valid project."
            )
        try:
            result = command(self._backend, Path(project.path), contents)
        except Exception as error:
            return self._operation_failure(operation, error, preserve_project=True)
        if result.contents is None:
            return self._edit_rejected(operation, result.validation)
        self._record_edit(contents, project)
        self._working_contents = result.contents
        self._snapshot = replace(
            self._snapshot,
            detail=f"{operation} updated paired sources in memory; save explicitly to persist.",
            validation=(),
            dirty=self._working_contents != self._saved_contents,
            can_undo=True,
            can_redo=False,
            logs=self._append_log(LogLevel.INFO, f"{operation} updated paired sources in memory."),
        )
        return self._snapshot

    def _edit_state(self, contents: ProjectContents, project: ProjectView) -> _EditState:
        return _EditState(
            contents=contents,
            project=project,
            connection_ports=self._snapshot.connection_ports,
            connection_edges=self._snapshot.connection_edges,
            safety_disclaimer=self._snapshot.safety_disclaimer,
            mechanical_preview=self._snapshot.mechanical_preview,
        )

    def _connection_graph(
        self, project_path: Path, contents: ProjectContents
    ) -> ConnectionBrowserResult:
        if self._backend is None:
            return ConnectionBrowserResult(
                ports=self._snapshot.connection_ports,
                edges=self._snapshot.connection_edges,
                safety_disclaimer=self._snapshot.safety_disclaimer,
            )
        try:
            return self._backend.browse_connections(project_path, contents)
        except Exception:
            return ConnectionBrowserResult(
                ports=self._snapshot.connection_ports,
                edges=self._snapshot.connection_edges,
                safety_disclaimer=self._snapshot.safety_disclaimer,
            )

    def _edit_rejected(
        self, operation: str, validation: tuple[ValidationItem, ...]
    ) -> StudioSnapshot:
        self._snapshot = replace(
            self._snapshot,
            detail=f"{operation} was rejected by {len(validation)} finding(s).",
            validation=validation,
            logs=self._append_log(LogLevel.WARNING, f"{operation} made no changes."),
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
