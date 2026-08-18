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


class RecipeApprovalRequest(BaseModel):
    """Payload for submitting a role approval or rejection for a recipe version."""

    role: str = Field(
        ...,
        description=(
            "Approval role (e.g. process_engineer, automation_engineer, "
            "administrator, safety_engineer)"
        ),
    )

    decision: str = Field("approved", description="'approved', 'rejected', or 'revoked'")
    comments: str | None = Field(None, description="Optional reviewer notes or audit rationale")
    signature: str | None = Field(
        None, description="Optional detached Ed25519 cryptographic signature"
    )


class RecipeApprovalRecord(BaseModel):
    """Immutable audit record of a recipe approval."""

    id: str
    recipe_record_id: str
    project_id: str
    recipe_id: str
    version: int
    recipe_sha256: str
    role: str
    approver_id: str
    decision: str
    comments: str | None = None
    signature: str | None = None
    created_at: str


class RecipeApprovalSummary(BaseModel):
    """Comprehensive approval status and history for a recipe version."""

    recipe_id: str
    version: int
    name: str
    status: str
    recipe_sha256: str
    created_by: str | None = None
    approvals: list[RecipeApprovalRecord] = Field(default_factory=list)
    is_approved_for_production: bool = False


class EvidenceRecordCreate(BaseModel):
    """Payload for registering a content-addressed evidence record."""

    schema_version: str = "0.1.0"
    evidence_id: str = Field(..., description="UUID of the evidence record")
    kind: str = Field(
        ...,
        description="One of: simulation, calibration, commissioning, production, safety_review",
    )
    cell_id: str
    subject: dict[str, Any] = Field(..., description="Subject identity dict")
    artifact_sha256: str = Field(
        ..., description="SHA-256 digest of attached content-addressed artifact"
    )
    issuer: str
    valid_until: str | None = None
    signature: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(BaseModel):
    """Registered evidence record."""

    id: str
    schema_version: str
    kind: str
    cell_id: str
    subject: dict[str, Any]
    artifact_sha256: str
    issuer: str
    valid_until: str | None = None
    signature: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    created_by: str | None = None


class EvidenceSnapshot(BaseModel):
    """Cryptographically signed approval and evidence snapshot for offline compiler verification."""

    schema_version: str = "0.1.0"
    snapshot_id: str
    cell_id: str
    issued_at: str
    valid_until: str | None = None
    key_id: str
    recipes: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    signature: str = ""


class ProductionJobRecord(BaseModel):
    """Locally recorded production job payload for platform synchronization."""

    idempotency_key: str
    cell_id: str
    job_id: str
    request_hash: str
    status: str
    frozen_json: str
    result_json: str | None = None
    created_at: str


class ProductionTraceRecord(BaseModel):
    """Locally recorded production trace event for platform synchronization."""

    trace_id: str
    sequence: int
    cell_id: str
    job_id: str
    component_instance_id: str
    command_id: str
    event_type: str
    severity: str
    bundle_id: str = ""
    source_revision: str = ""
    recipe_id: str = ""
    recipe_version: int = 0
    recipe_sha256: str = ""
    task_id: str = ""
    task_sha256: str = ""
    execution_mode: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class ProductionResultRecord(BaseModel):
    """Locally recorded production job result for platform synchronization."""

    cell_id: str
    job_id: str
    trace_id: str
    success: bool
    result_code: str
    result_message: str
    output_payload_json: str = "{}"
    completed_at: str


class ProductionAttachmentRecord(BaseModel):
    """Metadata for content-addressed production attachments (e.g. inspection images)."""

    digest: str
    cell_id: str
    job_id: str | None = None
    trace_id: str
    filename: str
    media_type: str
    size_bytes: int


class SyncBatchRequest(BaseModel):
    """Batch of locally recorded production items submitted for synchronization."""

    cell_id: str
    jobs: list[ProductionJobRecord] = Field(default_factory=list)
    traces: list[ProductionTraceRecord] = Field(default_factory=list)
    results: list[ProductionResultRecord] = Field(default_factory=list)
    attachments: list[ProductionAttachmentRecord] = Field(default_factory=list)


class SyncBatchResponse(BaseModel):
    """Acknowledgment of synchronized production items."""

    acknowledged_job_keys: list[str] = Field(default_factory=list)
    acknowledged_trace_ids: list[str] = Field(default_factory=list)
    acknowledged_result_ids: list[str] = Field(default_factory=list)
    acknowledged_attachment_ids: list[str] = Field(default_factory=list)
    server_timestamp: str
