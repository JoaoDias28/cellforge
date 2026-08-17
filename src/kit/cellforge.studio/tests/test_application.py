"""Headless tests for the pure Cell Studio application boundary."""

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from cellforge.studio.application import (
    BackendProject,
    BackendResult,
    BrowserComponent,
    BrowserResult,
    ComponentEditResult,
    ComponentFilters,
    ConnectionBrowserResult,
    ConnectionEdge,
    ConnectionEditResult,
    ProjectContents,
    SpatialBrowserResult,
    SpatialComponent,
    SpatialEditResult,
    StudioApplication,
    StudioStatus,
    ValidationItem,
)
from cellforge.studio.backend import create_default_application
from cellforge.studio.deployment_service import (
    AgentPaths,
    BundleAssemblyResult,
    BundleDiffResult,
    DeploymentBrowserResult,
    DeploymentInstallResult,
    DeploymentProfileDetail,
    DeploymentRollbackResult,
    DeploymentStatusResult,
    SignatureVerificationResult,
    TargetCompatibilityResult,
)
from cellforge.studio.recipe_service import (
    RecipeBrowserResult,
    RecipeDetail,
    RecipeDiffResult,
    RecipeEditResult,
)
from cellforge.studio.scenario_service import (
    EvidenceDetail,
    EvidenceSummary,
    FidelityInfo,
    ScenarioAssertionSpec,
    ScenarioBrowserResult,
    ScenarioDetail,
    ScenarioExecutionResult,
    ScenarioFaultSpec,
    ScenarioReplayResult,
)
from cellforge.studio.task_service import (
    TaskBrowserResult,
    TaskEditResult,
    TaskTreeModel,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PEN_PROJECT = REPOSITORY_ROOT / "examples" / "pen_engraving"


class RecordingBackend:
    def __init__(self, result: BackendResult) -> None:
        self.result = result
        self.paths: list[Path] = []
        self.created: list[Path] = []
        self.saved: list[tuple[Path, ProjectContents]] = []
        self.browser_result = BrowserResult(components=())
        self.edit_result = ComponentEditResult(contents=None)
        self.connection_browser_result = ConnectionBrowserResult(ports=(), edges=())
        self.connection_edit_result = ConnectionEditResult(contents=None)
        self.spatial_browser_result = SpatialBrowserResult(components=())
        self.spatial_edit_result = SpatialEditResult(contents=None)
        self.task_browser_result = TaskBrowserResult(tasks=(), available_node_specs=())
        self.task_edit_result = TaskEditResult(contents=None)
        self.recipe_browser_result = RecipeBrowserResult(recipes=())
        self.recipe_edit_result = RecipeEditResult(contents=None)
        self.recipe_detail: RecipeDetail | None = None
        self.recipe_diff_result: RecipeDiffResult | None = None
        self.scenario_browser_result = ScenarioBrowserResult(scenarios=())
        self.scenario_detail: ScenarioDetail | None = None
        self.scenario_execution_result = ScenarioExecutionResult(
            scenario_id="nominal",
            passed=True,
            final_status="SUCCESS",
            failures=(),
            fidelity=FidelityInfo("L0", "L0", "mock"),
            randomization_samples={},
            trace_events=(),
            evidence_document={},
        )
        self.evidence_summaries: tuple[EvidenceSummary, ...] = ()
        self.evidence_detail: EvidenceDetail | None = None
        self.scenario_replay_result: ScenarioReplayResult | None = None
        self.deployment_browser_result = DeploymentBrowserResult(profiles=())
        self.deployment_profile_detail: DeploymentProfileDetail | None = None
        self.bundle_assembly_result = BundleAssemblyResult(
            success=True, bundle_id="0" * 64, output_path=None, key_id="0" * 64
        )
        self.bundle_diff_result = BundleDiffResult("base", "cand", (), True, "compatible")
        self.signature_verification_result = SignatureVerificationResult(
            valid=True,
            key_id="0" * 64,
            algorithm="Ed25519",
            error_code=None,
            message="Signature valid",
            signed_files_count=10,
        )
        self.target_compatibility_result = TargetCompatibilityResult(
            compatible=True,
            profile_id="prof",
            platform_checks={},
            missing_packages=(),
            missing_prerequisites=(),
            missing_entrypoints=(),
            findings=(),
        )
        self.deployment_status_result = DeploymentStatusResult(
            state="healthy",
            active_bundle_id="0" * 64,
            previous_bundle_id=None,
            candidate_bundle_id=None,
            error=None,
            last_event="installed",
            event_count=1,
        )
        self.deployment_install_result = DeploymentInstallResult(
            success=True,
            bundle_id="0" * 64,
            status=DeploymentStatusResult(
                state="healthy",
                active_bundle_id="0" * 64,
                previous_bundle_id=None,
                candidate_bundle_id=None,
                error=None,
                last_event="installed",
                event_count=1,
            ),
        )
        self.deployment_rollback_result = DeploymentRollbackResult(
            success=True,
            restored_bundle_id="0" * 64,
            status=DeploymentStatusResult(
                state="healthy",
                active_bundle_id="0" * 64,
                previous_bundle_id=None,
                candidate_bundle_id=None,
                error=None,
                last_event="rolled_back",
                event_count=2,
            ),
        )

    def inspect(self, project_path: Path) -> BackendResult:
        self.paths.append(project_path)
        return self.result

    def create(self, project_path: Path) -> BackendResult:
        self.created.append(project_path)
        return self.result

    def save(self, project_path: Path, contents: ProjectContents) -> BackendResult:
        self.saved.append((project_path, contents))
        return self.result

    def browse_components(
        self, project_path: Path, filters: ComponentFilters = ComponentFilters()
    ) -> BrowserResult:
        return self.browser_result

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
        return self.edit_result

    def remove_component(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        remove_connections: bool,
    ) -> ComponentEditResult:
        return self.edit_result

    def browse_connections(
        self, project_path: Path, contents: ProjectContents
    ) -> ConnectionBrowserResult:
        return self.connection_browser_result

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
        return self.connection_edit_result

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
        return self.connection_edit_result

    def browse_spatial(self, project_path: Path, contents: ProjectContents) -> SpatialBrowserResult:
        return self.spatial_browser_result

    def set_component_transform(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        matrix: tuple[float, ...],
    ) -> SpatialEditResult:
        return self.spatial_edit_result

    def set_component_configuration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        configuration: Mapping[str, object],
    ) -> SpatialEditResult:
        return self.spatial_edit_result

    def set_component_variants(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        variants: Mapping[str, str],
    ) -> SpatialEditResult:
        return self.spatial_edit_result

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
        return self.spatial_edit_result

    def import_calibration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        calibration: Mapping[str, object],
    ) -> SpatialEditResult:
        return self.spatial_edit_result

    def browse_tasks(self, project_path: Path, contents: ProjectContents) -> TaskBrowserResult:
        return self.task_browser_result

    def set_task_tree(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        task_id: str,
        tree: TaskTreeModel | str,
    ) -> TaskEditResult:
        return self.task_edit_result

    def browse_recipes(self, project_path: Path, contents: ProjectContents) -> RecipeBrowserResult:
        return self.recipe_browser_result

    def inspect_recipe(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int | None = None,
    ) -> RecipeDetail | None:
        return self.recipe_detail

    def edit_recipe(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int,
        data: Mapping[str, object],
    ) -> RecipeEditResult:
        return self.recipe_edit_result

    def create_recipe_version(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        base_version: int | None = None,
        overrides: Mapping[str, object] | None = None,
    ) -> RecipeEditResult:
        return self.recipe_edit_result

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
        return self.recipe_edit_result

    def diff_recipes(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version_a: int,
        version_b: int,
    ) -> RecipeDiffResult | None:
        return self.recipe_diff_result

    def browse_scenarios(
        self, project_path: Path, contents: ProjectContents
    ) -> ScenarioBrowserResult:
        return self.scenario_browser_result

    def inspect_scenario(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        scenario_id: str,
    ) -> ScenarioDetail | None:
        return self.scenario_detail

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
        return self.scenario_execution_result

    def browse_evidence(self, project_path: Path) -> tuple[EvidenceSummary, ...]:
        return self.evidence_summaries

    def inspect_evidence(self, project_path: Path, *, evidence_path: str) -> EvidenceDetail | None:
        return self.evidence_detail

    def replay_evidence(
        self,
        project_path: Path,
        *,
        evidence_path: str,
        expected_assertions: ScenarioAssertionSpec | None = None,
    ) -> ScenarioReplayResult | None:
        return self.scenario_replay_result

    def browse_deployment_profiles(
        self, project_path: Path, contents: ProjectContents
    ) -> DeploymentBrowserResult:
        return self.deployment_browser_result

    def inspect_deployment_profile(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        profile_id: str,
    ) -> DeploymentProfileDetail | None:
        return self.deployment_profile_detail

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
        return self.bundle_assembly_result

    def diff_bundles(
        self,
        base_bundle_path: Path,
        candidate_bundle_path: Path,
    ) -> BundleDiffResult:
        return self.bundle_diff_result

    def verify_bundle_signature(
        self,
        bundle_root: Path,
        trusted_keys_root: Path | None = None,
    ) -> SignatureVerificationResult:
        return self.signature_verification_result

    def preflight_target_compatibility(
        self,
        bundle_root: Path,
        target_facts_path: Path,
    ) -> TargetCompatibilityResult:
        return self.target_compatibility_result

    def get_deployment_status(self, agent_paths: AgentPaths) -> DeploymentStatusResult:
        return self.deployment_status_result

    def install_bundle(
        self,
        bundle_root: Path,
        agent_paths: AgentPaths,
        *,
        systemd_runner: object | None = None,
        health_checker: object | None = None,
    ) -> DeploymentInstallResult:
        return self.deployment_install_result

    def rollback_deployment(
        self,
        agent_paths: AgentPaths,
        *,
        systemd_runner: object | None = None,
        health_checker: object | None = None,
    ) -> DeploymentRollbackResult:
        return self.deployment_rollback_result


