"""Task 015 project/scene round-trip and transactional failure-path tests."""

import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from cellforge.studio.application import ProjectContents, StudioApplication, StudioStatus
from cellforge.studio.project_service import (
    RECOVERY_FILE,
    ProjectCommandService,
    ProjectSaveError,
)
from cellforge.studio.scene import inspect_usda

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PEN_PROJECT = REPOSITORY_ROOT / "examples" / "pen_engraving"
SCHEMAS = REPOSITORY_ROOT / "schemas"


def _project_copy(tmp_path: Path) -> Path:
    project = tmp_path / "pen-project"
    shutil.copytree(PEN_PROJECT, project)
    shutil.copytree(SCHEMAS, project / "schemas")
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "schema: ../../schemas/recipe.schema.json",
            "schema: schemas/recipe.schema.json",
        ),
        encoding="utf-8",
        newline="\n",
    )
    return project


def _canonical_pair(project: Path) -> tuple[bytes, bytes]:
    return (project / "cell.yaml").read_bytes(), (project / "scene.usda").read_bytes()


def test_create_initializes_a_linked_stage_and_opens_clean(tmp_path: Path) -> None:
    destination = tmp_path / "new-cell"
    service = ProjectCommandService(SCHEMAS)

    result = service.create(destination)

    assert result.project is not None
    assert result.contents is not None
    assert result.validation == ()
    assert 'cellforge:instanceId = "workspace-001"' in result.contents.scene_usda


