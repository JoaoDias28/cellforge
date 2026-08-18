"""Component registry API endpoints."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from cellforge_platform.auth.dependencies import get_current_auth, require_role
from cellforge_platform.auth.models import AuthContext, CellForgeRole
from cellforge_platform.database.repository import (
    ComponentRepository,
    ConflictError,
)
from cellforge_platform.models import (
    ComponentDetail,
    ComponentPublishRequest,
    ComponentSummary,
    DeprecateComponentRequest,
)
from cellforge_platform.storage.base import ArtifactStore, BlobNotFoundError

router = APIRouter(prefix="/components", tags=["Components"])


@router.post(
    "/publish",
    response_model=ComponentDetail,
    status_code=201,
    dependencies=[
        Depends(require_role(CellForgeRole.AUTOMATION_ENGINEER, CellForgeRole.ADMINISTRATOR))
    ],
)
async def publish_component(
    req: ComponentPublishRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> ComponentDetail:
    """Publish a validated component package to the platform registry."""
    manifest = req.manifest
    comp_info = manifest.get("component")
    if isinstance(comp_info, dict):
        comp_type = comp_info.get("id") or comp_info.get("component")
        version = comp_info.get("version") or manifest.get("version")
        kind = comp_info.get("kind") or manifest.get("kind")
        name = comp_info.get("name") or manifest.get("name") or comp_type
        support = comp_info.get("support_level") or manifest.get("support_level") or "simulated"
        license_info = comp_info.get("license") or manifest.get("license")
    else:
        comp_type = comp_info
        version = manifest.get("version")
        kind = manifest.get("kind")
        name = manifest.get("name") or comp_type
        support = manifest.get("support_level") or "simulated"
        license_info = manifest.get("license")

    if not comp_type or not version or not kind:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "component.manifest.invalid",
                "message": "Manifest must contain component identifier, version, and kind.",
            },
        )

    license_str = (
        json.dumps(license_info)
        if isinstance(license_info, dict)
        else (str(license_info) if license_info else None)
    )

    # Check if artifact blob exists in storage if digest provided
    store: ArtifactStore = request.app.state.storage
    if req.package_artifact_digest is not None:
        if not store.exists(req.package_artifact_digest):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "component.artifact.missing",
                    "message": (
                        f"Referenced package artifact blob '{req.package_artifact_digest}' "
                        f"does not exist in storage."
                    ),
                },
            )

    canonical_manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest_sha = hashlib.sha256(canonical_manifest_json.encode("utf-8")).hexdigest()

    repo: ComponentRepository = request.app.state.component_repo
    try:
        detail = repo.publish(
            component_type=str(comp_type),
            version=str(version),
            name=str(name),
            kind=str(kind),
            support_level=str(support),
            license_str=license_str,
            manifest_json=canonical_manifest_json,
            manifest_sha256=manifest_sha,
            package_blob_digest=req.package_artifact_digest,
            git_repo=req.git_repo,
            git_commit=req.git_commit,
            created_by=auth.user_id,
        )
        # Audit log
        audit = request.app.state.audit_repo
        audit.record(
            event_type="component.published",
            entity_type="component",
            entity_id=f"{comp_type}@{version}",
            details={"manifest_sha256": manifest_sha, "blob_digest": req.package_artifact_digest},
            performed_by=auth.user_id,
        )
        return detail
    except ConflictError as err:
        raise HTTPException(
            status_code=409,
            detail={"code": "conflict.component_already_exists", "message": str(err)},
        ) from err


@router.get("", response_model=list[ComponentSummary])
async def list_components(
    request: Request,
    kind: str | None = Query(None),
    support_level: str | None = Query(None),
    query: str | None = Query(None),
    include_deprecated: bool = Query(True),
) -> list[ComponentSummary]:
    """Search and list registered component packages."""
    repo: ComponentRepository = request.app.state.component_repo
    return repo.list(
        kind=kind,
        support_level=support_level,
        query=query,
        include_deprecated=include_deprecated,
    )


@router.get("/{component_type:path}/{version}/download")
async def download_component_artifact(
    component_type: str,
    version: str,
    request: Request,
) -> Response:
    """Download the content-addressed package artifact blob for a component version."""
    repo: ComponentRepository = request.app.state.component_repo
    detail = repo.get(component_type, version)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "component.not_found",
                "message": f"Component '{component_type}' version '{version}' not found.",
            },
        )

    digest = detail.summary.package_blob_digest
    if not digest:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "component.artifact.not_bundled",
                "message": "No binary package artifact is registered for this component.",
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
                "message": f"Blob {digest} not found in storage.",
            },
        ) from err

    filename = f"{component_type.replace('.', '_')}-{version}.cfpkg"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Digest": f"sha-256=:{digest}:",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post(
    "/{component_type:path}/{version}/deprecate",
    response_model=ComponentSummary,
    dependencies=[Depends(require_role(CellForgeRole.MAINTAINER, CellForgeRole.ADMINISTRATOR))],
)
async def deprecate_component(
    component_type: str,
    version: str,
    req: DeprecateComponentRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> ComponentSummary:
    """Deprecate a component version."""
    repo: ComponentRepository = request.app.state.component_repo
    summary = repo.deprecate(
        component_type,
        version,
        req.reason,
        deprecated_by=auth.user_id,
    )
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "component.not_found",
                "message": f"Component '{component_type}' version '{version}' was not found.",
            },
        )
    # Audit log
    audit = request.app.state.audit_repo
    audit.record(
        event_type="component.deprecated",
        entity_type="component",
        entity_id=f"{component_type}@{version}",
        details={"reason": req.reason},
        performed_by=auth.user_id,
    )
    return summary


@router.get("/{component_type:path}/{version}", response_model=ComponentDetail)
async def get_component(
    component_type: str,
    version: str,
    request: Request,
) -> ComponentDetail:
    """Retrieve full details and manifest for a specific component version."""
    repo: ComponentRepository = request.app.state.component_repo
    detail = repo.get(component_type, version)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "component.not_found",
                "message": f"Component '{component_type}' version '{version}' was not found.",
            },
        )
    return detail
