"""Server-side cell dependency resolution API endpoint."""

from __future__ import annotations

import yaml
from cellforge_domain import CellProject, ExecutionMode
from cellforge_domain.models import ComponentType
from cellforge_domain.registry import FilesystemComponentRegistry, RegisteredComponentPackage
from cellforge_domain.resolver import resolve_cell
from fastapi import APIRouter, HTTPException, Request

from cellforge_platform.database.repository import ComponentRepository
from cellforge_platform.models import ResolutionRequest, ResolutionResponse

router = APIRouter(tags=["Resolution"])


@router.post("/resolve", response_model=ResolutionResponse)
async def resolve_project_dependencies(
    req: ResolutionRequest,
    request: Request,
) -> ResolutionResponse:
    """Resolve component dependencies in a cell.yaml against platform registry."""
    try:
        cell_dict = yaml.safe_load(req.cell_yaml)
        if not isinstance(cell_dict, dict):
            raise ValueError("cell.yaml root must be a mapping.")
        project = CellProject.model_validate(cell_dict)
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "cell_yaml.invalid", "message": f"Failed to parse cell.yaml: {error}"},
        ) from error

    try:
        exec_mode = ExecutionMode(req.mode)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"code": "mode.invalid", "message": f"Invalid execution mode '{req.mode}'."},
        ) from None

    repo: ComponentRepository = request.app.state.component_repo
    components = repo.list(include_deprecated=req.allow_deprecated)

    # Build memory registry for resolver
    packages: dict[tuple[str, str], RegisteredComponentPackage] = {}
    for summary in components:
        detail = repo.get(summary.component, summary.version)
        if detail is not None:
            try:
                manifest_obj = ComponentType.model_validate(detail.manifest)
                packages[(summary.component, summary.version)] = RegisteredComponentPackage(
                    manifest=manifest_obj,
                    source_path=detail.summary.package_blob_digest
                    or f"{summary.component}/{summary.version}",  # type: ignore[arg-type]
                    package_path=f"{summary.component}/{summary.version}",
                )
            except Exception:
                continue

    registry = FilesystemComponentRegistry(
        root=request.app.state.settings.storage_root,
        packages=packages,
        findings=(),
    )

    report = resolve_cell(project, registry, mode=exec_mode)

    resolved_list = [
        {
            "instance_id": c.instance_id,
            "component": c.component,
            "version": c.version,
            "package_path": c.package_path,
        }
        for c in report.components
    ]

    findings_list = [
        {
            "code": f.code,
            "severity": f.severity.value,
            "path": f.path,
            "message": f.message,
        }
        for f in report.findings
    ]

    return ResolutionResponse(
        valid=report.valid,
        mode=report.mode.value,
        resolved_components=resolved_list,
        findings=findings_list,
    )