def test_pen_open_is_byte_for_byte_read_only_and_ids_validate(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    before = _canonical_pair(project)

    result = ProjectCommandService(SCHEMAS).inspect(project)

    assert result.project is not None
    assert result.contents is not None
    assert result.project.component_count == 6
    assert result.validation == ()
    assert _canonical_pair(project) == before


def test_missing_prim_and_duplicate_scene_id_are_structured_findings(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    scene_path = project / "scene.usda"
    scene_text = scene_path.read_text(encoding="utf-8")
    scene_path.write_text(
        scene_text.replace('def Xform "Fixture" {', 'def Xform "FixtureMissing" {').replace(
            'cellforge:instanceId = "camera-001"',
            'cellforge:instanceId = "robot-001"',
        ),
        encoding="utf-8",
        newline="\n",
    )

    service = ProjectCommandService(SCHEMAS)
    result = service.inspect(project)
    snapshot = StudioApplication(service).open_project(project)
    codes = {finding.code for finding in result.validation}

    assert result.project is None
    assert snapshot.status is StudioStatus.PROJECT_INVALID
    assert {finding.code for finding in snapshot.validation} == codes
    assert "studio.scene-prim-missing" in codes
    assert "studio.scene-instance-id-duplicate" in codes


def test_duplicate_operational_instance_id_is_a_validation_panel_finding(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    cell_path = project / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace("id: camera-001", "id: robot-001"),
        encoding="utf-8",
        newline="\n",
    )

    snapshot = StudioApplication(ProjectCommandService(SCHEMAS)).open_project(project)

    assert snapshot.status is StudioStatus.PROJECT_INVALID
    assert "studio.instance-id-duplicate" in {item.code for item in snapshot.validation}


def test_round_trip_preserves_canonical_ids_and_scene_content(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = ProjectCommandService(SCHEMAS)
    opened = service.inspect(project)
    assert opened.contents is not None
    changed_yaml = opened.contents.cell_yaml.replace(
        "name: Pen Engraving Reference Cell",
        "name: Pen Engraving Round Trip Cell",
    )

    saved = service.save(
        project,
        ProjectContents(cell_yaml=changed_yaml, scene_usda=opened.contents.scene_usda),
    )
    reopened = service.inspect(project)

    assert saved.project is not None
    assert reopened.project is not None
    assert reopened.project.name == "Pen Engraving Round Trip Cell"
    assert reopened.contents is not None
    assert reopened.contents.scene_usda == opened.contents.scene_usda
    cell_data = yaml.safe_load(reopened.contents.cell_yaml)
    assert isinstance(cell_data, Mapping)
    component_ids = {item["id"] for item in cell_data["components"]}
    scene, findings = inspect_usda(reopened.contents.scene_usda, project / "scene.usda")
    assert findings == ()
    assert scene is not None
    assert {prim.instance_id for prim in scene.prims if prim.instance_id} == component_ids


def test_invalid_candidate_blocks_save_and_preserves_both_files(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = ProjectCommandService(SCHEMAS)
    opened = service.inspect(project)
    assert opened.contents is not None
    before = _canonical_pair(project)

    result = service.save(
        project,
        ProjectContents(cell_yaml="components: [", scene_usda=opened.contents.scene_usda),
    )

    assert result.project is None
    assert {item.code for item in result.validation} == {"source.parse-failed"}
    assert _canonical_pair(project) == before


def test_broken_cross_file_reference_blocks_save(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = ProjectCommandService(SCHEMAS)
    opened = service.inspect(project)
    assert opened.contents is not None
    before = _canonical_pair(project)
    changed = opened.contents.cell_yaml.replace("path: recipe.yaml", "path: missing-recipe.yaml")

    result = service.save(
        project,
        ProjectContents(cell_yaml=changed, scene_usda=opened.contents.scene_usda),
    )

    assert result.project is None
    assert result.validation
    assert _canonical_pair(project) == before


def test_second_replace_failure_restores_last_valid_pair(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    before = _canonical_pair(project)
    calls = 0
    saw_journal = False

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal calls, saw_journal
        calls += 1
        saw_journal = saw_journal or (project / RECOVERY_FILE).is_file()
        if calls == 2:
            raise OSError("injected replacement failure")
        Path(source).replace(target)

    service = ProjectCommandService(SCHEMAS, replace_file=fail_second_replace)
    opened = service.inspect(project)
    assert opened.contents is not None
    changed = opened.contents.cell_yaml.replace(
        "name: Pen Engraving Reference Cell",
        "name: Interrupted Save",
    )

    with pytest.raises(ProjectSaveError, match="previous cell.yaml and USD scene were restored"):
        service.save(
            project,
            ProjectContents(cell_yaml=changed, scene_usda=opened.contents.scene_usda),
        )

    assert saw_journal is True
    assert _canonical_pair(project) == before
    assert not (project / RECOVERY_FILE).exists()
    assert ProjectCommandService(SCHEMAS).inspect(project).project is not None


def test_recovery_journal_restores_pair_after_abrupt_interruption(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    before = _canonical_pair(project)
    calls = 0

    class SimulatedProcessInterruption(BaseException):
        pass

    def interrupt_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SimulatedProcessInterruption
        Path(source).replace(target)

    service = ProjectCommandService(SCHEMAS, replace_file=interrupt_second_replace)
    opened = service.inspect(project)
    assert opened.contents is not None
    changed = opened.contents.cell_yaml.replace(
        "name: Pen Engraving Reference Cell",
        "name: Abruptly Interrupted Save",
    )
    changed_scene = opened.contents.scene_usda.replace(
        "#usda 1.0\n",
        "#usda 1.0\n# Candidate scene edit\n",
    )

    with pytest.raises(SimulatedProcessInterruption):
        service.save(
            project,
            ProjectContents(cell_yaml=changed, scene_usda=changed_scene),
        )

    assert (project / RECOVERY_FILE).is_file()
    assert _canonical_pair(project) != before

    ProjectCommandService(SCHEMAS).recover(project)

    assert _canonical_pair(project) == before
    assert not (project / RECOVERY_FILE).exists()
    assert ProjectCommandService(SCHEMAS).inspect(project).project is not None


def test_application_edits_do_not_write_until_explicit_save(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    application = StudioApplication(ProjectCommandService(SCHEMAS))
    opened = application.open_project(project)
    assert opened.status is StudioStatus.PROJECT_READY
    before = _canonical_pair(project)
    cell_text = (project / "cell.yaml").read_text(encoding="utf-8")

    dirty = application.edit_cell_yaml(
        cell_text.replace("name: Pen Engraving Reference Cell", "name: Explicit Save Cell")
    )

    assert dirty.dirty is True
    assert _canonical_pair(project) == before

    saved = application.save_project()

    assert saved.status is StudioStatus.PROJECT_READY
    assert saved.dirty is False
    assert _canonical_pair(project) != before
