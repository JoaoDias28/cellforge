"""Focused Task 040 coverage for deterministic readiness and explicit remediation Save."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from cellforge.studio.application import ProjectContents, StudioApplication, StudioStatus
from cellforge.studio.project_service import ProjectCommandService
from cellforge.studio.readiness import (
    EvaluateStudioReadiness,
    ReadinessBackendProbe,
    ReadinessStatus,
    StudioReadinessReport,
    validate_studio_readiness_report_document,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = REPOSITORY_ROOT / "schemas"
PEN_PROJECT = REPOSITORY_ROOT / "examples" / "pen_engraving"
KITTING_PROJECT = REPOSITORY_ROOT / "examples" / "kitting"


def _project_copy(tmp_path: Path, source: Path = PEN_PROJECT) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
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


def _service(project_service: ProjectCommandService | None = None) -> EvaluateStudioReadiness:
    return EvaluateStudioReadiness(SCHEMAS, project_service=project_service)


def _statuses(report: StudioReadinessReport) -> dict[str, int]:
    return {
        status.value: sum(item.status == status for item in report.checks)
        for status in ReadinessStatus
    }


def test_nominal_pen_and_kitting_reports_are_source_linked_and_deterministic(
    tmp_path: Path,
) -> None:
    service = _service()
    pen = service.EvaluateStudioReadiness(PEN_PROJECT)
    kitting = service.EvaluateStudioReadiness(KITTING_PROJECT)

    assert pen.summary.blocked_count == 0
    assert kitting.summary.blocked_count == 0
    assert pen.requested_fidelity == "L0"
    assert pen.observed_fidelity == "L0"
    assert any(check.category == "safety_review" for check in pen.checks)
    assert all(check.source_reference for check in pen.checks)
    assert pen.to_json() == service.EvaluateStudioReadiness(PEN_PROJECT).to_json()
    assert "generated_at" not in pen.to_json()
    assert validate_studio_readiness_report_document(pen.normalized()) == ()
    assert validate_studio_readiness_report_document(kitting.normalized()) == ()


def test_missing_manifest_and_bad_behavior_tree_are_blocking(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    (project / "components" / "robot" / "component.yaml").unlink()
    missing_manifest = _service().EvaluateStudioReadiness(project)
    assert missing_manifest.summary.blocked_count > 0
    assert any(check.category == "components" for check in missing_manifest.blocked)
    assert any(check.remediation_id for check in missing_manifest.blocked)

    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    project = _project_copy(malformed_root)
    (project / "behavior_tree.xml").write_text("<root>", encoding="utf-8")
    malformed = _service().EvaluateStudioReadiness(project)
    assert malformed.summary.blocked_count > 0
    assert any(check.category == "tasks" for check in malformed.blocked)
    assert any("behavior_tree" in check.source_reference for check in malformed.checks)


def test_unresolved_simulation_adapter_is_blocked_and_source_linked(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    manifest_path = project / "components" / "robot" / "component.yaml"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest = manifest.replace(
        """  simulation:
    package: cellforge_simulation
    entrypoint: isaac_l2_adapter
    minimum_version: 0.1.0
    fidelity: L2
