"""FastAPI application factory and combined routing."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from cellforge_platform.api.artifacts import router as artifacts_router
from cellforge_platform.api.bundles import router as bundles_router
from cellforge_platform.api.components import router as components_router
from cellforge_platform.api.evidence import router as evidence_router
from cellforge_platform.api.health import router as health_router
from cellforge_platform.api.projects import router as projects_router
from cellforge_platform.api.recipes import router as recipes_router
from cellforge_platform.api.resolution import router as resolution_router
from cellforge_platform.api.sync import router as sync_router
from cellforge_platform.auth.signing import PlatformSigner
from cellforge_platform.config import PlatformSettings
from cellforge_platform.database.engine import DatabaseEngine
from cellforge_platform.database.migrations import DatabaseManager
from cellforge_platform.database.repository import (
    ArtifactRepository,
    AuditRepository,
    BundleRepository,
    ComponentRepository,
    EvidenceRepository,
    ProductionSyncRepository,
    ProjectRepository,
    RecipeApprovalRepository,
    RecipeRepository,
)
from cellforge_platform.storage.base import ArtifactStore
from cellforge_platform.storage.filesystem import FilesystemArtifactStore
from cellforge_platform.storage.s3 import S3ArtifactStore


def create_platform_app(
    settings: PlatformSettings | None = None,
    platform_signer: PlatformSigner | None = None,
) -> FastAPI:
    """Create and configure the CellForge platform service FastAPI application."""
    cfg = settings or PlatformSettings.from_env()
    signer = platform_signer or PlatformSigner.generate(key_id="platform-default-key")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        # Initialize storage
        storage: ArtifactStore
        if cfg.storage_backend == "s3":
            storage = S3ArtifactStore(
                bucket_name=cfg.s3_bucket,
                prefix="artifacts/sha256",
            )
        else:
            storage = FilesystemArtifactStore(cfg.storage_root)

        # Initialize database and run migrations
        engine = DatabaseEngine(cfg.database_url)
        with engine.connect() as conn:
            mgr = DatabaseManager(conn)
            mgr.migrate_up()

            app.state.settings = cfg
            app.state.storage = storage
            app.state.db_engine = engine
            app.state.db_conn = conn
            app.state.component_repo = ComponentRepository(conn)
            app.state.project_repo = ProjectRepository(conn)
            app.state.recipe_repo = RecipeRepository(conn)
            app.state.recipe_approval_repo = RecipeApprovalRepository(conn)
            app.state.bundle_repo = BundleRepository(conn)
            app.state.artifact_repo = ArtifactRepository(conn)
            app.state.audit_repo = AuditRepository(conn)
            app.state.evidence_repo = EvidenceRepository(conn)
            app.state.production_sync_repo = ProductionSyncRepository(conn)
            app.state.platform_signer = signer

            yield

    app = FastAPI(
        title="CellForge Platform API",
        description=(
            "Central authenticated engineering metadata and content-addressed artifact services"
        ),
        lifespan=lifespan,
    )

    # Global state fallback for tests when lifespan isn't run
    engine = DatabaseEngine(cfg.database_url)
    with engine.connect() as conn:
        mgr = DatabaseManager(conn)
        mgr.migrate_up()
        fallback_storage: ArtifactStore
        if cfg.storage_backend == "s3":
            fallback_storage = S3ArtifactStore(bucket_name=cfg.s3_bucket)
        else:
            fallback_storage = FilesystemArtifactStore(cfg.storage_root)

        app.state.settings = cfg
        app.state.storage = fallback_storage
        app.state.db_engine = engine
        app.state.db_conn = conn
        app.state.component_repo = ComponentRepository(conn)
        app.state.project_repo = ProjectRepository(conn)
        app.state.recipe_repo = RecipeRepository(conn)
        app.state.recipe_approval_repo = RecipeApprovalRepository(conn)
        app.state.bundle_repo = BundleRepository(conn)
        app.state.artifact_repo = ArtifactRepository(conn)
        app.state.audit_repo = AuditRepository(conn)
        app.state.evidence_repo = EvidenceRepository(conn)
        app.state.production_sync_repo = ProductionSyncRepository(conn)
        app.state.platform_signer = signer

    # Register routers
    app.include_router(health_router)
    app.include_router(components_router, prefix=cfg.api_prefix)
    app.include_router(projects_router, prefix=cfg.api_prefix)
    app.include_router(recipes_router, prefix=cfg.api_prefix)
    app.include_router(bundles_router, prefix=cfg.api_prefix)
    app.include_router(artifacts_router, prefix=cfg.api_prefix)
    app.include_router(resolution_router, prefix=cfg.api_prefix)
    app.include_router(evidence_router, prefix=cfg.api_prefix)
    app.include_router(sync_router, prefix=cfg.api_prefix)

    return app
