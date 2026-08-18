"""Recipe versioning API endpoints."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from cellforge_platform.auth.dependencies import get_current_auth, require_role
from cellforge_platform.auth.models import AuthContext, CellForgeRole
from cellforge_platform.database.repository import ConflictError, RecipeRepository
from cellforge_platform.models import RecipePublishRequest, RecipeRecord

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
