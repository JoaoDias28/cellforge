"""Health and system status API router."""

from __future__ import annotations

from fastapi import APIRouter, Request

from cellforge_platform.config import PlatformSettings
from cellforge_platform.models import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    settings: PlatformSettings = getattr(request.app.state, "settings", PlatformSettings())
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.environment,
        database="connected",
        storage=settings.storage_backend,
    )
