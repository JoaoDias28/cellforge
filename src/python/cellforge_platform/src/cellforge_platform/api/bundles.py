"""Release bundle registry API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from cellforge_platform.auth.dependencies import get_current_auth, require_role
from cellforge_platform.auth.models import AuthContext, CellForgeRole
from cellforge_platform.database.repository import BundleRepository, ConflictError
from cellforge_platform.models import BundlePublishRequest, BundleRecord
from cellforge_platform.storage.base import ArtifactStore, BlobNotFoundError

router = APIRouter(prefix="/bundles", tags=["Bundles"])


@router.post(
    "/publish",
    response_model=BundleRecord,
    status_code=201,
    dependencies=[
        Depends(require_role(CellForgeRole.AUTOMATION_ENGINEER, CellForgeRole.ADMINISTRATOR))
    ],
)
async def publish_bundle(
    req: BundlePublishRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> BundleRecord:
    """Register and index an immutable signed release bundle."""
    repo: BundleRepository = request.app.state.bundle_repo
    manifest_json = json.dumps(req.manifest, sort_keys=True, separators=(",", ":"))
    sig_json = json.dumps(req.signature, sort_keys=True, separators=(",", ":"))
    key_id = req.signature.get("key_id")

    # Check if artifact blob exists in storage if digest provided
    store: ArtifactStore = request.app.state.storage
    if req.bundle_artifact_digest is not None:
        if not store.exists(req.bundle_artifact_digest):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "bundle.artifact.missing",
                    "message": (
                        f"Referenced bundle artifact blob '{req.bundle_artifact_digest}' "
                        f"does not exist in storage."
                    ),
                },
            )

    try:
        record = repo.publish(
            bundle_id=req.bundle_id,
            target_profile=req.target_profile,
            execution_mode=req.execution_mode,
            source_revision=req.source_revision,
            manifest_json=manifest_json,
            signature_json=sig_json,
            project_id=req.project_id,
            key_id=str(key_id) if key_id else None,
            blob_digest=req.bundle_artifact_digest,
            created_by=auth.user_id,
        )
        # Audit log
        audit = request.app.state.audit_repo
        audit.record(
            event_type="bundle.published",
            entity_type="bundle",
            entity_id=req.bundle_id,
            details={
                "target_profile": req.target_profile,
                "execution_mode": req.execution_mode,
                "source_revision": req.source_revision,
                "blob_digest": req.bundle_artifact_digest,
            },
            performed_by=auth.user_id,
        )
        return record
    except ConflictError as err:
        raise HTTPException(
            status_code=409,
            detail={"code": "conflict.bundle_already_exists", "message": str(err)},
        ) from err


@router.get("", response_model=list[BundleRecord])
async def list_bundles(
    request: Request,
    target_profile: str | None = Query(None),
    execution_mode: str | None = Query(None),
) -> list[BundleRecord]:
    """Search and list registered release bundles."""
    repo: BundleRepository = request.app.state.bundle_repo
    return repo.list(target_profile=target_profile, execution_mode=execution_mode)


@router.get("/{bundle_id}", response_model=BundleRecord)
async def get_bundle(bundle_id: str, request: Request) -> BundleRecord:
    """Get release bundle metadata by bundle ID."""
    repo: BundleRepository = request.app.state.bundle_repo
    record = repo.get(bundle_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "bundle.not_found", "message": f"Bundle '{bundle_id}' was not found."},
        )
    return record


@router.get("/{bundle_id}/download")
async def download_bundle_artifact(bundle_id: str, request: Request) -> Response:
    """Download binary release bundle archive."""
    repo: BundleRepository = request.app.state.bundle_repo
    record = repo.get(bundle_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "bundle.not_found", "message": f"Bundle '{bundle_id}' was not found."},
        )

    digest = record.blob_digest
    if not digest:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "bundle.artifact.not_uploaded",
                "message": "No binary archive blob is registered for this bundle.",
            },
        )

    store: ArtifactStore = request.app.state.storage
    try:
        data = store.get(digest)
    except BlobNotFoundError as err:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "artifact.blob_missing",
                "message": f"Bundle blob {digest} not found in storage.",
            },
        ) from err

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Digest": f"sha-256=:{digest}:",
            "Content-Disposition": f'attachment; filename="bundle-{bundle_id[:16]}.cfbundle"',
        },
    )
