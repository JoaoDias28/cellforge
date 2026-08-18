"""Evidence registry, query, and signed snapshot generation API endpoints."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from cellforge_platform.auth.dependencies import get_current_auth, require_role
from cellforge_platform.auth.models import AuthContext, CellForgeRole
from cellforge_platform.auth.signing import PlatformSigner
from cellforge_platform.database.repository import (
    ConflictError,
    EvidenceRepository,
    RecipeApprovalRepository,
    RecipeRepository,
)
from cellforge_platform.models import (
    EvidenceRecord,
    EvidenceRecordCreate,
    EvidenceSnapshot,
)

router = APIRouter(prefix="/evidence", tags=["Evidence"])
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_VALID_KINDS = {"simulation", "calibration", "commissioning", "production", "safety_review"}


class CreateSnapshotRequest(BaseModel):
    """Payload for generating a signed evidence snapshot for a cell."""

    cell_id: str
    valid_until: str | None = Field(
        None, description="Optional ISO timestamp for snapshot expiration"
    )
    key_id: str | None = Field(None, description="Optional key ID override")


@router.post(
    "",
    response_model=EvidenceRecord,
    status_code=201,
    dependencies=[
        Depends(
            require_role(
                CellForgeRole.AUTOMATION_ENGINEER,
                CellForgeRole.PROCESS_ENGINEER,
                CellForgeRole.MAINTAINER,
                CellForgeRole.ADMINISTRATOR,
            )
        )
    ],
)
async def create_evidence(
    req: EvidenceRecordCreate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> EvidenceRecord:
    """Register an immutable, content-addressed evidence record."""
    if req.kind not in _VALID_KINDS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "evidence.invalid_kind",
                "message": f"Invalid evidence kind '{req.kind}'. Expected one of {_VALID_KINDS}.",
            },
        )
    if not _SHA256_HEX.fullmatch(req.artifact_sha256.lower().strip()):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "evidence.invalid_digest",
                "message": (
                    "artifact_sha256 must be a 64-character lowercase hexadecimal SHA-256 digest."
                ),
            },
        )

    # Verify that the artifact blob is stored in the artifact store
    storage = request.app.state.storage
    if not storage.exists(req.artifact_sha256.lower().strip()):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "evidence.artifact_not_found",
                "message": (
                    f"Evidence artifact blob with digest '{req.artifact_sha256}' was not "
                    f"found in the artifact store. Please upload the artifact first."
                ),
            },
        )

    repo: EvidenceRepository = request.app.state.evidence_repo
    audit = request.app.state.audit_repo

    try:
        record = repo.create(req, created_by=auth.user_id)
        audit.record(
            event_type="evidence.registered",
            entity_type="evidence",
            entity_id=record.id,
            details={
                "kind": record.kind,
                "cell_id": record.cell_id,
                "artifact_sha256": record.artifact_sha256,
            },
            performed_by=auth.user_id,
        )
        return record
    except ConflictError as err:
        raise HTTPException(
            status_code=409,
            detail={"code": "conflict.evidence_already_exists", "message": str(err)},
        ) from err


@router.get("", response_model=list[EvidenceRecord])
async def list_evidence(
    request: Request,
    cell_id: str | None = Query(None),
    kind: str | None = Query(None),
    artifact_sha256: str | None = Query(None),
) -> list[EvidenceRecord]:
    """Query registered evidence records."""
    repo: EvidenceRepository = request.app.state.evidence_repo
    return repo.list(cell_id=cell_id, kind=kind, artifact_sha256=artifact_sha256)


@router.get("/{evidence_id}", response_model=EvidenceRecord)
async def get_evidence(
    evidence_id: str,
    request: Request,
) -> EvidenceRecord:
    """Get an evidence record by ID."""
    repo: EvidenceRepository = request.app.state.evidence_repo
    record = repo.get(evidence_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "evidence.not_found",
                "message": f"Evidence record '{evidence_id}' not found.",
            },
        )
    return record


@router.post(
    "/snapshots",
    response_model=EvidenceSnapshot,
    status_code=201,
    dependencies=[
        Depends(
            require_role(
                CellForgeRole.AUTOMATION_ENGINEER,
                CellForgeRole.PROCESS_ENGINEER,
                CellForgeRole.ADMINISTRATOR,
            )
        )
    ],
)
async def generate_evidence_snapshot(
    req: CreateSnapshotRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> EvidenceSnapshot:
    """Generate and sign an Ed25519 approval/evidence snapshot for a cell."""
    cell_id = req.cell_id
    recipe_repo: RecipeRepository = request.app.state.recipe_repo
    approval_repo: RecipeApprovalRepository = request.app.state.recipe_approval_repo
    evidence_repo: EvidenceRepository = request.app.state.evidence_repo
    signer: PlatformSigner = getattr(
        request.app.state, "platform_signer", PlatformSigner.generate(key_id="platform-default-key")
    )

    # 1. Collect all recipes and their approval summaries for cell_id
    all_recipes = recipe_repo.list(project_id=cell_id)
    recipe_summaries: list[dict[str, Any]] = []
    for r in all_recipes:
        summary = approval_repo.get_approval_summary(cell_id, r.recipe_id, r.version)
        recipe_summaries.append(
            {
                "recipe_id": summary.recipe_id,
                "version": summary.version,
                "name": summary.name,
                "status": summary.status,
                "recipe_sha256": summary.recipe_sha256,
                "created_by": summary.created_by,
                "approvals": [
                    {
                        "id": a.id,
                        "recipe_record_id": a.recipe_record_id,
                        "project_id": a.project_id,
                        "recipe_id": a.recipe_id,
                        "version": a.version,
                        "recipe_sha256": a.recipe_sha256,
                        "role": a.role,
                        "approver_id": a.approver_id,
                        "decision": a.decision,
                        "comments": a.comments,
                        "signature": a.signature,
                        "created_at": a.created_at,
                    }
                    for a in summary.approvals
                ],
                "is_approved_for_production": summary.is_approved_for_production,
            }
        )

    # 2. Collect all evidence records for cell_id
    evidence_records = evidence_repo.list(cell_id=cell_id)
    evidence_dicts = [
        {
            "schema_version": e.schema_version,
            "evidence_id": e.id,
            "kind": e.kind,
            "cell_id": e.cell_id,
            "subject": e.subject,
            "artifact_sha256": e.artifact_sha256,
            "issuer": e.issuer,
            "valid_until": e.valid_until,
            "signature": e.signature,
            "metadata": e.metadata,
            "created_at": e.created_at,
            "created_by": e.created_by,
        }
        for e in evidence_records
    ]

    snapshot_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    key_id = req.key_id or signer.key_id

    doc_to_sign: dict[str, Any] = {
        "schema_version": "0.1.0",
        "snapshot_id": snapshot_id,
        "cell_id": cell_id,
        "issued_at": now,
        "valid_until": req.valid_until,
        "key_id": key_id,
        "recipes": recipe_summaries,
        "evidence": evidence_dicts,
    }

    signature = signer.sign_document(doc_to_sign)

    snapshot = EvidenceSnapshot(
        schema_version="0.1.0",
        snapshot_id=snapshot_id,
        cell_id=cell_id,
        issued_at=now,
        valid_until=req.valid_until,
        key_id=key_id,
        recipes=recipe_summaries,
        evidence=evidence_dicts,
        signature=signature,
    )

    audit = request.app.state.audit_repo
    audit.record(
        event_type="evidence_snapshot.generated",
        entity_type="evidence_snapshot",
        entity_id=snapshot_id,
        details={
            "cell_id": cell_id,
            "key_id": key_id,
            "recipe_count": len(recipe_summaries),
            "evidence_count": len(evidence_dicts),
        },
        performed_by=auth.user_id,
    )

    return snapshot
