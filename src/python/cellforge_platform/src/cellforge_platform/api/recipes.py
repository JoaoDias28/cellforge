"""Recipe versioning API endpoints."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from cellforge_platform.auth.dependencies import get_current_auth, require_role
from cellforge_platform.auth.models import AuthContext, CellForgeRole
from cellforge_platform.database.repository import (
    ConflictError,
    NotFoundError,
    RecipeApprovalRepository,
    RecipeRepository,
)
from cellforge_platform.models import (
    RecipeApprovalRequest,
    RecipeApprovalSummary,
    RecipePublishRequest,
    RecipeRecord,
)

router = APIRouter(prefix="/projects/{cell_id}/recipes", tags=["Recipes"])


@router.post(
    "",
    response_model=RecipeRecord,
    status_code=201,
    dependencies=[
        Depends(
            require_role(
                CellForgeRole.PROCESS_ENGINEER,
                CellForgeRole.AUTOMATION_ENGINEER,
                CellForgeRole.ADMINISTRATOR,
            )
        )
    ],
)
async def publish_recipe(
    cell_id: str,
    req: RecipePublishRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> RecipeRecord:
    """Publish a recipe version for a project."""
    repo: RecipeRepository = request.app.state.recipe_repo
    canonical_json = json.dumps(req.recipe_data, sort_keys=True, separators=(",", ":"))
    recipe_sha = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    try:
        record = repo.publish(
            project_id=cell_id,
            recipe_id=req.recipe_id,
            version=req.version,
            name=req.name,
            status=req.status,
            schema_sha256=req.schema_sha256,
            recipe_sha256=recipe_sha,
            recipe_json=canonical_json,
            created_by=auth.user_id,
        )
        # Audit log
        audit = request.app.state.audit_repo
        audit.record(
            event_type="recipe.published",
            entity_type="recipe",
            entity_id=f"{cell_id}/{req.recipe_id}/v{req.version}",
            details={"status": req.status, "recipe_sha256": recipe_sha},
            performed_by=auth.user_id,
        )
        return record
    except ConflictError as err:
        raise HTTPException(
            status_code=409,
            detail={"code": "conflict.recipe_already_exists", "message": str(err)},
        ) from err


@router.get("", response_model=list[RecipeRecord])
async def list_recipes(
    cell_id: str,
    request: Request,
    recipe_id: str | None = Query(None),
) -> list[RecipeRecord]:
    """List recipes for a project."""
    repo: RecipeRepository = request.app.state.recipe_repo
    return repo.list(project_id=cell_id, recipe_id=recipe_id)


@router.get("/{recipe_id}/{version}", response_model=RecipeRecord)
async def get_recipe(
    cell_id: str,
    recipe_id: str,
    version: int,
    request: Request,
) -> RecipeRecord:
    """Get a specific recipe version."""
    repo: RecipeRepository = request.app.state.recipe_repo
    record = repo.get(cell_id, recipe_id, version)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "recipe.not_found",
                "message": (
                    f"Recipe '{recipe_id}' version {version} not found in project '{cell_id}'."
                ),
            },
        )
    return record


@router.post(
    "/{recipe_id}/{version}/approve",
    response_model=RecipeApprovalSummary,
    dependencies=[
        Depends(
            require_role(
                CellForgeRole.PROCESS_ENGINEER,
                CellForgeRole.AUTOMATION_ENGINEER,
                CellForgeRole.ADMINISTRATOR,
            )
        )
    ],
)
async def approve_recipe(
    cell_id: str,
    recipe_id: str,
    version: int,
    req: RecipeApprovalRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> RecipeApprovalSummary:
    """Submit a role approval or rejection for a recipe version."""
    approval_repo: RecipeApprovalRepository = request.app.state.recipe_approval_repo
    audit = request.app.state.audit_repo

    # Verify that user has the specified approval role
    user_roles = {r.value if isinstance(r, CellForgeRole) else str(r) for r in auth.roles}
    if req.role not in user_roles and CellForgeRole.ADMINISTRATOR.value not in user_roles:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "auth.role_mismatch",
                "message": f"User does not hold the requested approval role '{req.role}'.",
            },
        )

    try:
        approval_rec, summary = approval_repo.record_approval(
            project_id=cell_id,
            recipe_id=recipe_id,
            version=version,
            role=req.role,
            approver_id=auth.user_id,
            decision=req.decision,
            comments=req.comments,
            signature=req.signature,
        )
        audit.record(
            event_type=f"recipe.approval.{req.decision}",
            entity_type="recipe_approval",
            entity_id=f"{cell_id}/{recipe_id}/v{version}/{approval_rec.id}",
            details={
                "role": req.role,
                "decision": req.decision,
                "is_approved_for_production": summary.is_approved_for_production,
            },
            performed_by=auth.user_id,
        )
        return summary
    except NotFoundError as err:
        raise HTTPException(
            status_code=404,
            detail={"code": "recipe.not_found", "message": str(err)},
        ) from err


@router.get(
    "/{recipe_id}/{version}/approvals",
    response_model=RecipeApprovalSummary,
)
async def get_recipe_approvals(
    cell_id: str,
    recipe_id: str,
    version: int,
    request: Request,
) -> RecipeApprovalSummary:
    """Get the full approval status and history for a recipe version."""
    approval_repo: RecipeApprovalRepository = request.app.state.recipe_approval_repo
    try:
        return approval_repo.get_approval_summary(cell_id, recipe_id, version)
    except NotFoundError as err:
        raise HTTPException(
            status_code=404,
            detail={"code": "recipe.not_found", "message": str(err)},
        ) from err
