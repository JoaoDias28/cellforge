"""Cell project metadata API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request

from cellforge_platform.auth.dependencies import get_current_auth, require_role
from cellforge_platform.auth.models import AuthContext, CellForgeRole
from cellforge_platform.database.repository import ProjectRepository
from cellforge_platform.models import ProjectRecord, ProjectRegisterRequest

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectRecord,
    status_code=201,
    dependencies=[
        Depends(require_role(CellForgeRole.AUTOMATION_ENGINEER, CellForgeRole.ADMINISTRATOR))
    ],
)
async def register_project(
    req: ProjectRegisterRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> ProjectRecord:
    """Register or update cell project metadata and source revisions."""
    repo: ProjectRepository = request.app.state.project_repo
    record = repo.register(
        cell_id=req.cell_id,
        name=req.name,
        description=req.description,
        git_repo=req.git_repo,
        git_revision=req.git_revision,
        cell_yaml_sha256=req.cell_yaml_sha256,
        scene_sha256=req.scene_sha256,
        metadata_json=json.dumps(req.metadata),
        created_by=auth.user_id,
    )
    # Audit log
    audit = request.app.state.audit_repo
    audit.record(
        event_type="project.registered",
        entity_type="project",
        entity_id=req.cell_id,
        details={"name": req.name, "git_revision": req.git_revision},
        performed_by=auth.user_id,
    )
    return record


@router.get("", response_model=list[ProjectRecord])
async def list_projects(request: Request) -> list[ProjectRecord]:
    """List registered cell projects."""
    repo: ProjectRepository = request.app.state.project_repo
    return repo.list()


@router.get("/{cell_id}", response_model=ProjectRecord)
async def get_project(cell_id: str, request: Request) -> ProjectRecord:
    """Get project details for a specific cell ID."""
    repo: ProjectRepository = request.app.state.project_repo
    record = repo.get(cell_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project.not_found",
                "message": f"Project with cell_id '{cell_id}' was not found.",
            },
        )
    return record
