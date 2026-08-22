"""Pure, immutable application state for the Cell Studio extension shell."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from cellforge.studio.deployment_service import (
        AgentPaths,
        BundleAssemblyResult,
        BundleDiffResult,
        DeploymentBrowserResult,
        DeploymentInstallResult,
        DeploymentProfileDetail,
        DeploymentProfileSummary,
        DeploymentRollbackResult,
        DeploymentStatusResult,
        SignatureVerificationResult,
        TargetCompatibilityResult,
    )
    from cellforge.studio.guided_launcher import (
        CreateProjectRequest,
        GuidedProjectService,
        ProjectPreview,
    )
    from cellforge.studio.readiness import (
        EvaluateStudioReadiness,
        ReadinessBackendProbe,
        ReadinessCandidatePreview,
        StudioReadinessReport,
    )
    from cellforge.studio.recipe_service import (
        RecipeBrowserResult,
        RecipeDetail,
        RecipeDiffResult,
        RecipeEditResult,
        RecipeSummary,
    )
    from cellforge.studio.scenario_service import (
        EvidenceDetail,
        EvidenceSummary,
        ScenarioAssertionSpec,
        ScenarioBrowserResult,
        ScenarioDetail,
        ScenarioExecutionResult,
        ScenarioFaultSpec,
        ScenarioReplayResult,
        ScenarioSummary,
    )
    from cellforge.studio.schema_authoring import (
        AuthoringCandidate,
        SchemaFormModel,
    )
    from cellforge.studio.task_service import (
        TaskBrowserResult,
        TaskEditResult,
        TaskNodeSpec,
        TaskSummary,
        TaskTreeModel,
    )


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

    @property
    def endpoint_id(self) -> str:
        """Return the immutable endpoint identity used by the canvas."""

        return f"{self.kind}:{self.component_instance}:{self.port}"

    @property
    def component_instance_id(self) -> str:
        """Alias that makes the persistence identity explicit to UI consumers."""

        return self.component_instance

    @property
    def port_id(self) -> str:
        """Alias that makes the persistence identity explicit to UI consumers."""

        return self.port


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

    @property
    def edge_id(self) -> str:
        """Return the canonical deterministic connection ID for this visual edge."""

        return self.connection_id

    @property
    def from_endpoint_id(self) -> str:
        """Return the immutable source endpoint identity."""

        return f"{self.kind}:{self.from_component}:{self.from_port}"

    @property
    def to_endpoint_id(self) -> str:
        """Return the immutable target endpoint identity."""

        return f"{self.kind}:{self.to_component}:{self.to_port}"


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
    collision_findings: tuple[ValidationItem, ...] = ()
    payload_findings: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ConnectionEndpointRef:
    """Immutable component-instance/port identity used by preview DTOs."""

    component_instance_id: str
    port_id: str
    kind: str = "unknown"

    @property
    def endpoint_id(self) -> str:
        """Return a stable endpoint key independent of display aliases."""

        return f"{self.kind}:{self.component_instance_id}:{self.port_id}"


@dataclass(frozen=True, slots=True)
class ConnectionPreview:
    """A validated, write-free candidate for one typed connection."""

    edge_id: str
    kind: str
    from_endpoint: ConnectionEndpointRef
    to_endpoint: ConnectionEndpointRef
    candidate_cell_sha256: str
    candidate_scene_sha256: str
    proposed_transform: tuple[float, ...] | None = None
    source_prim: str | None = None
    current_target_prim: str | None = None
    proposed_target_prim: str | None = None
    source_frame: str | None = None
    target_frame: str | None = None
    findings: tuple[ValidationItem, ...] = ()
    collision_findings: tuple[ValidationItem, ...] = ()
    payload_findings: tuple[ValidationItem, ...] = ()
    modeled_only: bool = False
    executable: bool = False
    no_write: bool = True

    @property
    def endpoint_ids(self) -> tuple[str, str]:
        """Return source and target endpoint keys in canonical direction."""

        return (self.from_endpoint.endpoint_id, self.to_endpoint.endpoint_id)

    @property
    def candidate_hashes(self) -> tuple[tuple[str, str], ...]:
        """Return deterministic canonical candidate hashes without exposing mutable state."""

        return (
            ("cell.yaml", self.candidate_cell_sha256),
            ("scene.usda", self.candidate_scene_sha256),
        )

    @property
    def transform(self) -> tuple[float, ...] | None:
        """Compatibility alias for callers that consume spatial previews."""

        return self.proposed_transform

    @property
    def proposed_prim_path(self) -> str | None:
        """Compatibility alias for the generated target prim path."""

        return self.proposed_target_prim


@dataclass(frozen=True, slots=True)
class ConnectionLayoutEntry:
    """Derived screen position for one immutable endpoint."""

    endpoint_id: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class ConnectionLayoutMetadata:
    """Non-canonical canvas positions and edge routes."""

    entries: tuple[ConnectionLayoutEntry, ...] = ()
    routes: tuple[tuple[str, tuple[tuple[float, float], ...]], ...] = ()
    selected_endpoint_id: str | None = None

    def position_for(self, endpoint_id: str) -> tuple[float, float] | None:
        """Return a derived position without treating it as an operational identity."""

        for entry in self.entries:
            if entry.endpoint_id == endpoint_id:
                return (entry.x, entry.y)
        return None


@dataclass(frozen=True, slots=True)
class ConnectionLayerView:
    """One visually distinct connection layer assembled from service DTOs."""

    kind: str
    label: str
    ports: tuple[ConnectionPort, ...]
    edges: tuple[ConnectionEdge, ...]
    modeled_only: bool = False


@dataclass(frozen=True, slots=True)
class ConnectionCanvas:
    """Dockable-canvas model containing only derived presentation state."""

    layers: tuple[ConnectionLayerView, ...]
    ports: tuple[ConnectionPort, ...]
    edges: tuple[ConnectionEdge, ...]
    palette_ports: tuple[ConnectionPort, ...]
    query: str = ""
    highlighted_endpoint_ids: tuple[str, ...] = ()
    layout: ConnectionLayoutMetadata = ConnectionLayoutMetadata()
    safety_disclaimer: str = ""


@dataclass(frozen=True, slots=True)
class ConnectionBrowserResult:
    """Typed port graph and validation findings returned by the backend."""

    ports: tuple[ConnectionPort, ...]
    edges: tuple[ConnectionEdge, ...]
    validation: tuple[ValidationItem, ...] = ()
    safety_disclaimer: str = ""
    canvas: ConnectionCanvas | None = None
    warnings: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ConnectionEditResult:
    """Connection preview or atomic source transformation result."""

    contents: ProjectContents | None
    validation: tuple[ValidationItem, ...] = ()
    connection_id: str | None = None
    edge: ConnectionEdge | None = None
    preview: MechanicalSnapPreview | None = None
    connection_preview: ConnectionPreview | None = None
    warnings: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class SpatialEditResult:
    """Result of an undoable spatial/configuration/calibration paired edit."""

    contents: ProjectContents | None
    validation: tuple[ValidationItem, ...] = ()
    calibration_path: str | None = None


@dataclass(frozen=True, slots=True)
class SpatialComponent:
    """One selected component's inspectable spatial/configuration details."""

    instance_id: str
    alias: str
    usd_prim: str
    frames: tuple[str, ...]
    collision_asset: str
    transform: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SpatialBrowserResult:
    """Viewport-neutral selection, frame, and collision display data."""

    components: tuple[SpatialComponent, ...]
    validation: tuple[ValidationItem, ...] = ()


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

    def browse_spatial(self, project_path: Path, contents: ProjectContents) -> SpatialBrowserResult:
        """Return component transforms, frames, and collision display data."""

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

    def import_calibration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        calibration: Mapping[str, object],
    ) -> SpatialEditResult:
        """Stage and bind one existing immutable calibration artifact in memory."""

    def browse_tasks(self, project_path: Path, contents: ProjectContents) -> TaskBrowserResult:
        """Return tasks and node manifests for current project sources."""

    def set_task_tree(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        task_id: str,
        tree: TaskTreeModel | str,
    ) -> TaskEditResult:
        """Edit a task's BehaviorTree XML in staged project artifacts."""

    def browse_recipes(self, project_path: Path, contents: ProjectContents) -> RecipeBrowserResult:
        """Return recipes and validation findings for current project sources."""

    def inspect_recipe(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int | None = None,
    ) -> RecipeDetail | None:
        """Inspect specific recipe version fields and form schema metadata."""

    def edit_recipe(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int,
        data: Mapping[str, Any],
    ) -> RecipeEditResult:
        """Edit a draft recipe document in memory."""

    def create_recipe_version(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        base_version: int | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> RecipeEditResult:
        """Create a new immutable recipe version without mutating its predecessor."""

    def transition_recipe_lifecycle(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int,
        target_status: str,
        evidence: Sequence[str] | None = None,
    ) -> RecipeEditResult:
        """Transition a recipe version to a new lifecycle state."""

    def diff_recipes(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version_a: int,
        version_b: int,
    ) -> RecipeDiffResult | None:
        """Diff two recipe versions in the current project sources."""

    def browse_scenarios(
        self, project_path: Path, contents: ProjectContents
    ) -> ScenarioBrowserResult:
        """Enumerate and summarize all scenarios declared in the project."""

    def inspect_scenario(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        scenario_id: str,
    ) -> ScenarioDetail | None:
        """Inspect full scenario definition and parameters."""

    def execute_scenario(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        scenario_id: str,
        seed_override: int | None = None,
        injected_faults: Sequence[ScenarioFaultSpec] | None = None,
        available_backend_fidelity: str = "L0",
        has_cuda_gpu: bool = False,
        actual_physx_executed: bool = False,
    ) -> ScenarioExecutionResult:
        """Execute a scenario and produce evidence."""

    def browse_evidence(self, project_path: Path) -> tuple[EvidenceSummary, ...]:
        """Scan and summarize evidence files in the project."""

    def inspect_evidence(self, project_path: Path, *, evidence_path: str) -> EvidenceDetail | None:
        """Inspect full simulation evidence document."""

    def replay_evidence(
        self,
        project_path: Path,
        *,
        evidence_path: str,
        expected_assertions: ScenarioAssertionSpec | None = None,
    ) -> ScenarioReplayResult | None:
        """Replay and verify recorded evidence for deterministic consistency."""

    def browse_deployment_profiles(
        self, project_path: Path, contents: ProjectContents
    ) -> DeploymentBrowserResult:
        """Enumerate all deployment profiles declared in the project."""

    def inspect_deployment_profile(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        profile_id: str,
    ) -> DeploymentProfileDetail | None:
        """Inspect full deployment profile configuration."""

    def assemble_bundle(
        self,
        project_path: Path,
        schemas_path: Path,
        *,
        target_profile: str,
        mode: str,
        source_revision: str,
        output_dir: Path,
        signing_key_path: Path,
    ) -> BundleAssemblyResult:
        """Assemble an immutable signed release bundle."""

    def diff_bundles(
        self,
        base_bundle_path: Path,
        candidate_bundle_path: Path,
    ) -> BundleDiffResult:
        """Compute deterministic differences between two bundle directories."""

    def verify_bundle_signature(
        self,
        bundle_root: Path,
        trusted_keys_root: Path | None = None,
    ) -> SignatureVerificationResult:
        """Verify the Ed25519 signature of a release bundle."""

    def preflight_target_compatibility(
        self,
        bundle_root: Path,
        target_facts_path: Path,
    ) -> TargetCompatibilityResult:
        """Check bundle compatibility against target facts."""

    def get_deployment_status(self, agent_paths: AgentPaths) -> DeploymentStatusResult:
        """Query deployment agent status."""

    def install_bundle(
        self,
        bundle_root: Path,
        agent_paths: AgentPaths,
        *,
        systemd_runner: Any | None = None,
        health_checker: Any | None = None,
    ) -> DeploymentInstallResult:
        """Install a release bundle to target."""

    def rollback_deployment(
        self,
        agent_paths: AgentPaths,
        *,
        systemd_runner: Any | None = None,
        health_checker: Any | None = None,
    ) -> DeploymentRollbackResult:
        """Rollback to previous release."""


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
    guided_preview: ProjectPreview | None = None
    readiness_report: StudioReadinessReport | None = None
    readiness_preview: ReadinessCandidatePreview | None = None
    authoring_form: SchemaFormModel | None = None
    authoring_candidate: AuthoringCandidate | None = None
    browser: tuple[BrowserComponent, ...] = ()
    spatial_components: tuple[SpatialComponent, ...] = ()
    connection_ports: tuple[ConnectionPort, ...] = ()
    connection_edges: tuple[ConnectionEdge, ...] = ()
    connection_canvas: ConnectionCanvas | None = None
    connection_layout: ConnectionLayoutMetadata = ConnectionLayoutMetadata()
    connection_query: str = ""
    safety_disclaimer: str = ""
    mechanical_preview: MechanicalSnapPreview | None = None
    connection_preview: ConnectionPreview | None = None
    tasks: tuple[TaskSummary, ...] = ()
    available_node_specs: tuple[TaskNodeSpec, ...] = ()
    recipes: tuple[RecipeSummary, ...] = ()
    scenarios: tuple[ScenarioSummary, ...] = ()
    evidence_records: tuple[EvidenceSummary, ...] = ()
    deployment_profiles: tuple[DeploymentProfileSummary, ...] = ()
    selected_scenario: ScenarioDetail | None = None
    selected_evidence: EvidenceDetail | None = None
    selected_deployment_profile: DeploymentProfileDetail | None = None
    last_execution_result: ScenarioExecutionResult | None = None
    last_replay_result: ScenarioReplayResult | None = None
    last_bundle_assembly: BundleAssemblyResult | None = None
    last_bundle_diff: BundleDiffResult | None = None
    last_signature_verification: SignatureVerificationResult | None = None
    last_compatibility_result: TargetCompatibilityResult | None = None
    last_deployment_status: DeploymentStatusResult | None = None
    can_undo: bool = False
    can_redo: bool = False


@dataclass(frozen=True, slots=True)
class _EditState:
    contents: ProjectContents
    project: ProjectView
    spatial_components: tuple[SpatialComponent, ...]
    connection_ports: tuple[ConnectionPort, ...]
    connection_edges: tuple[ConnectionEdge, ...]
    connection_canvas: ConnectionCanvas | None
    connection_layout: ConnectionLayoutMetadata
    connection_query: str
    safety_disclaimer: str
    mechanical_preview: MechanicalSnapPreview | None
    connection_preview: ConnectionPreview | None
    tasks: tuple[TaskSummary, ...] = ()
    available_node_specs: tuple[TaskNodeSpec, ...] = ()
    recipes: tuple[RecipeSummary, ...] = ()
    scenarios: tuple[ScenarioSummary, ...] = ()
    evidence_records: tuple[EvidenceSummary, ...] = ()
    deployment_profiles: tuple[DeploymentProfileSummary, ...] = ()


class StudioApplication:
    """Coordinate read-only backend queries and expose immutable UI state."""

    def __init__(
        self,
        backend: ProjectBackend | None,
        *,
        backend_unavailable_message: str = "CellForge project services are unavailable.",
        guided_service: GuidedProjectService | None = None,
        readiness_service: EvaluateStudioReadiness | None = None,
    ) -> None:
        self._backend = backend
        self._guided_service = guided_service
        self._readiness_service = readiness_service
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
                readiness_report=None,
                readiness_preview=None,
                authoring_form=None,
                authoring_candidate=None,
                browser=(),
                spatial_components=(),
                connection_ports=(),
                connection_edges=(),
                safety_disclaimer="",
                mechanical_preview=None,
                tasks=(),
                available_node_specs=(),
                recipes=(),
                scenarios=(),
                evidence_records=(),
                deployment_profiles=(),
                selected_scenario=None,
                selected_evidence=None,
                selected_deployment_profile=None,
                last_execution_result=None,
                last_replay_result=None,
                last_bundle_assembly=None,
                last_bundle_diff=None,
                last_signature_verification=None,
                last_compatibility_result=None,
                last_deployment_status=None,
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
        self.refresh_spatial()
        return self.refresh_connections()

    def evaluate_readiness(
        self,
        *,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
    ) -> StudioSnapshot:
        """Evaluate the selected project through the pure readiness application service."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._readiness_service is None:
            return self._operation_failure(
                "Studio readiness evaluation",
                RuntimeError("Studio readiness service is unavailable."),
                preserve_project=True,
            )
        if project is None or contents is None:
            return self._no_open_project("Cannot evaluate readiness without a valid project open.")
        try:
            report = self._readiness_service.EvaluateStudioReadiness(
                Path(project.path),
                requested_fidelity=requested_fidelity,
                backend_probe=backend_probe,
                candidate_contents=contents,
            )
        except Exception as error:
            return self._operation_failure(
                "Studio readiness evaluation", error, preserve_project=True
            )
        self._snapshot = replace(
            self._snapshot,
            readiness_report=report,
            detail=(
                f"Readiness {report.summary.overall_status}: {report.summary.pass_count} pass, "
                f"{report.summary.blocked_count} blocked, "
                f"{report.summary.unavailable_count} unavailable."
            ),
            logs=self._append_log(
                LogLevel.INFO,
                f"Evaluated Studio readiness for {project.cell_id} at {report.observed_fidelity}.",
            ),
        )
        return self._snapshot

    def preview_readiness_remediation(
        self,
        remediation_id: str,
        *,
        candidate_contents: ProjectContents | None = None,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
    ) -> StudioSnapshot:
        """Stage a readiness remediation candidate without writing canonical sources."""

        project = self._snapshot.project
        contents = candidate_contents or self._working_contents
        if self._readiness_service is None:
            return self._operation_failure(
                "Studio remediation preview",
                RuntimeError("Studio readiness service is unavailable."),
                preserve_project=True,
            )
        if project is None:
            return self._no_open_project(
                "Cannot preview a remediation without a valid project open."
            )
        try:
            preview = self._readiness_service.PreviewStudioReadinessRemediation(
                Path(project.path),
                remediation_id,
                candidate_contents=contents,
                requested_fidelity=requested_fidelity,
                backend_probe=backend_probe,
            )
        except Exception as error:
            return self._operation_failure(
                "Studio remediation preview", error, preserve_project=True
            )
        self._snapshot = replace(
            self._snapshot,
            readiness_report=preview.report,
            readiness_preview=preview,
            detail=(
                "Readiness remediation preview staged in memory; "
                + ("explicit Save is available." if preview.can_save else "Save is blocked.")
            ),
            logs=self._append_log(
                LogLevel.INFO if preview.can_save else LogLevel.WARNING,
                f"Previewed remediation {remediation_id}; no canonical files were written.",
            ),
        )
        return self._snapshot

    def save_readiness_preview(
        self,
        *,
        confirmation_token: str | None = None,
        confirmed: bool = False,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
    ) -> StudioSnapshot:
        """Explicitly Save a reviewed readiness candidate through the existing transaction."""

        preview = self._snapshot.readiness_preview
        if self._readiness_service is None or preview is None:
            return self._no_open_project("No readiness remediation preview is available to Save.")
        try:
            result = self._readiness_service.SaveStudioReadiness(
                preview,
                confirmation_token,
                confirmed=confirmed,
                requested_fidelity=requested_fidelity,
                backend_probe=backend_probe,
            )
        except Exception as error:
            return self._operation_failure("Studio remediation Save", error, preserve_project=True)
        if not result.success:
            self._snapshot = replace(
                self._snapshot,
                readiness_report=result.report,
                validation=result.validation,
                detail=result.message,
                logs=self._append_log(LogLevel.WARNING, result.message),
            )
            return self._snapshot
        refreshed = self.open_project(preview.project_path)
        self._snapshot = replace(
            refreshed,
            readiness_report=result.report,
            readiness_preview=None,
            detail=result.message,
            logs=self._append_log(LogLevel.INFO, result.message),
        )
        return self._snapshot

    def build_schema_form(
        self,
        schema: Mapping[str, Any] | str | Path,
        *,
        source_path: str | Path | None = None,
        schema_kind: str | None = None,
        allocator_seed: str | None = None,
        required_choices: Mapping[str, Sequence[str]] | None = None,
        artifact_path: str | None = None,
    ) -> StudioSnapshot:
        """Build a schema-driven authoring form from the open project's buffers."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot build an authoring form without a valid project.")
        try:
            form = getattr(self._backend, "build_schema_form")(
                Path(project.path),
                contents,
                schema=schema,
                source_path=source_path,
                schema_kind=schema_kind,
                allocator_seed=allocator_seed,
                required_choices=required_choices,
                artifact_path=artifact_path,
            )
        except Exception as error:
            return self._operation_failure("Schema form build", error, preserve_project=True)
        validation = _authoring_validation(form.findings)
        self._snapshot = replace(
            self._snapshot,
            authoring_form=form,
            authoring_candidate=None,
            validation=validation,
            status=(
                StudioStatus.PROJECT_INVALID
                if any(item.severity == "error" for item in validation)
                else StudioStatus.PROJECT_READY
            ),
            detail=(
                f"Built {form.title} authoring form; "
                + (
                    f"{len(form.choices)} choice(s) require resolution."
                    if form.choices
                    else "ready for review."
                )
            ),
            logs=self._append_log(
                LogLevel.INFO,
                f"Built schema-driven form for {form.source_path}; no files were written.",
            ),
        )
        return self._snapshot

    def update_schema_form(
        self,
        values: Mapping[str, Any] | None = None,
        *,
        changes: Mapping[str, Any] | None = None,
    ) -> StudioSnapshot:
        """Apply form values in memory and clear any stale source candidate."""

        if self._backend is None or self._snapshot.authoring_form is None:
            return self._no_open_project("No schema authoring form is available to update.")
        try:
            form = getattr(self._backend, "update_schema_form")(
                self._snapshot.authoring_form,
                values,
                changes=changes,
            )
        except Exception as error:
            return self._operation_failure("Schema form update", error, preserve_project=True)
        validation = _authoring_validation(form.findings)
        self._snapshot = replace(
            self._snapshot,
            authoring_form=form,
            authoring_candidate=None,
            validation=validation,
            detail="Updated schema-driven authoring form in memory; preview before Save.",
            logs=self._append_log(LogLevel.INFO, "Updated authoring form; no files were written."),
        )
        return self._snapshot

    def preview_source_edit(
        self,
        source: str | bytes | Path | None = None,
        *,
        source_path: str | Path | None = None,
        artifact_path: str | None = None,
    ) -> StudioSnapshot:
        """Preview an advanced source edit and retain its immutable candidate."""

        if self._backend is None:
            return self._snapshot
        project = self._snapshot.project
        contents = self._working_contents
        form = self._snapshot.authoring_form
        if project is None or contents is None or form is None:
            return self._no_open_project("No schema authoring form is available to preview.")
        try:
            candidate = getattr(self._backend, "preview_source_edit")(
                form,
                source,
                source_path=source_path,
                artifact_path=artifact_path,
                project_path=Path(project.path),
                project_contents=contents,
            )
        except Exception as error:
            return self._operation_failure("Source edit preview", error, preserve_project=True)
        validation = _authoring_validation(candidate.findings)
        self._snapshot = replace(
            self._snapshot,
            authoring_candidate=candidate,
            validation=validation,
            status=(
                StudioStatus.PROJECT_INVALID
                if any(item.severity == "error" for item in validation)
                else StudioStatus.PROJECT_READY
            ),
            detail=(
                "Source edit preview ready; explicit Save is available."
                if candidate.can_save
                else "Source edit preview is blocked by unresolved findings."
            ),
            logs=self._append_log(
                LogLevel.INFO if candidate.can_save else LogLevel.WARNING,
                "Previewed schema source edit; no canonical files were written.",
            ),
        )
        return self._snapshot

    def merge_source_edit(
        self,
        source_or_candidate: str | bytes | Path | AuthoringCandidate,
    ) -> StudioSnapshot:
        """Three-way merge a source edit and retain the resulting candidate."""

        if self._backend is None:
            return self._snapshot
        project = self._snapshot.project
        contents = self._working_contents
        form = self._snapshot.authoring_form
        if project is None or contents is None or form is None:
            return self._no_open_project("No schema authoring form is available to merge.")
        try:
            candidate = getattr(self._backend, "merge_source_edit")(
                form,
                source_or_candidate,
                project_path=Path(project.path),
                project_contents=contents,
            )
        except Exception as error:
            return self._operation_failure("Source edit merge", error, preserve_project=True)
        validation = _authoring_validation(candidate.findings)
        self._snapshot = replace(
            self._snapshot,
            authoring_candidate=candidate,
            validation=validation,
            detail=(
                "Merged source edit preview ready; explicit Save is available."
                if candidate.can_save
                else "Merged source edit is blocked by conflicts or validation findings."
            ),
            logs=self._append_log(
                LogLevel.INFO, "Merged schema source edit; no files were written."
            ),
        )
        return self._snapshot

    def save_authoring_candidate(
        self,
        *,
        confirmation_token: str | None = None,
        confirmed: bool = False,
    ) -> StudioSnapshot:
        """Save the reviewed authoring candidate through the existing project transaction."""

        if self._backend is None:
            return self._snapshot
        project = self._snapshot.project
        contents = self._working_contents
        candidate = self._snapshot.authoring_candidate
        if project is None or contents is None or candidate is None:
            return self._no_open_project("No schema authoring preview is available to Save.")
        try:
            result = getattr(self._backend, "save_authoring_candidate")(
                candidate,
                confirmation_token,
                confirmed=confirmed,
                project_path=Path(project.path),
                project_contents=contents,
            )
        except Exception as error:
            return self._operation_failure("Authoring Save", error, preserve_project=True)
        if not result.success:
            validation = _authoring_validation(result.findings)
            self._snapshot = replace(
                self._snapshot,
                validation=validation,
                detail=result.message,
                logs=self._append_log(LogLevel.WARNING, result.message),
            )
            return self._snapshot
        refreshed = self.open_project(project.path)
        self._snapshot = replace(
            refreshed,
            authoring_form=None,
            authoring_candidate=None,
            detail=result.message,
            logs=self._append_log(LogLevel.INFO, result.message),
        )
        return self._snapshot

    # Exact command spellings for headless callers and future non-Kit clients.
    def EvaluateStudioReadiness(
        self,
        project_path: str | Path | None = None,
        *,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
    ) -> StudioSnapshot:
        if project_path is not None and self._snapshot.project is None:
            self.open_project(project_path)
        return self.evaluate_readiness(
            requested_fidelity=requested_fidelity, backend_probe=backend_probe
        )

    def PreviewStudioReadinessRemediation(
        self,
        remediation_id: str,
        *,
        candidate_contents: ProjectContents | None = None,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
    ) -> StudioSnapshot:
        return self.preview_readiness_remediation(
            remediation_id,
            candidate_contents=candidate_contents,
            requested_fidelity=requested_fidelity,
            backend_probe=backend_probe,
        )

    def SaveStudioReadiness(
        self,
        confirmation_token: str | None = None,
        *,
        confirmed: bool = False,
        requested_fidelity: str = "L0",
        backend_probe: ReadinessBackendProbe | None = None,
    ) -> StudioSnapshot:
        return self.save_readiness_preview(
            confirmation_token=confirmation_token,
            confirmed=confirmed,
            requested_fidelity=requested_fidelity,
            backend_probe=backend_probe,
        )

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
        self.refresh_spatial()
        return self.refresh_connections()

    def create_guided_project(self, request: CreateProjectRequest) -> StudioSnapshot:
        """Stage a deterministic guided project preview without writing project files."""

        if self._guided_service is None:
            return self._operation_failure(
                "Guided project preview",
                RuntimeError("Guided Studio service is unavailable."),
                preserve_project=True,
            )
        try:
            preview = self._guided_service.CreateProject(request)
        except Exception as error:
            return self._operation_failure("Guided project preview", error, preserve_project=True)
        self._snapshot = replace(
            self._snapshot,
            guided_preview=preview,
            status=(
                StudioStatus.PROJECT_INVALID if not preview.can_save else StudioStatus.NO_PROJECT
            ),
            headline="Guided project preview",
            detail=(
                f"Previewed {len(preview.generated_paths)} generated file(s); "
                + (
                    "Save is available after confirmation."
                    if preview.can_save
                    else "Save is blocked."
                )
            ),
            validation=tuple(_guided_validation_item(item) for item in preview.findings),
            dirty=self._snapshot.dirty,
            logs=self._append_log(
                LogLevel.INFO if preview.can_save else LogLevel.WARNING,
                f"Guided preview {preview.draft_id} created without filesystem writes.",
            ),
        )
        return self._snapshot

    def preview_guided_project(self, draft: str | ProjectPreview) -> StudioSnapshot:
        """Refresh a guided draft preview without mutating canonical source."""

        if self._guided_service is None:
            return self._operation_failure(
                "Guided project preview",
                RuntimeError("Guided Studio service is unavailable."),
                preserve_project=True,
            )
        try:
            preview = self._guided_service.PreviewProject(draft)
        except Exception as error:
            return self._operation_failure("Guided project preview", error, preserve_project=True)
        self._snapshot = replace(
            self._snapshot,
            guided_preview=preview,
            status=(
                StudioStatus.PROJECT_INVALID if not preview.can_save else StudioStatus.NO_PROJECT
            ),
            headline="Guided project preview",
            detail=(
                f"Reviewed {preview.draft_id}; explicit Save is "
                f"{'available' if preview.can_save else 'blocked'}."
            ),
            validation=tuple(_guided_validation_item(item) for item in preview.findings),
            dirty=self._snapshot.dirty,
        )
        return self._snapshot

    def open_guided_project(self, project_path: str | Path) -> StudioSnapshot:
        """Open through the guided read-only command, then reuse the existing Studio state map."""

        if self._guided_service is None:
            return self.open_project(project_path)
        result = self._guided_service.OpenProject(project_path)
        if result.project is None or result.contents is None:
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.PROJECT_INVALID,
                headline="Project is not ready",
                detail="Guided Open found validation findings; no files were changed.",
                project=None,
                validation=tuple(_guided_validation_item(item) for item in result.findings),
                dirty=False,
                logs=self._append_log(
                    LogLevel.WARNING,
                    f"Guided Open rejected {Path(project_path).resolve()} without writes.",
                ),
            )
            return self._snapshot
        snapshot = self._apply_result(
            BackendResult(
                project=result.project,
                contents=result.contents,
                validation=tuple(_guided_validation_item(item) for item in result.findings),
            ),
            Path(project_path).expanduser().resolve(),
            operation="Guided opened",
        )
        if snapshot.project is None:
            return snapshot
        self._snapshot = replace(snapshot, guided_preview=None)
        self.refresh_components()
        self.refresh_spatial()
        return self.refresh_connections()

    def confirm_guided_project_save(
        self,
        draft: str | ProjectPreview,
        confirmation_token: str | None = None,
        *,
        confirmed: bool = False,
    ) -> StudioSnapshot:
        """Persist a reviewed guided candidate only after explicit confirmation."""

        if self._guided_service is None:
            return self._operation_failure(
                "Guided project save",
                RuntimeError("Guided Studio service is unavailable."),
                preserve_project=True,
            )
        try:
            result = self._guided_service.ConfirmProjectSave(
                draft,
                confirmation_token,
                confirmed=confirmed,
            )
        except Exception as error:
            return self._operation_failure("Guided project save", error, preserve_project=True)
        if not result.success or result.project is None:
            self._snapshot = replace(
                self._snapshot,
                status=StudioStatus.PROJECT_INVALID,
                headline="Guided save blocked",
                detail="The reviewed candidate was not persisted; canonical files were unchanged.",
                guided_preview=result.preview,
                validation=tuple(_guided_validation_item(item) for item in result.findings),
                dirty=False,
                logs=self._append_log(
                    LogLevel.WARNING, "Guided Save was blocked or failed safely."
                ),
            )
            return self._snapshot
        snapshot = self.open_guided_project(result.project.path)
        self._snapshot = replace(
            snapshot,
            guided_preview=None,
            detail="Guided project saved and reopened with canonical validation.",
            logs=self._append_log(
                LogLevel.INFO, "Guided Save completed after explicit confirmation."
            ),
        )
        return self._snapshot

    def cancel_guided_project_draft(self, draft: str | ProjectPreview) -> StudioSnapshot:
        """Cancel a guided draft without changing the current project or filesystem."""

        if self._guided_service is None:
            return self._operation_failure(
                "Guided draft cancellation",
                RuntimeError("Guided Studio service is unavailable."),
                preserve_project=True,
            )
        result = self._guided_service.CancelProjectDraft(draft)
        self._snapshot = replace(
            self._snapshot,
            guided_preview=None if result.cancelled else self._snapshot.guided_preview,
            detail=(
                "Guided project draft cancelled without filesystem writes."
                if result.cancelled
                else "Guided draft cancellation found no active draft."
            ),
            validation=tuple(_guided_validation_item(item) for item in result.findings),
            logs=self._append_log(
                LogLevel.INFO if result.cancelled else LogLevel.WARNING,
                f"Guided draft {result.draft_id} cancellation: {result.cancelled}.",
            ),
        )
        return self._snapshot

    # Exact public command spellings from Task 039.  Kit callbacks use the snake-case methods
    # above, while headless callers can discover the command names directly on the application.
    def CreateProject(self, request: CreateProjectRequest) -> StudioSnapshot:
        """Execute the guided CreateProject command."""

        return self.create_guided_project(request)

    def OpenProject(self, project_path: str | Path) -> StudioSnapshot:
        """Execute the guided OpenProject command."""

        return self.open_guided_project(project_path)

    def PreviewProject(self, draft: str | ProjectPreview) -> StudioSnapshot:
        """Execute the guided PreviewProject command."""

        return self.preview_guided_project(draft)

    def ConfirmProjectSave(
        self,
        draft: str | ProjectPreview,
        confirmation_token: str | None = None,
        *,
        confirmed: bool = False,
    ) -> StudioSnapshot:
        """Execute the guided ConfirmProjectSave command."""

        return self.confirm_guided_project_save(draft, confirmation_token, confirmed=confirmed)

    def CancelProjectDraft(self, draft: str | ProjectPreview) -> StudioSnapshot:
        """Execute the guided CancelProjectDraft command."""

        return self.cancel_guided_project_draft(draft)

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

    def refresh_spatial(self) -> StudioSnapshot:
        """Refresh viewport-neutral transforms, frames, and collision display data."""

        if self._backend is None:
            return self._snapshot
        project = self._snapshot.project
        contents = self._working_contents
        if project is None or contents is None:
            return self._no_open_project(
                "Cannot inspect spatial configuration without a valid project open."
            )
        try:
            result = self._backend.browse_spatial(Path(project.path), contents)
        except Exception as error:
            return self._operation_failure(
                "Spatial configuration refresh", error, preserve_project=True
            )
        self._snapshot = replace(
            self._snapshot,
            spatial_components=result.components,
            validation=result.validation,
            detail=f"Spatial browser contains {len(result.components)} component(s).",
            logs=self._append_log(
                LogLevel.INFO,
                f"Refreshed spatial browser with {len(result.components)} component(s).",
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
        spatial = self._spatial_graph(Path(project.path), self._working_contents)
        connection_graph = self._connection_graph(Path(project.path), self._working_contents)
        self._snapshot = replace(
            self._snapshot,
            status=StudioStatus.PROJECT_READY,
            headline=project.name,
            detail=(
                f"Placed component instance {result.instance_id}; save to commit both artifacts."
            ),
            project=replace(project, component_count=project.component_count + 1),
            dirty=self._working_contents != self._saved_contents,
            spatial_components=spatial.components,
            connection_ports=connection_graph.ports,
            connection_edges=connection_graph.edges,
            connection_canvas=connection_graph.canvas,
            connection_layout=(
                connection_graph.canvas.layout
                if connection_graph.canvas is not None
                else self._snapshot.connection_layout
            ),
            safety_disclaimer=connection_graph.safety_disclaimer,
            mechanical_preview=None,
            connection_preview=None,
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
            validator = getattr(self._backend, "ValidateCellConnections", None)
            if callable(validator):
                result = validator(
                    Path(project.path),
                    contents,
                    query=self._snapshot.connection_query,
                    selected_endpoint_id=self._snapshot.connection_layout.selected_endpoint_id,
                    layout=self._snapshot.connection_layout,
                )
            else:
                result = self._backend.browse_connections(Path(project.path), contents)
        except Exception as error:
            return self._operation_failure(
                "Connection browser refresh", error, preserve_project=True
            )
        self._snapshot = replace(
            self._snapshot,
            connection_ports=result.ports,
            connection_edges=result.edges,
            connection_canvas=result.canvas,
            connection_layout=(
                result.canvas.layout
                if result.canvas is not None
                else self._snapshot.connection_layout
            ),
            safety_disclaimer=result.safety_disclaimer,
            validation=(*result.validation, *result.warnings),
            mechanical_preview=None,
            connection_preview=None,
            logs=self._append_log(
                LogLevel.INFO,
                f"Refreshed connection graph with {len(result.edges)} edge(s).",
            ),
        )
        return self._snapshot

    def preview_cell_connection(
        self,
        kind: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
        connection_id: str | None = None,
    ) -> StudioSnapshot:
        """Preview any typed edge through the project command boundary without staging it."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot preview a connection without a valid project.")
        command = getattr(self._backend, "PreviewCellConnection", None)
        if not callable(command):
            if kind == "mechanical" and connection_id is not None:
                return self.preview_mechanical_connection(
                    connection_id, from_component, from_port, to_component, to_port
                )
            return self._operation_failure(
                "Connection preview",
                AttributeError("Project backend does not expose PreviewCellConnection"),
                preserve_project=True,
            )
        try:
            result = command(
                Path(project.path),
                contents,
                kind=kind,
                from_component=from_component,
                from_port=from_port,
                to_component=to_component,
                to_port=to_port,
                connection_id=connection_id,
            )
        except Exception as error:
            return self._operation_failure("Connection preview", error, preserve_project=True)
        if result.connection_preview is None and result.edge is None and result.preview is None:
            return self._edit_rejected("Connection preview", result.validation)
        preview_id = result.connection_id
        if preview_id is None and result.connection_preview is not None:
            preview_id = result.connection_preview.edge_id
        self._snapshot = replace(
            self._snapshot,
            validation=(*result.validation, *result.warnings),
            mechanical_preview=result.preview,
            connection_preview=result.connection_preview,
            detail=(f"Previewed {kind} connection {preview_id or ''}; no sources changed."),
            logs=self._append_log(
                LogLevel.INFO, f"Previewed {kind} connection; no sources changed."
            ),
        )
        return self._snapshot

    def stage_cell_connection(
        self,
        kind: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
        connection_id: str | None = None,
    ) -> StudioSnapshot:
        """Stage any typed edge in both canonical buffers where the contract requires it."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot create a connection without a valid project.")
        command = getattr(self._backend, "StageCellConnection", None)
        if callable(command):
            try:
                result = command(
                    Path(project.path),
                    contents,
                    kind=kind,
                    from_component=from_component,
                    from_port=from_port,
                    to_component=to_component,
                    to_port=to_port,
                    connection_id=connection_id,
                )
            except Exception as error:
                return self._operation_failure("Connection staging", error, preserve_project=True)
        elif connection_id is not None:
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
                return self._operation_failure("Connection staging", error, preserve_project=True)
        else:
            return self._operation_failure(
                "Connection staging",
                AttributeError("Project backend does not expose StageCellConnection"),
                preserve_project=True,
            )
        if result.contents is None or result.edge is None:
            return self._edit_rejected("Connection staging", result.validation)
        self._record_edit(contents, project)
        self._working_contents = result.contents
        graph = self._connection_graph(Path(project.path), self._working_contents)
        spatial = self._spatial_graph(Path(project.path), self._working_contents)
        connection_key = result.connection_id or result.edge.connection_id
        self._snapshot = replace(
            self._snapshot,
            project=replace(project, connection_count=project.connection_count + 1),
            validation=result.warnings,
            dirty=self._working_contents != self._saved_contents,
            connection_ports=graph.ports,
            connection_edges=graph.edges,
            connection_canvas=graph.canvas,
            connection_layout=(
                graph.canvas.layout
                if graph.canvas is not None
                else self._snapshot.connection_layout
            ),
            spatial_components=spatial.components,
            safety_disclaimer=graph.safety_disclaimer,
            mechanical_preview=result.preview,
            connection_preview=result.connection_preview,
            can_undo=True,
            can_redo=False,
            detail=f"Staged {kind} connection {connection_key}; save to commit canonical sources.",
            logs=self._append_log(LogLevel.INFO, f"Staged {kind} connection {connection_key}."),
        )
        return self._snapshot

    def remove_cell_connection(self, connection_id: str) -> StudioSnapshot:
        """Stage removal of one edge and any paired mechanical scene reparent."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot remove a connection without a valid project.")
        command = getattr(self._backend, "RemoveCellConnection", None)
        if not callable(command):
            return self._operation_failure(
                "Connection removal",
                AttributeError("Project backend does not expose RemoveCellConnection"),
                preserve_project=True,
            )
        try:
            result = command(Path(project.path), contents, connection_id=connection_id)
        except Exception as error:
            return self._operation_failure("Connection removal", error, preserve_project=True)
        if result.contents is None:
            return self._edit_rejected("Connection removal", result.validation)
        self._record_edit(contents, project)
        self._working_contents = result.contents
        graph = self._connection_graph(Path(project.path), self._working_contents)
        spatial = self._spatial_graph(Path(project.path), self._working_contents)
        self._snapshot = replace(
            self._snapshot,
            project=replace(project, connection_count=max(0, project.connection_count - 1)),
            validation=result.warnings,
            dirty=self._working_contents != self._saved_contents,
            connection_ports=graph.ports,
            connection_edges=graph.edges,
            connection_canvas=graph.canvas,
            connection_layout=(
                graph.canvas.layout
                if graph.canvas is not None
                else self._snapshot.connection_layout
            ),
            spatial_components=spatial.components,
            safety_disclaimer=graph.safety_disclaimer,
            mechanical_preview=None,
            connection_preview=None,
            can_undo=True,
            can_redo=False,
            detail=f"Removed connection {connection_id}; save to commit canonical sources.",
            logs=self._append_log(LogLevel.INFO, f"Removed connection {connection_id}."),
        )
        return self._snapshot

    def validate_cell_connections(
        self,
        query: str = "",
        selected_endpoint_id: str | None = None,
        layout: ConnectionLayoutMetadata | None = None,
    ) -> StudioSnapshot:
        """Validate and render all connection layers without changing canonical buffers."""

        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot validate connections without a valid project.")
        command = getattr(self._backend, "ValidateCellConnections", None)
        if not callable(command):
            self._snapshot = replace(self._snapshot, connection_query=query)
            return self.refresh_connections()
        current_layout = layout or self._snapshot.connection_layout
        try:
            result = command(
                Path(project.path),
                contents,
                query=query,
                selected_endpoint_id=selected_endpoint_id,
                layout=current_layout,
            )
        except Exception as error:
            return self._operation_failure("Connection validation", error, preserve_project=True)
        self._snapshot = replace(
            self._snapshot,
            connection_query=query,
            connection_ports=result.ports,
            connection_edges=result.edges,
            connection_canvas=result.canvas,
            connection_layout=(
                result.canvas.layout if result.canvas is not None else current_layout
            ),
            safety_disclaimer=result.safety_disclaimer,
            validation=(*result.validation, *result.warnings),
            mechanical_preview=None,
            connection_preview=None,
            logs=self._append_log(LogLevel.INFO, "Validated connection layers."),
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
            connection_preview=result.connection_preview,
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
        spatial = self._spatial_graph(Path(project.path), self._working_contents)
        connection_graph = self._connection_graph(Path(project.path), self._working_contents)
        connection_edges = connection_graph.edges or (result.edge,)
        self._snapshot = replace(
            self._snapshot,
            status=StudioStatus.PROJECT_READY,
            headline=project.name,
            detail=f"Created connection {connection_id}; save to commit canonical sources.",
            project=replace(project, connection_count=project.connection_count + 1),
            dirty=self._working_contents != self._saved_contents,
            spatial_components=spatial.components,
            connection_ports=connection_graph.ports,
            connection_edges=connection_edges,
            connection_canvas=connection_graph.canvas,
            connection_layout=(
                connection_graph.canvas.layout
                if connection_graph.canvas is not None
                else self._snapshot.connection_layout
            ),
            mechanical_preview=result.preview,
            connection_preview=result.connection_preview,
            validation=result.warnings,
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
        spatial = self._spatial_graph(Path(project.path), self._working_contents)
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
            spatial_components=spatial.components,
            connection_ports=connection_graph.ports,
            connection_edges=connection_graph.edges,
            connection_canvas=connection_graph.canvas,
            connection_layout=(
                connection_graph.canvas.layout
                if connection_graph.canvas is not None
                else self._snapshot.connection_layout
            ),
            safety_disclaimer=connection_graph.safety_disclaimer,
            mechanical_preview=None,
            connection_preview=None,
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

    def import_calibration(
        self, instance_id: str, calibration: Mapping[str, object]
    ) -> StudioSnapshot:
        """Import and bind an existing immutable calibration until explicit save."""

        return self._spatial_edit(
            "Calibration import",
            lambda backend, path, contents: backend.import_calibration(
                path,
                contents,
                instance_id=instance_id,
                calibration=calibration,
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
            spatial_components=previous.spatial_components,
            connection_ports=previous.connection_ports,
            connection_edges=previous.connection_edges,
            connection_canvas=previous.connection_canvas,
            connection_layout=previous.connection_layout,
            connection_query=previous.connection_query,
            safety_disclaimer=previous.safety_disclaimer,
            mechanical_preview=previous.mechanical_preview,
            connection_preview=previous.connection_preview,
            tasks=previous.tasks,
            available_node_specs=previous.available_node_specs,
            recipes=previous.recipes,
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
            spatial_components=next_state.spatial_components,
            connection_ports=next_state.connection_ports,
            connection_edges=next_state.connection_edges,
            connection_canvas=next_state.connection_canvas,
            connection_layout=next_state.connection_layout,
            connection_query=next_state.connection_query,
            safety_disclaimer=next_state.safety_disclaimer,
            mechanical_preview=next_state.mechanical_preview,
            connection_preview=next_state.connection_preview,
            tasks=next_state.tasks,
            available_node_specs=next_state.available_node_specs,
            recipes=next_state.recipes,
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
                readiness_report=None,
                readiness_preview=None,
                browser=(),
                spatial_components=(),
                connection_ports=(),
                connection_edges=(),
                connection_canvas=None,
                connection_layout=ConnectionLayoutMetadata(),
                connection_query="",
                connection_preview=None,
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

        task_graph = self._task_graph(resolved_path, result.contents)
        recipe_graph = self._recipe_graph(resolved_path, result.contents)
        scenario_graph = self._scenario_graph(resolved_path, result.contents)
        evidence_records = self._evidence_records(resolved_path)
        deployment_graph = self._deployment_graph(resolved_path, result.contents)
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
            readiness_report=None,
            readiness_preview=None,
            authoring_form=None,
            authoring_candidate=None,
            spatial_components=(),
            connection_ports=(),
            connection_edges=(),
            connection_canvas=None,
            connection_layout=ConnectionLayoutMetadata(),
            connection_query="",
            safety_disclaimer="",
            mechanical_preview=None,
            connection_preview=None,
            tasks=task_graph.tasks,
            available_node_specs=task_graph.available_node_specs,
            recipes=recipe_graph.recipes,
            scenarios=scenario_graph.scenarios,
            evidence_records=evidence_records,
            deployment_profiles=deployment_graph.profiles,
            selected_scenario=None,
            selected_evidence=None,
            selected_deployment_profile=None,
            last_execution_result=None,
            last_replay_result=None,
            last_bundle_assembly=None,
            last_bundle_diff=None,
            last_signature_verification=None,
            last_compatibility_result=None,
            last_deployment_status=None,
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
            readiness_report=None,
            readiness_preview=None,
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

    def set_task_tree(self, task_id: str, tree: TaskTreeModel | str) -> StudioSnapshot:
        """Update or replace a task's BehaviorTree XML in staged project artifacts."""
        return self._task_edit(
            f"Task {task_id}",
            lambda backend, path, contents: backend.set_task_tree(
                path, contents, task_id=task_id, tree=tree
            ),
        )

    def edit_recipe(self, recipe_id: str, version: int, data: Mapping[str, Any]) -> StudioSnapshot:
        """Edit a draft recipe document in memory."""
        return self._recipe_edit(
            f"Recipe {recipe_id} v{version}",
            lambda backend, path, contents: backend.edit_recipe(
                path, contents, recipe_id=recipe_id, version=version, data=data
            ),
        )

    def create_recipe_version(
        self,
        recipe_id: str,
        base_version: int | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> StudioSnapshot:
        """Create a new immutable recipe version without mutating its predecessor."""
        return self._recipe_edit(
            f"New version of recipe {recipe_id}",
            lambda backend, path, contents: backend.create_recipe_version(
                path, contents, recipe_id=recipe_id, base_version=base_version, overrides=overrides
            ),
        )

    def transition_recipe_lifecycle(
        self,
        recipe_id: str,
        version: int,
        target_status: str,
        evidence: Sequence[str] | None = None,
    ) -> StudioSnapshot:
        """Transition a recipe version to a new lifecycle state."""
        return self._recipe_edit(
            f"Transition recipe {recipe_id} v{version} to {target_status}",
            lambda backend, path, contents: backend.transition_recipe_lifecycle(
                path,
                contents,
                recipe_id=recipe_id,
                version=version,
                target_status=target_status,
                evidence=evidence,
            ),
        )

    def refresh_tasks(self) -> StudioSnapshot:
        """Refresh tasks and available node manifests for the open project."""
        project = self._snapshot.project
        contents = self._working_contents
        if project is None or contents is None:
            return self._snapshot
        task_graph = self._task_graph(Path(project.path), contents)
        self._snapshot = replace(
            self._snapshot,
            tasks=task_graph.tasks,
            available_node_specs=task_graph.available_node_specs,
            validation=task_graph.validation or self._snapshot.validation,
        )
        return self._snapshot

    def refresh_recipes(self) -> StudioSnapshot:
        """Refresh recipes and validation findings for the open project."""
        project = self._snapshot.project
        contents = self._working_contents
        if project is None or contents is None:
            return self._snapshot
        recipe_graph = self._recipe_graph(Path(project.path), contents)
        self._snapshot = replace(
            self._snapshot,
            recipes=recipe_graph.recipes,
            project=replace(project, recipe_count=len(recipe_graph.recipes)),
            validation=recipe_graph.validation or self._snapshot.validation,
        )
        return self._snapshot

    def inspect_recipe(self, recipe_id: str, version: int | None = None) -> RecipeDetail | None:
        """Inspect specific recipe version fields and form schema metadata."""
        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None or project is None or contents is None:
            return None
        try:
            return self._backend.inspect_recipe(
                Path(project.path), contents, recipe_id=recipe_id, version=version
            )
        except Exception:
            return None

    def diff_recipes(
        self, recipe_id: str, version_a: int, version_b: int
    ) -> RecipeDiffResult | None:
        """Diff two recipe versions in the current project sources."""
        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None or project is None or contents is None:
            return None
        try:
            return self._backend.diff_recipes(
                Path(project.path),
                contents,
                recipe_id=recipe_id,
                version_a=version_a,
                version_b=version_b,
            )
        except Exception:
            return None

    def _task_edit(
        self,
        operation: str,
        command: Callable[[ProjectBackend, Path, ProjectContents], TaskEditResult],
    ) -> StudioSnapshot:
        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot edit tasks without a valid project.")
        try:
            result = command(self._backend, Path(project.path), contents)
        except Exception as error:
            return self._operation_failure(operation, error, preserve_project=True)
        if result.contents is None:
            return self._edit_rejected(operation, result.validation)
        self._record_edit(contents, project)
        self._working_contents = result.contents
        task_graph = self._task_graph(Path(project.path), self._working_contents)
        self._snapshot = replace(
            self._snapshot,
            detail=f"{operation} updated task in memory; save explicitly to persist.",
            tasks=task_graph.tasks,
            available_node_specs=task_graph.available_node_specs,
            validation=task_graph.validation,
            dirty=self._working_contents != self._saved_contents,
            can_undo=True,
            can_redo=False,
            logs=self._append_log(LogLevel.INFO, f"{operation} updated task in memory."),
        )
        return self._snapshot

    def _recipe_edit(
        self,
        operation: str,
        command: Callable[[ProjectBackend, Path, ProjectContents], RecipeEditResult],
    ) -> StudioSnapshot:
        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None:
            return self._snapshot
        if project is None or contents is None:
            return self._no_open_project("Cannot edit recipes without a valid project.")
        try:
            result = command(self._backend, Path(project.path), contents)
        except Exception as error:
            return self._operation_failure(operation, error, preserve_project=True)
        if result.contents is None:
            return self._edit_rejected(operation, result.validation)
        self._record_edit(contents, project)
        self._working_contents = result.contents
        recipe_graph = self._recipe_graph(Path(project.path), self._working_contents)
        self._snapshot = replace(
            self._snapshot,
            detail=f"{operation} updated recipe in memory; save explicitly to persist.",
            recipes=recipe_graph.recipes,
            project=replace(project, recipe_count=len(recipe_graph.recipes)),
            validation=recipe_graph.validation,
            dirty=self._working_contents != self._saved_contents,
            can_undo=True,
            can_redo=False,
            logs=self._append_log(LogLevel.INFO, f"{operation} updated recipe in memory."),
        )
        return self._snapshot

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
        spatial = self._spatial_graph(Path(project.path), self._working_contents)
        self._snapshot = replace(
            self._snapshot,
            detail=f"{operation} updated paired sources in memory; save explicitly to persist.",
            spatial_components=spatial.components,
            validation=spatial.validation,
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
            spatial_components=self._snapshot.spatial_components,
            connection_ports=self._snapshot.connection_ports,
            connection_edges=self._snapshot.connection_edges,
            connection_canvas=self._snapshot.connection_canvas,
            connection_layout=self._snapshot.connection_layout,
            connection_query=self._snapshot.connection_query,
            safety_disclaimer=self._snapshot.safety_disclaimer,
            mechanical_preview=self._snapshot.mechanical_preview,
            connection_preview=self._snapshot.connection_preview,
            tasks=self._snapshot.tasks,
            available_node_specs=self._snapshot.available_node_specs,
            recipes=self._snapshot.recipes,
            scenarios=self._snapshot.scenarios,
            evidence_records=self._snapshot.evidence_records,
            deployment_profiles=self._snapshot.deployment_profiles,
        )

    def _task_graph(self, project_path: Path, contents: ProjectContents) -> TaskBrowserResult:
        from cellforge.studio.task_service import TaskBrowserResult

        if self._backend is None:
            return TaskBrowserResult(
                tasks=self._snapshot.tasks, available_node_specs=self._snapshot.available_node_specs
            )
        try:
            return self._backend.browse_tasks(project_path, contents)
        except Exception:
            return TaskBrowserResult(
                tasks=self._snapshot.tasks, available_node_specs=self._snapshot.available_node_specs
            )

    def _recipe_graph(self, project_path: Path, contents: ProjectContents) -> RecipeBrowserResult:
        from cellforge.studio.recipe_service import RecipeBrowserResult

        if self._backend is None:
            return RecipeBrowserResult(recipes=self._snapshot.recipes)
        try:
            return self._backend.browse_recipes(project_path, contents)
        except Exception:
            return RecipeBrowserResult(recipes=self._snapshot.recipes)

    def _scenario_graph(
        self, project_path: Path, contents: ProjectContents
    ) -> ScenarioBrowserResult:
        from cellforge.studio.scenario_service import ScenarioBrowserResult

        if self._backend is None:
            return ScenarioBrowserResult(scenarios=self._snapshot.scenarios)
        try:
            return self._backend.browse_scenarios(project_path, contents)
        except Exception:
            return ScenarioBrowserResult(scenarios=self._snapshot.scenarios)

    def _evidence_records(self, project_path: Path) -> tuple[EvidenceSummary, ...]:
        if self._backend is None:
            return self._snapshot.evidence_records
        try:
            return self._backend.browse_evidence(project_path)
        except Exception:
            return self._snapshot.evidence_records

    def _deployment_graph(
        self, project_path: Path, contents: ProjectContents
    ) -> DeploymentBrowserResult:
        from cellforge.studio.deployment_service import DeploymentBrowserResult

        if self._backend is None:
            return DeploymentBrowserResult(profiles=self._snapshot.deployment_profiles)
        try:
            return self._backend.browse_deployment_profiles(project_path, contents)
        except Exception:
            return DeploymentBrowserResult(profiles=self._snapshot.deployment_profiles)

    def refresh_scenarios(self) -> StudioSnapshot:
        """Refresh scenarios declared in the open project."""
        project = self._snapshot.project
        contents = self._working_contents
        if project is None or contents is None:
            return self._snapshot
        scenario_graph = self._scenario_graph(Path(project.path), contents)
        self._snapshot = replace(
            self._snapshot,
            scenarios=scenario_graph.scenarios,
            validation=scenario_graph.validation or self._snapshot.validation,
        )
        return self._snapshot

    def inspect_scenario(self, scenario_id: str) -> ScenarioDetail | None:
        """Inspect specific scenario parameters and assertions."""
        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None or project is None or contents is None:
            return None
        try:
            detail = self._backend.inspect_scenario(
                Path(project.path), contents, scenario_id=scenario_id
            )
            if detail is not None:
                self._snapshot = replace(self._snapshot, selected_scenario=detail)
            return detail
        except Exception:
            return None

    def execute_scenario(
        self,
        scenario_id: str,
        *,
        seed_override: int | None = None,
        injected_faults: Sequence[ScenarioFaultSpec] | None = None,
        available_backend_fidelity: str = "L0",
        has_cuda_gpu: bool = False,
        actual_physx_executed: bool = False,
    ) -> StudioSnapshot:
        """Execute a scenario through the pure service and record evidence."""
        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None or project is None or contents is None:
            return self._no_open_project("Cannot execute scenario without a valid project.")
        try:
            result = self._backend.execute_scenario(
                Path(project.path),
                contents,
                scenario_id=scenario_id,
                seed_override=seed_override,
                injected_faults=injected_faults,
                available_backend_fidelity=available_backend_fidelity,
                has_cuda_gpu=has_cuda_gpu,
                actual_physx_executed=actual_physx_executed,
            )
            evidence_records = self._evidence_records(Path(project.path))
            self._snapshot = replace(
                self._snapshot,
                last_execution_result=result,
                evidence_records=evidence_records,
                detail=(
                    f"Scenario '{scenario_id}' executed: {result.final_status} "
                    f"(Fidelity: {result.fidelity.achieved})."
                ),
                logs=self._append_log(
                    LogLevel.INFO if result.passed else LogLevel.WARNING,
                    f"Executed scenario '{scenario_id}' with "
                    f"{result.fidelity.achieved} fidelity: {result.final_status}.",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure(
                f"Scenario execution '{scenario_id}'", error, preserve_project=True
            )

    def refresh_evidence(self) -> StudioSnapshot:
        """Refresh evidence files in the open project."""
        project = self._snapshot.project
        if project is None:
            return self._snapshot
        evidence_records = self._evidence_records(Path(project.path))
        self._snapshot = replace(
            self._snapshot,
            evidence_records=evidence_records,
        )
        return self._snapshot

    def inspect_evidence(self, evidence_path: str) -> EvidenceDetail | None:
        """Inspect specific simulation evidence document."""
        project = self._snapshot.project
        if self._backend is None or project is None:
            return None
        try:
            detail = self._backend.inspect_evidence(Path(project.path), evidence_path=evidence_path)
            if detail is not None:
                self._snapshot = replace(self._snapshot, selected_evidence=detail)
            return detail
        except Exception:
            return None

    def replay_evidence(
        self,
        evidence_path: str,
        expected_assertions: ScenarioAssertionSpec | None = None,
    ) -> StudioSnapshot:
        """Replay recorded evidence trace and verify deterministic consistency."""
        project = self._snapshot.project
        if self._backend is None or project is None:
            return self._no_open_project("Cannot replay evidence without a valid project.")
        try:
            replay_result = self._backend.replay_evidence(
                Path(project.path),
                evidence_path=evidence_path,
                expected_assertions=expected_assertions,
            )
            if replay_result is None:
                return self._operation_failure(
                    f"Replay evidence '{evidence_path}'",
                    RuntimeError("Evidence file not found"),
                    preserve_project=True,
                )
            match_str = "MATCHED" if replay_result.events_matched else "MISMATCH"
            self._snapshot = replace(
                self._snapshot,
                last_replay_result=replay_result,
                detail=f"Replayed evidence '{evidence_path}': {match_str}.",
                logs=self._append_log(
                    LogLevel.INFO if replay_result.passed else LogLevel.WARNING,
                    f"Replayed evidence '{evidence_path}' "
                    f"({replay_result.replayed_event_count} events).",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure(
                f"Replay evidence '{evidence_path}'", error, preserve_project=True
            )

    def refresh_deployment_profiles(self) -> StudioSnapshot:
        """Refresh deployment profiles declared in the project."""
        project = self._snapshot.project
        contents = self._working_contents
        if project is None or contents is None:
            return self._snapshot
        deployment_graph = self._deployment_graph(Path(project.path), contents)
        self._snapshot = replace(
            self._snapshot,
            deployment_profiles=deployment_graph.profiles,
            validation=deployment_graph.validation or self._snapshot.validation,
        )
        return self._snapshot

    def inspect_deployment_profile(self, profile_id: str) -> DeploymentProfileDetail | None:
        """Inspect full deployment profile configuration."""
        project = self._snapshot.project
        contents = self._working_contents
        if self._backend is None or project is None or contents is None:
            return None
        try:
            detail = self._backend.inspect_deployment_profile(
                Path(project.path), contents, profile_id=profile_id
            )
            if detail is not None:
                self._snapshot = replace(self._snapshot, selected_deployment_profile=detail)
            return detail
        except Exception:
            return None

    def assemble_bundle(
        self,
        *,
        target_profile: str,
        mode: str,
        source_revision: str,
        output_dir: Path,
        signing_key_path: Path,
        schemas_path: Path | None = None,
    ) -> StudioSnapshot:
        """Assemble an immutable signed bundle release."""
        project = self._snapshot.project
        if self._backend is None or project is None:
            return self._no_open_project("Cannot assemble bundle without a valid open project.")
        schemas = schemas_path or (Path(project.path) / "../../schemas").resolve()
        try:
            result = self._backend.assemble_bundle(
                Path(project.path),
                schemas,
                target_profile=target_profile,
                mode=mode,
                source_revision=source_revision,
                output_dir=output_dir,
                signing_key_path=signing_key_path,
            )
            err_msg = f"Bundle assembly failed: {result.error}"
            self._snapshot = replace(
                self._snapshot,
                last_bundle_assembly=result,
                detail=(
                    f"Assembled signed bundle '{result.bundle_id[:16]}...'."
                    if result.success
                    else err_msg
                ),
                logs=self._append_log(
                    LogLevel.INFO if result.success else LogLevel.ERROR,
                    f"Assembled signed bundle {result.bundle_id}."
                    if result.success
                    else f"Assembly failed: {result.error}",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure("Bundle assembly", error, preserve_project=True)

    def diff_bundles(self, base_bundle_path: Path, candidate_bundle_path: Path) -> StudioSnapshot:
        """Compute deterministic diff between two release bundles."""
        if self._backend is None:
            return self._snapshot
        try:
            diff_result = self._backend.diff_bundles(base_bundle_path, candidate_bundle_path)
            base_short = diff_result.base_bundle_id[:12]
            cand_short = diff_result.candidate_bundle_id[:12]
            self._snapshot = replace(
                self._snapshot,
                last_bundle_diff=diff_result,
                detail=f"Bundle diff: {diff_result.summary}",
                logs=self._append_log(
                    LogLevel.INFO,
                    f"Compared bundle {base_short} vs {cand_short}: {diff_result.summary}",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure("Bundle diff", error, preserve_project=True)

    def verify_bundle_signature(
        self, bundle_root: Path, trusted_keys_root: Path | None = None
    ) -> StudioSnapshot:
        """Verify Ed25519 signature and checksum inventory of a release bundle."""
        if self._backend is None:
            return self._snapshot
        try:
            sig_result = self._backend.verify_bundle_signature(bundle_root, trusted_keys_root)
            sig_status = "VALID" if sig_result.valid else "FAILED"
            sig_outcome = "VALID" if sig_result.valid else sig_result.message
            self._snapshot = replace(
                self._snapshot,
                last_signature_verification=sig_result,
                detail=f"Signature verification: {sig_status} ({sig_result.message}).",
                logs=self._append_log(
                    LogLevel.INFO if sig_result.valid else LogLevel.ERROR,
                    f"Signature check for {bundle_root.name}: {sig_outcome}.",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure("Signature verification", error, preserve_project=True)

    def preflight_target_compatibility(
        self, bundle_root: Path, target_facts_path: Path
    ) -> StudioSnapshot:
        """Check compatibility of a bundle against local target facts."""
        if self._backend is None:
            return self._snapshot
        try:
            compat_result = self._backend.preflight_target_compatibility(
                bundle_root, target_facts_path
            )
            compat_status = "COMPATIBLE" if compat_result.compatible else "INCOMPATIBLE"
            self._snapshot = replace(
                self._snapshot,
                last_compatibility_result=compat_result,
                detail=f"Target compatibility: {compat_status}.",
                logs=self._append_log(
                    LogLevel.INFO if compat_result.compatible else LogLevel.WARNING,
                    f"Target preflight for {bundle_root.name}: {compat_status}.",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure(
                "Target compatibility check", error, preserve_project=True
            )

    def refresh_deployment_status(self, agent_paths: AgentPaths) -> StudioSnapshot:
        """Query deployment agent status."""
        if self._backend is None:
            return self._snapshot
        try:
            status_result = self._backend.get_deployment_status(agent_paths)
            active_id = status_result.active_bundle_id or "none"
            self._snapshot = replace(
                self._snapshot,
                last_deployment_status=status_result,
                detail=f"Deployment agent status: {status_result.state} (Active: {active_id}).",
                logs=self._append_log(
                    LogLevel.INFO,
                    f"Agent status: {status_result.state}, active: {active_id}.",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure("Deployment status query", error, preserve_project=True)

    def install_bundle(
        self,
        bundle_root: Path,
        agent_paths: AgentPaths,
        *,
        systemd_runner: Any | None = None,
        health_checker: Any | None = None,
    ) -> StudioSnapshot:
        """Install a release bundle via BundleAgent."""
        if self._backend is None:
            return self._snapshot
        try:
            result = self._backend.install_bundle(
                bundle_root,
                agent_paths,
                systemd_runner=systemd_runner,
                health_checker=health_checker,
            )
            outcome = "SUCCESS" if result.success else result.error
            self._snapshot = replace(
                self._snapshot,
                last_deployment_status=result.status,
                detail=f"Bundle install: {'SUCCESS' if result.success else 'FAILED'}.",
                logs=self._append_log(
                    LogLevel.INFO if result.success else LogLevel.ERROR,
                    f"Installed bundle {result.bundle_id}: {outcome}.",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure("Bundle installation", error, preserve_project=True)

    def rollback_deployment(
        self,
        agent_paths: AgentPaths,
        *,
        systemd_runner: Any | None = None,
        health_checker: Any | None = None,
    ) -> StudioSnapshot:
        """Rollback to previous release via BundleAgent."""
        if self._backend is None:
            return self._snapshot
        try:
            result = self._backend.rollback_deployment(
                agent_paths, systemd_runner=systemd_runner, health_checker=health_checker
            )
            outcome = "SUCCESS" if result.success else result.error
            self._snapshot = replace(
                self._snapshot,
                last_deployment_status=result.status,
                detail=f"Deployment rollback: {'SUCCESS' if result.success else 'FAILED'}.",
                logs=self._append_log(
                    LogLevel.INFO if result.success else LogLevel.ERROR,
                    f"Rollback to {result.restored_bundle_id}: {outcome}.",
                ),
            )
            return self._snapshot
        except Exception as error:
            return self._operation_failure("Deployment rollback", error, preserve_project=True)

    def _spatial_graph(self, project_path: Path, contents: ProjectContents) -> SpatialBrowserResult:
        if self._backend is None:
            return SpatialBrowserResult(components=self._snapshot.spatial_components)
        try:
            return self._backend.browse_spatial(project_path, contents)
        except Exception:
            return SpatialBrowserResult(components=self._snapshot.spatial_components)

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
            validator = getattr(self._backend, "ValidateCellConnections", None)
            if callable(validator):
                return cast(
                    ConnectionBrowserResult,
                    validator(
                        project_path,
                        contents,
                        query=self._snapshot.connection_query,
                        selected_endpoint_id=self._snapshot.connection_layout.selected_endpoint_id,
                        layout=self._snapshot.connection_layout,
                    ),
                )
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


def _guided_validation_item(item: Any) -> ValidationItem:
    """Map the pure launcher finding into the existing validation-panel DTO."""

    return ValidationItem(
        code=str(item.code),
        severity=str(item.severity),
        path=str(item.path),
        message=str(item.message),
    )


def _authoring_validation(items: Sequence[Any]) -> tuple[ValidationItem, ...]:
    """Map schema-authoring findings into the existing validation-panel DTO."""

    return tuple(
        ValidationItem(
            code=str(item.code),
            severity=str(item.severity),
            path=str(item.path),
            message=str(item.message),
        )
        for item in items
    )
