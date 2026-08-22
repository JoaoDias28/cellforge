"""Task 039 guided launcher, deterministic preview, and explicit-save tests."""

import hashlib
import shutil
from pathlib import Path

import pytest

from cellforge.studio.application import StudioApplication
from cellforge.studio.guided_launcher import (
    CreateProjectRequest,
    GuidedProjectService,
    ProjectTemplateDescriptor,
    validate_project_preview_document,
)
from cellforge.studio.project_service import RECOVERY_FILE, ProjectCommandService

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = REPOSITORY_ROOT / "schemas"
PEN = REPOSITORY_ROOT / "examples" / "pen_engraving"
KITTING = REPOSITORY_ROOT / "examples" / "kitting"


def _request(
    destination: Path, *, template: str = "blank", seed: int = 3901
) -> CreateProjectRequest:
    return CreateProjectRequest(
        template_id=template,
        destination_directory=destination,
        cell_display_name="Guided Test Cell",
        requested_schema_version="0.1.0",
        seed=seed,
    )


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_same_request_produces_byte_identical_blank_preview_and_schema_validates(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "blank-cell"
    first = GuidedProjectService(SCHEMAS).CreateProject(_request(destination))
    second = GuidedProjectService(SCHEMAS).CreateProject(_request(destination))

    assert first == second
    assert first.can_save is True
    assert first.cell_id is not None
    assert "cell.yaml" in first.generated_paths
    assert "scene.usda" in first.generated_paths
    assert "behavior_tree.xml" in first.generated_paths
    assert first.candidate_hashes["cell.yaml"]
    validate_project_preview_document(first.as_dict())


def test_example_previews_are_read_only_and_keep_canonical_runtime_ids(tmp_path: Path) -> None:
    before_pen = _tree_hashes(PEN)
    before_kitting = _tree_hashes(KITTING)
    service = GuidedProjectService(SCHEMAS)

    pen = service.CreateProject(_request(tmp_path / "pen", template="pen_engraving", seed=3902))
    kitting = service.CreateProject(_request(tmp_path / "kitting", template="kitting", seed=3903))

    assert pen.can_save is True
    assert kitting.can_save is True
    assert "robot-001" in pen.component_instance_ids
    assert "robot-001" in kitting.component_instance_ids
    assert "safety-status-001" in kitting.component_instance_ids
    assert not (tmp_path / "pen").exists()
    assert not (tmp_path / "kitting").exists()
    assert _tree_hashes(PEN) == before_pen
    assert _tree_hashes(KITTING) == before_kitting


def test_application_preview_preserves_existing_dirty_state(tmp_path: Path) -> None:
    project_service = ProjectCommandService(SCHEMAS)
    application = StudioApplication(
        project_service,
        guided_service=GuidedProjectService(SCHEMAS, project_service=project_service),
    )

    opened = application.open_project(PEN)
    assert opened.project is not None
    dirty = application.edit_cell_yaml(opened.project.name)
    assert dirty.dirty is True

    preview = application.create_guided_project(_request(tmp_path / "preview"))

    assert preview.guided_preview is not None
    assert preview.dirty is True
    assert not (tmp_path / "preview").exists()


def test_guided_open_accepts_the_reusable_kitting_contract_without_writes() -> None:
    service = GuidedProjectService(SCHEMAS)
    before = _tree_hashes(KITTING)

    result = service.OpenProject(KITTING)

    assert result.is_valid is True
    assert result.project is not None
    assert result.project.cell_id == "6e3f8f7c-7aa9-4b72-b72d-9c6a7f6f0c31"
    assert result.source_hashes["cell.yaml"] == before["cell.yaml"]
    assert _tree_hashes(KITTING) == before


def test_ambiguous_and_invalid_inputs_are_structured_and_non_saveable(tmp_path: Path) -> None:
    ambiguous_templates = (
        ProjectTemplateDescriptor("alpha", "Alpha", "", None),
        ProjectTemplateDescriptor("alpine", "Alpine", "", None),
    )
    service = GuidedProjectService(SCHEMAS, template_descriptors=ambiguous_templates)

    ambiguous = service.CreateProject(_request(tmp_path / "ambiguous", template="al"))
    invalid_schema = service.CreateProject(
        CreateProjectRequest(
            template_id="alpha",
            destination_directory=tmp_path / "invalid-schema",
            cell_display_name="Cell",
            requested_schema_version="9.9.9",
        )
    )
    escaping = service.CreateProject(
        CreateProjectRequest(
            template_id="alpha",
            destination_directory=tmp_path / ".." / "escape",
            cell_display_name="Cell",
        )
    )

    assert ambiguous.can_save is False
    assert ambiguous.required_choices[0].key == "template_id"
    assert invalid_schema.can_save is False
    assert "studio.schema-version-unsupported" in {item.code for item in invalid_schema.findings}
    assert escaping.can_save is False
    assert "studio.destination-path-escape" in {item.code for item in escaping.findings}
    assert not (tmp_path / "escape").exists()
    validate_project_preview_document(service.PreviewProject("draft-" + "0" * 24).as_dict())


def test_duplicate_component_choice_and_missing_scene_fail_closed(tmp_path: Path) -> None:
    template = tmp_path / "broken-template"
    shutil.copytree(PEN, template)
    (template / "scene.usda").unlink()
    service = GuidedProjectService(
        SCHEMAS,
        template_descriptors=(ProjectTemplateDescriptor("broken", "Broken", "", template),),
    )

    missing_scene = service.CreateProject(_request(tmp_path / "missing-scene", template="broken"))
    duplicate = service.CreateProject(
        CreateProjectRequest(
            template_id="broken",
            destination_directory=tmp_path / "duplicate",
            cell_display_name="Cell",
            explicit_choices={
                "component_id:robot-001": "same-001",
                "component_id:gripper-001": "same-001",
            },
        )
    )

    assert missing_scene.can_save is False
    assert "studio.canonical-file-missing" in {item.code for item in missing_scene.findings}
    assert duplicate.can_save is False
    assert "studio.component-id-duplicate" in {item.code for item in duplicate.findings}


def test_save_requires_confirmation_then_reopens_identical_ids_and_hashes(tmp_path: Path) -> None:
    destination = tmp_path / "saved-cell"
    service = GuidedProjectService(SCHEMAS)
    preview = service.CreateProject(_request(destination, seed=3904))
    before = _tree_hashes(tmp_path)

    blocked = service.ConfirmProjectSave(preview)

    assert blocked.success is False
    assert "studio.save-confirmation-required" in {item.code for item in blocked.findings}
    assert _tree_hashes(tmp_path) == before

    saved = service.ConfirmProjectSave(
        preview.draft_id,
        preview.confirmation_token,
        confirmed=True,
    )
    reopened = service.OpenProject(destination)

    assert saved.success is True
    assert reopened.is_valid is True
    assert reopened.project is not None
    assert reopened.contents is not None
    assert reopened.source_hashes["cell.yaml"] == preview.candidate_hashes["cell.yaml"]
    assert reopened.source_hashes["scene.usda"] == preview.candidate_hashes["scene.usda"]
    assert service.CancelProjectDraft(preview).cancelled is False


def test_cancel_and_injected_new_tree_failure_leave_no_partial_destination(tmp_path: Path) -> None:
    destination = tmp_path / "cancelled"
    service = GuidedProjectService(SCHEMAS)
    preview = service.CreateProject(_request(destination, seed=3905))
    assert service.CancelProjectDraft(preview).cancelled is True
    assert not destination.exists()

    failed_destination = tmp_path / "failed"

    def fail_replace(_source: str | Path, _target: str | Path) -> None:
        raise OSError("injected guided replacement failure")

    failing_project_service = ProjectCommandService(SCHEMAS, replace_file=fail_replace)
    failing_service = GuidedProjectService(
        SCHEMAS,
        project_service=failing_project_service,
    )
    failed_preview = failing_service.CreateProject(_request(failed_destination, seed=3906))
    failed = failing_service.ConfirmProjectSave(
        failed_preview,
        confirmed=True,
    )

    assert failed.success is False
    assert "studio.new-project-save-failed" in {item.code for item in failed.findings}
    assert not failed_destination.exists()

    interrupted_destination = tmp_path / "interrupted"
    calls = 0

    class SimulatedProcessInterruption(BaseException):
        pass

    def interrupt_before_scene_replace(source: str | Path, target: str | Path) -> None:
        nonlocal calls
        calls += 1
        if Path(target).name == "scene.usda":
            raise SimulatedProcessInterruption
        Path(source).replace(target)

    interrupted_project_service = ProjectCommandService(
        SCHEMAS,
        replace_file=interrupt_before_scene_replace,
    )
    interrupted_service = GuidedProjectService(
        SCHEMAS,
        project_service=interrupted_project_service,
    )
    interrupted_preview = interrupted_service.CreateProject(
        _request(interrupted_destination, seed=3907)
    )

    with pytest.raises(SimulatedProcessInterruption):
        interrupted_service.ConfirmProjectSave(
            interrupted_preview,
            interrupted_preview.confirmation_token,
            confirmed=True,
        )

    assert calls > 1
    assert (interrupted_destination / RECOVERY_FILE).is_file()
    ProjectCommandService(SCHEMAS).recover(interrupted_destination)
    assert not (interrupted_destination / RECOVERY_FILE).exists()
    assert not (interrupted_destination / "cell.yaml").exists()
    assert not (interrupted_destination / "scene.usda").exists()
