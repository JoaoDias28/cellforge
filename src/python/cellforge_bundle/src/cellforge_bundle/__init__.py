"""Deterministic CellForge deployment compilation and local activation."""

from cellforge_bundle.agent import (
    AgentError,
    AgentPaths,
    AgentStatus,
    BundleAgent,
    VerifiedBundle,
    preflight_target,
    verify_bundle,
)
from cellforge_bundle.assembly import AssemblyError, AssemblyResult, assemble_bundle
from cellforge_bundle.compiler import compile_project
from cellforge_bundle.models import CompilationReport, CompilerStage, StageResult, StageStatus
from cellforge_bundle.output import ManifestWriteError, write_manifest
from cellforge_bundle.qualification import (
    QUALIFICATION_DISCLAIMERS,
    ParityVerificationResult,
    PlatformQualificationResult,
    QualificationCategory,
    ScenarioQualificationResult,
    SoftwareReleaseQualificationReport,
    run_software_release_qualification,
    sign_qualification_report,
    verify_qualification_report,
    verify_tree_and_recipe_parity,
)

__all__ = [
    "AgentError",
    "AgentPaths",
    "AgentStatus",
    "BundleAgent",
    "AssemblyError",
    "AssemblyResult",
    "CompilationReport",
    "CompilerStage",
    "ManifestWriteError",
    "StageResult",
    "StageStatus",
    "VerifiedBundle",
    "compile_project",
    "assemble_bundle",
    "preflight_target",
    "verify_bundle",
    "write_manifest",
    "QUALIFICATION_DISCLAIMERS",
    "ParityVerificationResult",
    "PlatformQualificationResult",
    "QualificationCategory",
    "ScenarioQualificationResult",
    "SoftwareReleaseQualificationReport",
    "run_software_release_qualification",
    "sign_qualification_report",
    "verify_qualification_report",
    "verify_tree_and_recipe_parity",
]