""",
        "  simulation: null\n",
    )
    manifest_path.write_text(manifest, encoding="utf-8")

    report = _service().EvaluateStudioReadiness(project)

    adapter_check = next(
        check for check in report.checks if check.validator_link == "resolver.adapter-missing"
    )
    assert adapter_check.status == ReadinessStatus.BLOCKED
    assert adapter_check.category == "adapters"
    assert "/components/0/adapter_mode" in adapter_check.source_reference


def test_absent_scenario_is_blocking_and_missing_calibration_is_advisory(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    cell = (project / "cell.yaml").read_text(encoding="utf-8")
    prefix, scenario_block = cell.split("scenarios:", 1)
    _, suffix = scenario_block.split("deployment_profiles:", 1)
    cell = f"{prefix}scenarios: []\ndeployment_profiles:{suffix}"
    (project / "cell.yaml").write_text(cell, encoding="utf-8")
    report = _service().EvaluateStudioReadiness(project)
    assert any(
        check.category == "scenarios" and check.status == ReadinessStatus.BLOCKED
        for check in report.checks
    )
    assert any(
        check.category == "calibration" and check.status == ReadinessStatus.ADVISORY
        for check in report.checks
    )


def test_unavailable_backend_never_becomes_an_l2_pass(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    report = _service().EvaluateStudioReadiness(
        project,
        requested_fidelity="L2",
        backend_probe=ReadinessBackendProbe(
            available=False,
            observed_fidelity="L0",
            detail="Isaac Sim/GPU probe unavailable",
        ),
    )
    fidelity = next(check for check in report.checks if check.category == "fidelity")
    assert fidelity.status == ReadinessStatus.UNAVAILABLE
    assert report.observed_fidelity == "unavailable"
    assert report.summary.pass_count == sum(
        check.status == ReadinessStatus.PASS for check in report.checks
    )


def test_stale_calibration_is_blocking_and_malformed_report_is_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    cell = (project / "cell.yaml").read_text(encoding="utf-8")
    cell = cell.replace("calibrations: []", "calibrations:\n  - calibration/missing.json")
    (project / "cell.yaml").write_text(cell, encoding="utf-8")
    stale = _service().EvaluateStudioReadiness(project)
    assert any(
        check.category == "calibration" and check.status == ReadinessStatus.BLOCKED
        for check in stale.checks
    )

    malformed = dict(stale.normalized())
    malformed["summary"] = {"overall_status": "pass"}
    assert validate_studio_readiness_report_document(malformed)


def test_remediation_preview_is_no_write_and_save_requires_explicit_confirmation(
    tmp_path: Path,
) -> None:
    project = _project_copy(tmp_path)
    service = _service()
    original = {name: (project / name).read_bytes() for name in ("cell.yaml", "scene.usda")}
    candidate = ProjectContents(
        cell_yaml=(project / "cell.yaml")
        .read_text(encoding="utf-8")
        .replace("Pen Engraving Reference Cell", "Previewed Pen Cell"),
        scene_usda=(project / "scene.usda").read_text(encoding="utf-8"),
    )
    preview = service.PreviewStudioReadinessRemediation(
        project,
        "readiness.open-validator",
        candidate_contents=candidate,
    )
    assert preview.can_save is True
    assert {name: (project / name).read_bytes() for name in original} == original

    rejected = service.SaveStudioReadiness(
        preview,
        preview.confirmation_token,
        confirmed=False,
    )
    assert rejected.success is False
    assert {name: (project / name).read_bytes() for name in original} == original

    saved = service.SaveStudioReadiness(
        preview,
        preview.confirmation_token,
        confirmed=True,
    )
    assert saved.success is True
    assert b"Previewed Pen Cell" in (project / "cell.yaml").read_bytes()


def test_injected_transaction_failure_preserves_canonical_hashes(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    calls = 0

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replacement failure")
        Path(source).replace(target)

    project_service = ProjectCommandService(SCHEMAS, replace_file=fail_second_replace)
    service = _service(project_service)
    contents = _contents(project)
    candidate = ProjectContents(
        cell_yaml=contents.cell_yaml.replace(
            "Pen Engraving Reference Cell", "Interrupted Pen Cell"
        ),
        scene_usda=contents.scene_usda,
    )
    preview = service.PreviewStudioReadinessRemediation(
        project,
        "readiness.open-validator",
        candidate_contents=candidate,
    )
    before = dict(preview.source_hashes_before)
    result = service.SaveStudioReadiness(
        preview,
        preview.confirmation_token,
        confirmed=True,
    )
    after = service.EvaluateStudioReadiness(project)
    assert result.success is False
    assert result.source_hashes_before == before
    assert result.source_hashes_after == before
    assert _sha256((project / "cell.yaml").read_bytes()) == before["cell.yaml"]
    assert after.project_identity.source_hashes["cell.yaml"] == before["cell.yaml"]
    assert not (project / ".cellforge-save-recovery.json").exists()


def test_backend_failure_is_explicitly_unavailable(tmp_path: Path) -> None:
    class BrokenBackend:
        def inspect(self, project_path: Path) -> object:
            raise RuntimeError("backend probe failed")

    service = EvaluateStudioReadiness(SCHEMAS, project_service=BrokenBackend())  # type: ignore[arg-type]
    report = service.EvaluateStudioReadiness(tmp_path / "missing")
    assert report.summary.unavailable_count == 1
    assert report.checks[0].category == "backend"
    assert "RuntimeError" in report.checks[0].message


def test_application_readiness_state_is_presentation_neutral(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    project_service = ProjectCommandService(SCHEMAS)
    readiness_service = _service(project_service)
    application = StudioApplication(
        project_service,
        readiness_service=readiness_service,
    )

    opened = application.open_project(project)
    assert opened.status == StudioStatus.PROJECT_READY
    evaluated = application.evaluate_readiness()
    assert evaluated.readiness_report is not None
    assert evaluated.readiness_report.project_identity.cell_id

    before = (project / "cell.yaml").read_bytes()
    candidate = ProjectContents(
        cell_yaml=(project / "cell.yaml")
        .read_text(encoding="utf-8")
        .replace("Pen Engraving Reference Cell", "Application Preview Cell"),
        scene_usda=(project / "scene.usda").read_text(encoding="utf-8"),
    )
    previewed = application.preview_readiness_remediation(
        "readiness.open-validator",
        candidate_contents=candidate,
    )
    assert previewed.readiness_preview is not None
    assert (project / "cell.yaml").read_bytes() == before


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
