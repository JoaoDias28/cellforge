"""Headless tests for the pure Cell Studio application boundary."""

import shutil
from collections.abc import Mapping
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
    SpatialEditResult,
    StudioApplication,
    StudioStatus,
    ValidationItem,
)
from cellforge.studio.backend import create_default_application

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
        self.spatial_edit_result = SpatialEditResult(contents=None)

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
    assert _tree_bytes(project) == before