def _tree_bytes(root: Path) -> Mapping[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_startup_is_a_useful_empty_state_and_does_not_call_backend() -> None:
    backend = RecordingBackend(BackendResult(project=None, validation=()))

    application = StudioApplication(backend)

    assert application.snapshot.status is StudioStatus.NO_PROJECT
    assert application.snapshot.headline == "No project open"
    assert "without opening or modifying" in application.snapshot.logs[0].message
    assert backend.paths == []


def test_spatial_browser_data_is_exposed_for_viewport_selection(tmp_path: Path) -> None:
    project = BackendProject(
        path=tmp_path,
        cell_id="00000000-0000-4000-8000-000000000001",
        name="Test Cell",
        scene="scene.usda",
        component_count=1,
        connection_count=0,
        task_count=0,
        recipe_count=0,
        scenario_count=0,
        deployment_profile_count=1,
    )
    contents = ProjectContents(cell_yaml="before", scene_usda="scene")
    backend = RecordingBackend(BackendResult(project=project, validation=(), contents=contents))
    component = SpatialComponent(
        instance_id="camera-001",
        alias="camera",
        usd_prim="/World/Camera",
        frames=("root", "optical"),
        collision_asset="assets/camera_collision.usd",
        transform=(1.0,) * 16,
    )
    backend.spatial_browser_result = SpatialBrowserResult(components=(component,))

    snapshot = StudioApplication(backend).open_project(tmp_path)

    assert snapshot.spatial_components == (component,)


def test_missing_backend_is_explicit_and_stable() -> None:
    application = StudioApplication(None, backend_unavailable_message="Install backend packages.")

    assert application.snapshot.status is StudioStatus.BACKEND_UNAVAILABLE
    assert application.snapshot.detail == "Install backend packages."
    assert application.open_project(PEN_PROJECT) is application.snapshot


def test_backend_validation_findings_are_rendered_without_ui_rules(tmp_path: Path) -> None:
    finding = ValidationItem(
        code="cli.cell-document-not-found",
        severity="error",
        path=f"{tmp_path / 'cell.yaml'}#",
        message="Project does not contain the required cell.yaml document.",
    )
    backend = RecordingBackend(BackendResult(project=None, validation=(finding,)))
    application = StudioApplication(backend)

    snapshot = application.open_project(tmp_path)

    assert snapshot.status is StudioStatus.PROJECT_INVALID
    assert snapshot.validation == (finding,)
    assert backend.paths == [tmp_path.resolve()]


def test_valid_backend_project_maps_to_presentation_state(tmp_path: Path) -> None:
    project = BackendProject(
        path=tmp_path,
        cell_id="00000000-0000-4000-8000-000000000001",
        name="Test Cell",
        scene="scene.usda",
        component_count=2,
        connection_count=1,
        task_count=1,
        recipe_count=1,
        scenario_count=3,
        deployment_profile_count=1,
    )
    contents = ProjectContents(cell_yaml="cell", scene_usda="scene")
    application = StudioApplication(
        RecordingBackend(BackendResult(project=project, validation=(), contents=contents))
    )

    snapshot = application.open_project(tmp_path)

    assert snapshot.status is StudioStatus.PROJECT_READY
    assert snapshot.project is not None
    assert snapshot.project.name == "Test Cell"
    assert snapshot.project.component_count == 2
    assert snapshot.dirty is False


def test_in_memory_edits_are_dirty_and_only_explicit_save_calls_backend(tmp_path: Path) -> None:
    project = BackendProject(
        path=tmp_path,
        cell_id="00000000-0000-4000-8000-000000000001",
        name="Test Cell",
        scene="scene.usda",
        component_count=0,
        connection_count=0,
        task_count=0,
        recipe_count=0,
        scenario_count=0,
        deployment_profile_count=1,
    )
    original = ProjectContents(cell_yaml="original cell", scene_usda="original scene")
    saved = ProjectContents(cell_yaml="changed cell", scene_usda="original scene")
    backend = RecordingBackend(BackendResult(project=project, validation=(), contents=original))
    application = StudioApplication(backend)
    application.open_project(tmp_path)

    snapshot = application.edit_cell_yaml(saved.cell_yaml)

    assert snapshot.dirty is True
    assert backend.saved == []

    backend.result = BackendResult(project=project, validation=(), contents=saved)
    snapshot = application.save_project()

    assert backend.saved == [(tmp_path.resolve(), saved)]
    assert snapshot.dirty is False


def test_component_placement_remove_undo_and_redo_are_paired_in_memory(
    tmp_path: Path,
) -> None:
    project = BackendProject(
        path=tmp_path,
        cell_id="00000000-0000-4000-8000-000000000001",
        name="Test Cell",
        scene="scene.usda",
        component_count=1,
        connection_count=0,
        task_count=0,
        recipe_count=0,
        scenario_count=0,
        deployment_profile_count=1,
    )
    original = ProjectContents(cell_yaml="one", scene_usda="one scene")
    placed = ProjectContents(cell_yaml="two", scene_usda="two scene")
    backend = RecordingBackend(BackendResult(project=project, validation=(), contents=original))
    backend.browser_result = BrowserResult(
        components=(
            BrowserComponent(
                component="generic.fixture.reference",
                version="0.1.0",
                kind="fixture",
                name="Fixture",
                manufacturer=None,
                model=None,
                description=None,
                license=None,
                package_path="fixture",
                capabilities=(),
                support_level="simulated",
                simulation_level="L1",
                compatible_modes=("simulation",),
                warnings=("not production-qualified",),
                variants=(),
            ),
        )
    )
    application = StudioApplication(backend)
    opened = application.open_project(tmp_path)
    assert len(opened.browser) == 1
    backend.edit_result = ComponentEditResult(contents=placed, instance_id="component-123")

    after_place = application.place_component("generic.fixture.reference", "0.1.0", "fixture", {})
    after_undo = application.undo()
    after_redo = application.redo()

    assert after_place.project is not None and after_place.project.component_count == 2
    assert after_place.dirty is True
    assert after_undo.project is not None and after_undo.project.component_count == 1
    assert after_undo.can_redo is True
    assert after_redo.project is not None and after_redo.project.component_count == 2
    assert after_redo.can_undo is True
    assert backend.saved == []


def test_modeled_safety_connection_is_distinct_and_undoable(tmp_path: Path) -> None:
    project = BackendProject(
        path=tmp_path,
        cell_id="00000000-0000-4000-8000-000000000001",
        name="Test Cell",
        scene="scene.usda",
        component_count=2,
        connection_count=0,
        task_count=0,
        recipe_count=0,
        scenario_count=0,
        deployment_profile_count=1,
    )
    original = ProjectContents(cell_yaml="before", scene_usda="scene")
    changed = ProjectContents(cell_yaml="after", scene_usda="scene")
    backend = RecordingBackend(BackendResult(project=project, validation=(), contents=original))
    application = StudioApplication(backend)
    application.open_project(tmp_path)
    edge = ConnectionEdge(
        connection_id="safety-edge",
        kind="safety",
        from_component="status-001",
        from_port="permitted",
        to_component="machine-001",
        to_port="permitted",
        port_type="safety.status.permitted",
        modeled_only=True,
        executable=False,
    )
    backend.connection_edit_result = ConnectionEditResult(
        contents=changed, connection_id=edge.connection_id, edge=edge
    )

    created = application.connect_ports(
        "safety-edge", "safety", "status-001", "permitted", "machine-001", "permitted"
    )
    undone = application.undo()

    assert created.connection_edges == (edge,)
    assert created.project is not None and created.project.connection_count == 1
    assert "modeled-only safety" in created.logs[-1].message
    assert undone.project is not None and undone.project.connection_count == 0
    assert undone.connection_edges == ()
    assert backend.saved == []


def test_spatial_configuration_edits_are_undoable_complete_buffer_pairs(tmp_path: Path) -> None:
    project = BackendProject(
        path=tmp_path,
        cell_id="00000000-0000-4000-8000-000000000001",
        name="Test Cell",
        scene="scene.usda",
        component_count=1,
        connection_count=0,
        task_count=0,
        recipe_count=0,
        scenario_count=0,
        deployment_profile_count=1,
    )
    original = ProjectContents(cell_yaml="before", scene_usda="before scene")
    changed = ProjectContents(
        cell_yaml="after", scene_usda="after scene", artifacts={"calibration/a.json": b"{}\n"}
    )
    backend = RecordingBackend(BackendResult(project=project, validation=(), contents=original))
    backend.spatial_edit_result = SpatialEditResult(
        contents=changed, calibration_path="calibration/a.json"
    )
    application = StudioApplication(backend)
    application.open_project(tmp_path)

    edited = application.create_calibration(
        "camera-001", "camera.intrinsics", "2030-01-01T00:00:00Z", {}
    )
    undone = application.undo()
    redone = application.redo()

    assert edited.dirty is True
    assert undone.dirty is False
    assert redone.dirty is True
    assert backend.saved == []


def test_backend_failure_is_sanitized_and_does_not_escape() -> None:
    class FailingBackend:
        def inspect(self, project_path: Path) -> BackendResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def create(self, project_path: Path) -> BackendResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def save(self, project_path: Path, contents: ProjectContents) -> BackendResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def browse_components(
            self, project_path: Path, filters: ComponentFilters = ComponentFilters()
        ) -> BrowserResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

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
            raise RuntimeError(f"sensitive detail at {project_path}")

        def remove_component(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            instance_id: str,
            remove_connections: bool,
        ) -> ComponentEditResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def browse_connections(
            self, project_path: Path, contents: ProjectContents
        ) -> ConnectionBrowserResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

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
            raise RuntimeError(f"sensitive detail at {project_path}")

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
            raise RuntimeError(f"sensitive detail at {project_path}")

        def browse_spatial(
            self, project_path: Path, contents: ProjectContents
        ) -> SpatialBrowserResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def set_component_transform(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            instance_id: str,
            matrix: tuple[float, ...],
        ) -> SpatialEditResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def set_component_configuration(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            instance_id: str,
            configuration: Mapping[str, object],
        ) -> SpatialEditResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def set_component_variants(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            instance_id: str,
            variants: Mapping[str, str],
        ) -> SpatialEditResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

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
            raise RuntimeError(f"sensitive detail at {project_path}")

        def import_calibration(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            instance_id: str,
            calibration: Mapping[str, object],
        ) -> SpatialEditResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def browse_tasks(self, project_path: Path, contents: ProjectContents) -> TaskBrowserResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def set_task_tree(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            task_id: str,
            tree: TaskTreeModel | str,
        ) -> TaskEditResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def browse_recipes(
            self, project_path: Path, contents: ProjectContents
        ) -> RecipeBrowserResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def inspect_recipe(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            recipe_id: str,
            version: int | None = None,
        ) -> RecipeDetail | None:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def edit_recipe(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            recipe_id: str,
            version: int,
            data: Mapping[str, object],
        ) -> RecipeEditResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def create_recipe_version(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            recipe_id: str,
            base_version: int | None = None,
            overrides: Mapping[str, object] | None = None,
        ) -> RecipeEditResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

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
            raise RuntimeError(f"sensitive detail at {project_path}")

        def diff_recipes(
            self,
            project_path: Path,
            contents: ProjectContents,
            *,
            recipe_id: str,
            version_a: int,
            version_b: int,
        ) -> RecipeDiffResult | None:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def browse_scenarios(
            self, project_path: Path, contents: ProjectContents
        ) -> ScenarioBrowserResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def inspect_scenario(
            self, project_path: Path, contents: ProjectContents, *, scenario_id: str
        ) -> ScenarioDetail | None:
            raise RuntimeError(f"sensitive detail at {project_path}")

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
            raise RuntimeError(f"sensitive detail at {project_path}")

        def browse_evidence(self, project_path: Path) -> tuple[EvidenceSummary, ...]:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def inspect_evidence(
            self, project_path: Path, *, evidence_path: str
        ) -> EvidenceDetail | None:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def replay_evidence(
            self,
            project_path: Path,
            *,
            evidence_path: str,
            expected_assertions: ScenarioAssertionSpec | None = None,
        ) -> ScenarioReplayResult | None:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def browse_deployment_profiles(
            self, project_path: Path, contents: ProjectContents
        ) -> DeploymentBrowserResult:
            raise RuntimeError(f"sensitive detail at {project_path}")

        def inspect_deployment_profile(
            self, project_path: Path, contents: ProjectContents, *, profile_id: str
        ) -> DeploymentProfileDetail | None:
            raise RuntimeError(f"sensitive detail at {project_path}")

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
            raise RuntimeError(f"sensitive detail at {project_path}")

        def diff_bundles(
            self, base_bundle_path: Path, candidate_bundle_path: Path
        ) -> BundleDiffResult:
            raise RuntimeError(f"sensitive detail at {base_bundle_path}")

        def verify_bundle_signature(
            self, bundle_root: Path, trusted_keys_root: Path | None = None
        ) -> SignatureVerificationResult:
            raise RuntimeError(f"sensitive detail at {bundle_root}")

        def preflight_target_compatibility(
            self, bundle_root: Path, target_facts_path: Path
        ) -> TargetCompatibilityResult:
            raise RuntimeError(f"sensitive detail at {bundle_root}")

        def get_deployment_status(self, agent_paths: AgentPaths) -> DeploymentStatusResult:
            raise RuntimeError(f"sensitive detail at {agent_paths}")

        def install_bundle(
            self,
            bundle_root: Path,
            agent_paths: AgentPaths,
            *,
            systemd_runner: object | None = None,
            health_checker: object | None = None,
        ) -> DeploymentInstallResult:
            raise RuntimeError(f"sensitive detail at {bundle_root}")

        def rollback_deployment(
            self,
            agent_paths: AgentPaths,
            *,
            systemd_runner: object | None = None,
            health_checker: object | None = None,
        ) -> DeploymentRollbackResult:
            raise RuntimeError(f"sensitive detail at {agent_paths}")

    snapshot = StudioApplication(FailingBackend()).open_project(PEN_PROJECT)

    assert snapshot.status is StudioStatus.OPERATION_FAILED
    assert "sensitive detail" not in snapshot.detail
    assert "RuntimeError" in snapshot.logs[-1].message


def test_default_backend_inspection_is_byte_for_byte_read_only(tmp_path: Path) -> None:
    project = tmp_path / "pen-project"
    shutil.copytree(PEN_PROJECT, project)
    shutil.copytree(REPOSITORY_ROOT / "schemas", project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    before = _tree_bytes(project)
    application = create_default_application()

    snapshot = application.open_project(project)

    assert snapshot.status is StudioStatus.PROJECT_READY
    assert snapshot.project is not None
    assert snapshot.project.name == "Pen Engraving Reference Cell"
    assert len(snapshot.tasks) > 0
    assert len(snapshot.recipes) > 0
    assert _tree_bytes(project) == before


def test_task_edit_updates_snapshot_and_supports_undo(tmp_path: Path) -> None:
    project = tmp_path / "pen-project"
    shutil.copytree(PEN_PROJECT, project)
    shutil.copytree(REPOSITORY_ROOT / "schemas", project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    application = create_default_application()
    application.open_project(project)

    valid_xml = """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <CheckRequiredDevicesReady ready="true"/>
    </Sequence>
  </BehaviorTree>
  <TreeNodesModel/>
</root>"""
    snap_after_edit = application.set_task_tree("pen_engraving", valid_xml)
    assert snap_after_edit.dirty is True
    assert snap_after_edit.can_undo is True

    # Undo task edit
    snap_after_undo = application.undo()
    assert snap_after_undo.can_redo is True

    # Redo task edit
    snap_after_redo = application.redo()
    assert snap_after_redo.dirty is True


def test_recipe_lifecycle_and_versioning_through_application(tmp_path: Path) -> None:
    project = tmp_path / "pen-project"
    shutil.copytree(PEN_PROJECT, project)
    shutil.copytree(REPOSITORY_ROOT / "schemas", project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    application = create_default_application()
    application.open_project(project)

    # Approve version 1
    snap_approved = application.transition_recipe_lifecycle(
        "pen-aluminium-reference",
        version=1,
        target_status="APPROVED",
    )
    assert snap_approved.dirty is True
    rec1 = next(
        r for r in snap_approved.recipes if r.id == "pen-aluminium-reference" and r.version == 1
    )
    assert rec1.is_immutable is True

    # Create version 2
    snap_v2 = application.create_recipe_version(
        "pen-aluminium-reference",
        base_version=1,
        overrides={"parameters": {"robot_speed_scale": 0.5}},
    )
    assert any(r.version == 2 for r in snap_v2.recipes if r.id == "pen-aluminium-reference")

    # Inspect recipe
    detail = application.inspect_recipe("pen-aluminium-reference", version=2)
    assert detail is not None
    assert detail.data["parameters"]["robot_speed_scale"] == 0.5

    # Diff versions
    diff = application.diff_recipes("pen-aluminium-reference", version_a=1, version_b=2)
    assert diff is not None
    assert any(d.key == "robot_speed_scale" for d in diff.differences)


def test_scenario_workflow_through_application() -> None:
    application = create_default_application()
    application.open_project(PEN_PROJECT)

    # Refresh scenarios
    snapshot = application.refresh_scenarios()
    assert len(snapshot.scenarios) == 14
    assert any(s.id == "pen-nominal" for s in snapshot.scenarios)

    # Inspect scenario
    detail = application.inspect_scenario("nominal")
    assert detail is not None
    assert detail.summary.id == "pen-nominal"
    assert detail.assertions.final_status == "SUCCESS"

    # Execute scenario
    snap_exec = application.execute_scenario("nominal", seed_override=1001)
    assert snap_exec.last_execution_result is not None
    assert snap_exec.last_execution_result.passed is True
    assert snap_exec.last_execution_result.fidelity.achieved == "L0"
    assert len(snap_exec.last_execution_result.trace_events) > 0


def test_deployment_workflow_through_application(tmp_path: Path) -> None:
    import hashlib

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    application = create_default_application()
    application.open_project(PEN_PROJECT)

    # Refresh deployment profiles
    snapshot = application.refresh_deployment_profiles()
    assert len(snapshot.deployment_profiles) == 2
    assert any(p.id == "pen-sim-amd64" for p in snapshot.deployment_profiles)

    # Inspect deployment profile
    detail = application.inspect_deployment_profile("deployment-sim")
    assert detail is not None
    assert detail.summary.id == "pen-sim-amd64"

    # Generate signing key
    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = tmp_path / "signing.pem"
    key_file.write_bytes(pem)

    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = hashlib.sha256(public_bytes).hexdigest()
    trusted_dir = tmp_path / "trusted-keys"
    trusted_dir.mkdir(parents=True, exist_ok=True)
    (trusted_dir / f"{key_id}.pub").write_bytes(public_bytes)

    # Assemble bundle
    bundle_out = tmp_path / "app_bundle"
    snap_asm = application.assemble_bundle(
        target_profile="pen-sim-amd64",
        mode="simulation",
        source_revision="0123456789abcdef0123456789abcdef01234567",
        output_dir=bundle_out,
        signing_key_path=key_file,
        schemas_path=REPOSITORY_ROOT / "schemas",
    )
    assert snap_asm.last_bundle_assembly is not None
    assert snap_asm.last_bundle_assembly.success is True

    # Verify signature
    snap_sig = application.verify_bundle_signature(bundle_out, trusted_dir)
    assert snap_sig.last_signature_verification is not None
    assert snap_sig.last_signature_verification.valid is True
