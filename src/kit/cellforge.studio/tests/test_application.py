"""Headless tests for the pure Cell Studio application boundary."""

import shutil
from collections.abc import Mapping
from pathlib import Path

from cellforge.studio.application import (
    BackendProject,
    BackendResult,
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

    def inspect(self, project_path: Path) -> BackendResult:
        self.paths.append(project_path)
        return self.result


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
    application = StudioApplication(RecordingBackend(BackendResult(project=project, validation=())))

    snapshot = application.open_project(tmp_path)

    assert snapshot.status is StudioStatus.PROJECT_READY
    assert snapshot.project is not None
    assert snapshot.project.name == "Test Cell"
    assert snapshot.project.component_count == 2
    assert "read-only" in snapshot.detail


def test_backend_failure_is_sanitized_and_does_not_escape() -> None:
    class FailingBackend:
        def inspect(self, project_path: Path) -> BackendResult:
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
