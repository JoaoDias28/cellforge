"""Acceptance coverage for Task 028's pure spatial configuration commands."""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from cellforge.studio.application import ProjectContents
from cellforge.studio.project_service import ProjectCommandService
from cellforge.studio.spatial_configuration import SpatialConfigurationService

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PEN_PROJECT = REPOSITORY_ROOT / "examples" / "pen_engraving"
SCHEMAS = REPOSITORY_ROOT / "schemas"
NOW = datetime(2026, 8, 13, tzinfo=UTC)


def _project_copy(tmp_path: Path) -> Path:
    target = tmp_path / "pen_engraving"
    shutil.copytree(PEN_PROJECT, target)
    shutil.copytree(SCHEMAS, target / "schemas")
    cell_path = target / "cell.yaml"
    cell_path.write_text(
        cell_path.read_text(encoding="utf-8").replace(
            "../../schemas/recipe.schema.json", "schemas/recipe.schema.json"
        ),
        encoding="utf-8",
    )
    return target


def _contents(project: Path) -> ProjectContents:
    return ProjectContents(
        cell_yaml=(project / "cell.yaml").read_text(encoding="utf-8"),
        scene_usda=(project / "scene.usda").read_text(encoding="utf-8"),
    )


def _service() -> SpatialConfigurationService:
    return SpatialConfigurationService(
        SCHEMAS,
        new_uuid=lambda: UUID("00000000-0000-4000-8000-000000000009"),
        now=lambda: NOW,
    )


def test_transform_configuration_and_selection_preserve_paired_identity(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = _service()
    original = _contents(project)

    browser = service.browse(project, original)
    transformed = service.set_transform(
        project,
        original,
        instance_id="camera-001",
        matrix=(1.0, 0.0, 0.0, 0.75, 0.0, 1.0, 0.0, -0.35, 0.0, 0.0, 1.0, 1.2, 0.0, 0.0, 0.0, 1.0),
    )
    configured = service.set_component_configuration(
        project,
        transformed.contents or original,
        instance_id="robot-001",
        configuration={"controller_namespace": "/configured_robot"},
    )

    assert not browser.validation
    assert any(
        item.instance_id == "camera-001" and "root" in item.frames for item in browser.components
    )
    assert transformed.contents is not None
    assert "matrix4d xformOp:transform" in transformed.contents.scene_usda
    assert configured.contents is not None
    assert "/configured_robot" in configured.contents.cell_yaml
    assert "camera-001" in configured.contents.scene_usda


def test_invalid_transform_and_configuration_leave_both_buffers_unchanged(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = _service()
    original = _contents(project)

    invalid_transform = service.set_transform(
        project, original, instance_id="camera-001", matrix=(0.0,) * 16
    )
    invalid_configuration = service.set_component_configuration(
        project,
        original,
        instance_id="robot-001",
        configuration={"controller_namespace": 42},
    )

    assert invalid_transform.contents is None
    assert invalid_transform.validation[0].code == "studio.spatial-transform-invalid"
    assert invalid_configuration.contents is None
    assert invalid_configuration.validation[0].code == "studio.component-configuration-invalid"
    assert _contents(project) == original


def test_calibration_creation_is_digest_checked_bound_and_saved_transactionally(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    service = _service()
    created = service.create_calibration(
        project,
        _contents(project),
        instance_id="camera-001",
        kind="camera.intrinsics",
        valid_until=NOW + timedelta(days=7),
        data={"focal_length_mm": 12.0},
    )

    assert created.contents is not None
    assert created.calibration_path == "calibration/00000000-0000-4000-8000-000000000009.json"
    assert created.calibration_path in created.contents.artifacts
    assert created.calibration_path in created.contents.cell_yaml

    saved = ProjectCommandService(SCHEMAS).save(project, created.contents)
    reopened = ProjectCommandService(SCHEMAS).inspect(project)

    assert saved.project is not None
    assert reopened.project is not None
    assert (project / created.calibration_path).is_file()
    assert created.calibration_path in (reopened.contents or _contents(project)).cell_yaml


def test_expired_mismatched_or_wrongly_bound_calibration_is_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    service = _service()
    created = service.create_calibration(
        project,
        _contents(project),
        instance_id="camera-001",
        kind="camera.intrinsics",
        valid_until=NOW - timedelta(seconds=1),
        data={},
    )
    imported = service.import_calibration(
        project,
        _contents(project),
        instance_id="camera-001",
        calibration={
            "schema_version": "0.1.0",
            "calibration_id": "00000000-0000-4000-8000-000000000010",
            "component_instance_id": "robot-001",
            "kind": "camera.intrinsics",
            "created_at": "2026-08-13T00:00:00Z",
            "valid_until": "2026-08-20T00:00:00Z",
            "data": {},
            "sha256": "0" * 64,
        },
    )

    assert created.contents is None
    assert any(item.code == "studio.calibration-expired" for item in created.validation)
    assert imported.contents is None
    assert {item.code for item in imported.validation} >= {
        "studio.calibration-component-mismatch",
        "studio.calibration-digest-invalid",
    }
