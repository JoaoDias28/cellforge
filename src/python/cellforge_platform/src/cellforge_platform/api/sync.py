"""Production jobs, traces, results, and attachments synchronization endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from cellforge_platform.auth.dependencies import get_current_auth, require_role
from cellforge_platform.auth.models import AuthContext, CellForgeRole
from cellforge_platform.database.repository import ProductionSyncRepository
from cellforge_platform.models import (
    ProductionAttachmentRecord,
    ProductionJobRecord,
    ProductionResultRecord,
    ProductionTraceRecord,
    SyncBatchRequest,
    SyncBatchResponse,
)

router = APIRouter(tags=["Production Sync"])


@router.post(
    "/sync/batch",
    response_model=SyncBatchResponse,
    status_code=200,
    dependencies=[
        Depends(
            require_role(
                CellForgeRole.OPERATOR,
                CellForgeRole.AUTOMATION_ENGINEER,
                CellForgeRole.PROCESS_ENGINEER,
                CellForgeRole.MAINTAINER,
                CellForgeRole.ADMINISTRATOR,
            )
        )
    ],
)
async def sync_batch(
    req: SyncBatchRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
) -> SyncBatchResponse:
    """Ingest a batch of locally recorded production items idempotently."""
    repo: ProductionSyncRepository = request.app.state.production_sync_repo
    return repo.sync_batch(
        cell_id=req.cell_id,
        jobs=req.jobs,
        traces=req.traces,
        results=req.results,
        attachments=req.attachments,
    )


@router.get("/production/jobs", response_model=list[ProductionJobRecord])
async def list_production_jobs(
    request: Request,
    cell_id: str | None = Query(None),
    job_id: str | None = Query(None),
) -> list[ProductionJobRecord]:
    """Query synchronized production job records."""
    repo: ProductionSyncRepository = request.app.state.production_sync_repo
    return repo.list_jobs(cell_id=cell_id, job_id=job_id)


@router.get("/production/traces", response_model=list[ProductionTraceRecord])
async def list_production_traces(
    request: Request,
    trace_id: str | None = Query(None),
    cell_id: str | None = Query(None),
) -> list[ProductionTraceRecord]:
    """Query synchronized production trace events in monotonic sequence."""
    repo: ProductionSyncRepository = request.app.state.production_sync_repo
    return repo.list_traces(trace_id=trace_id, cell_id=cell_id)


@router.get("/production/results", response_model=list[ProductionResultRecord])
async def list_production_results(
    request: Request,
    cell_id: str | None = Query(None),
    trace_id: str | None = Query(None),
) -> list[ProductionResultRecord]:
    """Query synchronized production job results."""
    repo: ProductionSyncRepository = request.app.state.production_sync_repo
    return repo.list_results(cell_id=cell_id, trace_id=trace_id)


@router.get("/production/attachments", response_model=list[ProductionAttachmentRecord])
async def list_production_attachments(
    request: Request,
    cell_id: str | None = Query(None),
    trace_id: str | None = Query(None),
) -> list[ProductionAttachmentRecord]:
    """Query synchronized production attachment metadata."""
    repo: ProductionSyncRepository = request.app.state.production_sync_repo
    return repo.list_attachments(cell_id=cell_id, trace_id=trace_id)
