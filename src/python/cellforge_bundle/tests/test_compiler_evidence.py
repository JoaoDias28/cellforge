"""Comprehensive tests for compiler evidence-policy verification."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cellforge_bundle import compile_project
from cellforge_domain import ExecutionMode
from cellforge_platform.auth.signing import PlatformSigner

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "pen_engraving"
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas"
SOURCE_REVISION = "a" * 40
CELL_ID = "0d3c6b63-a57f-4207-8638-e4cf76efec90"


def _project_copy(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(EXAMPLE_ROOT, project)
    shutil.copytree(SCHEMA_ROOT, project / "schemas")
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


def _build_valid_snapshot(
    project: Path,
    signer: PlatformSigner,
    *,
    cell_id: str = CELL_ID,
    valid_until: str | None = None,
    recipe_status: str = "APPROVED",
    created_by: str = "alice",
    approvals: list[dict[str, Any]] | None = None,
    evidence_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if valid_until is None:
        valid_until = (datetime.now(UTC) + timedelta(days=30)).isoformat()

    # Compute actual recipe sha256
    recipe_bytes = (project / "recipe.yaml").read_bytes()
    recipe_sha256 = hashlib.sha256(recipe_bytes).hexdigest()

    if approvals is None:
        approvals = [
            {
                "approval_id": "app-1",
                "approver_id": "bob",
                "role": "automation_engineer",
                "decision": "approved",
                "recorded_at": "2026-08-18T10:00:00Z",
            },
            {
                "approval_id": "app-2",
                "approver_id": "carol",
                "role": "process_engineer",
                "decision": "approved",
                "recorded_at": "2026-08-18T11:00:00Z",
            },
        ]

    recipes_list = [
        {
            "recipe_id": "pen-aluminium-reference",
            "version": 1,
            "name": "Aluminium pen reference engraving",
            "status": recipe_status,
            "created_by": created_by,
            "recipe_sha256": recipe_sha256,
            "is_approved_for_production": (recipe_status == "APPROVED"),
            "approvals": approvals,
        }
    ]

    if evidence_records is None:
        evidence_records = [
            {
                "evidence_id": "ev-sim-1",
                "kind": "simulation",
                "cell_id": cell_id,
                "subject": {"cell_id": cell_id},
                "artifact_sha256": "1" * 64,
                "issuer": "ci_pipeline",
                "recorded_at": "2026-08-18T10:00:00Z",
            },
            {
                "evidence_id": "ev-calib-1",
                "kind": "calibration",
                "cell_id": cell_id,
                "subject": {"cell_id": cell_id, "component_instance_id": "robot-001"},
                "artifact_sha256": "2" * 64,
                "issuer": "calibrator_device",
                "recorded_at": "2026-08-18T10:00:00Z",
            },
            {
                "evidence_id": "ev-comm-1",
                "kind": "commissioning",
                "cell_id": cell_id,
                "subject": {"cell_id": cell_id},
                "artifact_sha256": "3" * 64,
                "issuer": "field_engineer",
                "recorded_at": "2026-08-18T10:00:00Z",
            },
            {
                "evidence_id": "ev-safe-1",
                "kind": "safety_review",
                "cell_id": cell_id,
                "subject": {"cell_id": cell_id},
                "artifact_sha256": "4" * 64,
                "issuer": "safety_officer",
                "recorded_at": "2026-08-18T10:00:00Z",
            },
        ]

    doc = {
        "schema_version": "0.1.0",
        "snapshot_id": str(uuid.uuid4()),
        "cell_id": cell_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "valid_until": valid_until,
        "key_id": signer.key_id,
        "recipes": recipes_list,
        "evidence": evidence_records,
    }
    sig = signer.sign_document(doc)
    doc["signature"] = sig
    return doc


def test_simulation_mode_evidence_not_required(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.SIMULATION,
        source_revision=SOURCE_REVISION,
    )
    assert report.valid is True
    assert report.manifest is not None
    assert report.manifest.evidence.required is False
    assert report.manifest.evidence.status == "not-required"


def test_production_missing_snapshot_fails_closed(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.production-evidence-unverified" in codes
    assert "compiler.production-evidence-missing" in codes


def test_production_valid_signed_snapshot_verified(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(project, signer)
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    # Update recipe status in project to APPROVED so recipe stage passes
    recipe_path = project / "recipe.yaml"
    recipe_path.write_text(
        recipe_path.read_text(encoding="utf-8").replace("status: TESTED", "status: APPROVED"),
        encoding="utf-8",
        newline="\n",
    )

    # Re-generate snapshot with updated recipe sha256
    snapshot = _build_valid_snapshot(project, signer)

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.SIMULATION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is True
    assert report.manifest is not None
    assert report.manifest.evidence.required is True
    assert report.manifest.evidence.status == "verified"


def test_tampered_artifact_digest_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(project, signer)
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    # Tamper with an artifact sha256 to not be 64-hex
    snapshot["evidence"][0]["artifact_sha256"] = "invalid_short_hash"
    snapshot["signature"] = signer.sign_document(
        {k: v for k, v in snapshot.items() if k != "signature"}
    )

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.tampered-artifact" in codes


def test_stale_snapshot_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(
        project,
        signer,
        valid_until="2020-01-01T00:00:00Z",
    )
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.stale-snapshot" in codes


def test_stale_evidence_record_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(project, signer)
    snapshot["evidence"][0]["valid_until"] = "2020-01-01T00:00:00Z"
    snapshot["signature"] = signer.sign_document(
        {k: v for k, v in snapshot.items() if k != "signature"}
    )
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.stale-evidence" in codes


def test_unsigned_snapshot_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(project, signer)
    snapshot["signature"] = ""
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.unsigned-snapshot" in codes


def test_invalid_signature_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(project, signer)
    # Modify data after signing
    snapshot["cell_id"] = CELL_ID
    snapshot["snapshot_id"] = "tampered-id"
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.invalid-signature" in codes


def test_cell_mismatch_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(
        project, signer, cell_id="11111111-2222-3333-4444-555555555555"
    )
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.cell-mismatch" in codes


def test_wrong_component_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(project, signer)
    snapshot["evidence"][1]["subject"]["component_instance_id"] = "non-existent-robot-999"
    snapshot["signature"] = signer.sign_document(
        {k: v for k, v in snapshot.items() if k != "signature"}
    )
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.wrong-component" in codes


def test_self_approved_recipe_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    # Recipe created by alice, only approved by alice
    self_approvals = [
        {
            "approval_id": "app-1",
            "approver_id": "alice",
            "role": "process_engineer",
            "decision": "approved",
        }
    ]
    snapshot = _build_valid_snapshot(
        project,
        signer,
        created_by="alice",
        approvals=self_approvals,
    )
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.self-approved-recipe" in codes


def test_insufficient_approval_roles_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    # Only 1 approval by bob
    single_approval = [
        {
            "approval_id": "app-1",
            "approver_id": "bob",
            "role": "automation_engineer",
            "decision": "approved",
        }
    ]
    snapshot = _build_valid_snapshot(
        project,
        signer,
        created_by="alice",
        approvals=single_approval,
    )
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.insufficient-approvals" in codes


def test_unapproved_recipe_status_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    snapshot = _build_valid_snapshot(
        project,
        signer,
        recipe_status="DRAFT",
    )
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.recipe-not-approved" in codes


def test_missing_hardware_evidence_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    signer = PlatformSigner.generate(key_id="test-platform-key")
    # Omit safety_review
    ev_records = [
        {
            "evidence_id": "ev-sim-1",
            "kind": "simulation",
            "cell_id": CELL_ID,
            "subject": {"cell_id": CELL_ID},
            "artifact_sha256": "1" * 64,
            "issuer": "ci_pipeline",
        },
        {
            "evidence_id": "ev-calib-1",
            "kind": "calibration",
            "cell_id": CELL_ID,
            "subject": {"cell_id": CELL_ID},
            "artifact_sha256": "2" * 64,
            "issuer": "calibrator",
        },
        {
            "evidence_id": "ev-comm-1",
            "kind": "commissioning",
            "cell_id": CELL_ID,
            "subject": {"cell_id": CELL_ID},
            "artifact_sha256": "3" * 64,
            "issuer": "field_eng",
        },
    ]
    snapshot = _build_valid_snapshot(project, signer, evidence_records=ev_records)
    public_keys = {"test-platform-key": signer.public_key_raw_b64()}

    report = compile_project(
        project,
        project / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.PRODUCTION,
        source_revision=SOURCE_REVISION,
        evidence_snapshot=snapshot,
        platform_public_keys=public_keys,
    )
    assert report.valid is False
    codes = {finding.code for finding in report.findings}
    assert "compiler.evidence.missing-hardware-evidence" in codes
