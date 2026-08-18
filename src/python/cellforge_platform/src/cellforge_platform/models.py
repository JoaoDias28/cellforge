"""Pydantic API request and response models for the CellForge platform service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComponentPublishRequest(BaseModel):
    """Payload for publishing a component package to the registry."""

    manifest: dict[str, Any] = Field(..., description="Parsed component.yaml manifest")
    package_artifact_digest: str | None = Field(
        None, description="SHA-256 digest of the full component zip/tar package artifact blob"
    )
    git_repo: str | None = Field(None, description="Source Git repository URL")
    git_commit: str | None = Field(None, description="Source Git 40-hex commit revision")


class ComponentSummary(BaseModel):
    """Summary representation of a registered component version."""

    id: str
    component: str
    version: str
    name: str
    kind: str
    support_level: str
    license: str | None = None
    is_deprecated: bool = False
    deprecation_reason: str | None = None
    manifest_sha256: str
    package_blob_digest: str | None = None
    created_at: str
    created_by: str | None = None


class ComponentDetail(BaseModel):
    """Full detail of a registered component version including manifest."""

    summary: ComponentSummary
    manifest: dict[str, Any]
    git_repo: str | None = None
    git_commit: str | None = None


class DeprecateComponentRequest(BaseModel):
    """Request to deprecate a specific component version."""

    reason: str = Field(
        ..., min_length=3, description="Reason for deprecating this component version"
    )


class ProjectRegisterRequest(BaseModel):
    """Payload for indexing a cell project."""

    cell_id: str
    name: str
    description: str | None = None
    git_repo: str | None = None
    git_revision: str | None = None
    cell_yaml_sha256: str
    scene_sha256: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectRecord(BaseModel):
    """Registered project record."""

    id: str
    cell_id: str
    name: str
    description: str | None = None
    git_repo: str | None = None
    git_revision: str | None = None
    cell_yaml_sha256: str
    scene_sha256: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    created_by: str | None = None


class RecipePublishRequest(BaseModel):
    """Payload for publishing a recipe version."""

    project_id: str
    recipe_id: str
    version: int
    name: str
    status: str = "draft"
    schema_sha256: str
    recipe_data: dict[str, Any]


class RecipeRecord(BaseModel):
    """Registered recipe record."""

    id: str
    project_id: str
    recipe_id: str
    version: int
    name: str
    status: str
    schema_sha256: str
    recipe_sha256: str
    recipe_data: dict[str, Any]
    created_at: str
    created_by: str | None = None


class BundlePublishRequest(BaseModel):
    """Payload for registering a signed release bundle."""

    bundle_id: str
    project_id: str | None = None
    target_profile: str
    execution_mode: str
    source_revision: str
    manifest: dict[str, Any]
    signature: dict[str, Any]
    checksums_txt: str
    bundle_artifact_digest: str | None = None


class BundleRecord(BaseModel):
    """Registered release bundle record."""

    id: str
    bundle_id: str
    project_id: str | None = None
    target_profile: str
    execution_mode: str
    source_revision: str
    manifest: dict[str, Any]
    signature: dict[str, Any]
    key_id: str | None = None
    blob_digest: str | None = None
    created_at: str
    created_by: str | None = None


class ArtifactUploadResponse(BaseModel):
    """Response returned upon successful content-addressed blob upload."""

    digest: str
    size_bytes: int
    media_type: str
    created_at: str


class ResolutionRequest(BaseModel):
    """Request to resolve component dependencies in a cell.yaml against platform registry."""

    cell_yaml: str
    mode: str = "simulation"
    allow_deprecated: bool = False


class ResolutionResponse(BaseModel):
    """Result of dependency resolution against the platform registry."""

    valid: bool
    mode: str
    resolved_components: list[dict[str, Any]]
    findings: list[dict[str, Any]]


class HealthResponse(BaseModel):
    """Platform health check response."""

    status: str
    service: str
    version: str
    environment: str
    database: str
    storage: str
