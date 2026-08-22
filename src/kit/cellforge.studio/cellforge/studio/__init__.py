"""Pure application boundary and Kit adapter for the Cell Studio shell."""

import importlib

from cellforge.studio.application import (
    BackendProject,
    BackendResult,
    BrowserComponent,
    BrowserResult,
    ComponentEditResult,
    ComponentFilters,
    ComponentVariant,
    ConnectionBrowserResult,
    ConnectionEdge,
    ConnectionEditResult,
    ConnectionPort,
    LogEntry,
    LogLevel,
    MechanicalSnapPreview,
    ProjectBackend,
    ProjectContents,
    ProjectView,
    StudioApplication,
    StudioSnapshot,
    StudioStatus,
    ValidationItem,
)

_GUIDED_EXPORTS = frozenset(
    {
        "CancelProjectDraft",
        "CancelProjectDraftResult",
        "CreateProject",
        "CreateProjectRequest",
        "GuidedFinding",
        "GuidedProjectService",
        "GuidedStudioService",
        "OpenProject",
        "OpenProjectResult",
        "PreviewProject",
        "ProjectPreview",
        "ProjectSaveResult",
        "ProjectTemplateDescriptor",
        "RequiredChoice",
        "StudioProjectLauncher",
        "validate_project_preview_document",
    }
)

_READINESS_EXPORTS = frozenset(
    {
        "EvaluateStudioReadiness",
        "ReadinessBackendProbe",
        "ReadinessCandidatePreview",
        "ReadinessCategory",
        "ReadinessRemediation",
        "ReadinessSaveResult",
        "ReadinessService",
        "ReadinessSeverity",
        "ReadinessStatus",
        "SAFETY_REVIEW_DISCLAIMER",
        "StudioProjectIdentity",
        "StudioReadinessCheck",
        "StudioReadinessReport",
        "StudioReadinessService",
        "StudioReadinessSummary",
        "evaluate_studio_readiness",
        "validate_studio_readiness_report_document",
    }
)


def __getattr__(name: str) -> object:
    """Load guided services lazily so Kit can bootstrap its source workspace first."""

    if name not in _GUIDED_EXPORTS and name not in _READINESS_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name = "guided_launcher" if name in _GUIDED_EXPORTS else "readiness"
    module = importlib.import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [
    "BackendProject",
    "BackendResult",
    "BrowserComponent",
    "BrowserResult",
    "ComponentEditResult",
    "ComponentFilters",
    "ComponentVariant",
    "ConnectionBrowserResult",
    "ConnectionEdge",
    "ConnectionEditResult",
    "ConnectionPort",
    "LogEntry",
    "LogLevel",
    "MechanicalSnapPreview",
    "ProjectBackend",
    "ProjectContents",
    "ProjectView",
    "StudioApplication",
    "StudioSnapshot",
    "StudioStatus",
    "ValidationItem",
    "CancelProjectDraft",
    "CancelProjectDraftResult",
    "CreateProject",
    "CreateProjectRequest",
    "GuidedFinding",
    "GuidedProjectService",
    "GuidedStudioService",
    "OpenProject",
    "OpenProjectResult",
    "PreviewProject",
    "ProjectPreview",
    "ProjectSaveResult",
    "ProjectTemplateDescriptor",
    "RequiredChoice",
    "StudioProjectLauncher",
    "validate_project_preview_document",
    "EvaluateStudioReadiness",
    "ReadinessBackendProbe",
    "ReadinessCandidatePreview",
    "ReadinessCategory",
    "ReadinessRemediation",
    "ReadinessSaveResult",
    "ReadinessService",
    "ReadinessSeverity",
    "ReadinessStatus",
    "SAFETY_REVIEW_DISCLAIMER",
    "StudioProjectIdentity",
    "StudioReadinessCheck",
    "StudioReadinessReport",
    "StudioReadinessService",
    "StudioReadinessSummary",
    "evaluate_studio_readiness",
    "validate_studio_readiness_report_document",
]
