"""Public compiler report contracts."""

from enum import StrEnum

from cellforge_domain import (
    BundleManifest,
    DomainModel,
    ExecutionMode,
    ResolutionReport,
    StableIdentifier,
    ValidationFinding,
)


class CompilerStage(StrEnum):
    SCHEMA = "schema-validation"
    LINK = "instance-port-linking"
    SPATIAL = "usd-frame-validation"
    CAPABILITY = "capability-resolution"
    BEHAVIOR_TREE = "behavior-tree-validation"
    RECIPE = "recipe-compatibility"
    TARGET = "target-dependency-resolution"
    EVIDENCE = "required-evidence-check"
    MANIFEST = "immutable-manifest"


class StageStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageResult(DomainModel):
    stage: CompilerStage
    status: StageStatus
    finding_codes: tuple[StableIdentifier, ...] = ()


class CompilationReport(DomainModel):
    """Structured, deterministic result for CLI, Studio, and CI callers."""

    valid: bool
    execution_mode: ExecutionMode
    requested_target_profile: StableIdentifier
    stages: tuple[StageResult, ...]
    resolution: ResolutionReport | None = None
    manifest: BundleManifest | None = None
    manifest_json: str | None = None
    findings: tuple[ValidationFinding, ...] = ()
