"""Content-addressed artifact blob upload and download API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from cellforge_platform.auth.dependencies import get_current_auth, require_authenticated
from cellforge_platform.auth.models import AuthContext
from cellforge_platform.database.repository import ArtifactRepository
from cellforge_platform.models import ArtifactUploadResponse
from cellforge_platform.storage.base import (
    ArtifactStore,
    BlobNotFoundError,
    DigestMismatchError,
)

router = APIRouter(prefix="/artifacts", tags=["Artifacts"])


@router.post(
    "/upload",
    response_model=ArtifactUploadResponse,
    status_code=201,
    dependencies=[Depends(require_authenticated)],
)
async def upload_artifact(
    request: Request,
    content_digest: str | None = Header(None),
    content_type: str | None = Header(None),
    auth: AuthContext = Depends(get_current_auth),
) -> ArtifactUploadResponse:
    """Upload a content-addressed binary artifact blob."""
    data = await request.body()
    if not data:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "artifact.empty_body",
                "message": "Uploaded artifact body cannot be empty.",
            },
        )

    expected_digest: str | None = None
    if content_digest is not None:
        # e.g., "sha-256=:digest:" or "sha256:digest" or plain digest
        clean = content_digest.strip()
        if clean.startswith("sha-256=:"):
            expected_digest = clean[9:].rstrip(":")
        elif clean.startswith("sha256:"):
            expected_digest = clean[7:]
        else:
            expected_digest = clean

    media = content_type or "application/octet-stream"
    store: ArtifactStore = request.app.state.storage
    try:
        digest = store.put(data, expected_digest=expected_digest, media_type=media)
    except DigestMismatchError as err:
        raise HTTPException(
            status_code=400,
            detail={"code": "artifact.digest_mismatch", "message": str(err)},
        ) from err

    size = len(data)
    repo: ArtifactRepository = request.app.state.artifact_repo
    repo.register(
        digest=digest,
        size_bytes=size,
        media_type=media,
        storage_path=f"sha256/{digest[:2]}/{digest}",
        created_by=auth.user_id,
    )

    return ArtifactUploadResponse(
        digest=digest,
        size_bytes=size,
        media_type=media,
        created_at=datetime.now(UTC).isoformat(),
    )


@router.get("/{digest}")
async def download_artifact(digest: str, request: Request) -> Response:
    """Download a content-addressed binary artifact blob by SHA-256 digest."""
    store: ArtifactStore = request.app.state.storage
    try:
        data = store.get(digest)
    except BlobNotFoundError as err:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "artifact.not_found",
                "message": f"Artifact blob '{digest}' not found.",
            },
        ) from err
    except DigestMismatchError as err:
        raise HTTPException(
            status_code=500,
            detail={"code": "artifact.corrupted", "message": str(err)},
        ) from err

    repo: ArtifactRepository = request.app.state.artifact_repo
    meta = repo.get(digest)
    media_type = (
        meta.get("media_type", "application/octet-stream") if meta else "application/octet-stream"
    )

    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Digest": f"sha-256=:{digest}:",
            "ETag": f'"{digest}"',
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


@router.head("/{digest}")
async def head_artifact(digest: str, request: Request) -> Response:
    """Check existence and size of a content-addressed blob."""
    store: ArtifactStore = request.app.state.storage
    if not store.exists(digest):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "artifact.not_found",
                "message": f"Artifact blob '{digest}' not found.",
            },
        )

    size = store.size(digest)
    return Response(
        status_code=200,
        headers={
            "Content-Digest": f"sha-256=:{digest}:",
            "Content-Length": str(size),
            "ETag": f'"{digest}"',
        },
    )
