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


def __getattr__(name: str) -> object:
    """Load guided services lazily so Kit can bootstrap its source workspace first."""

    if name not in _GUIDED_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    guided = importlib.import_module(f"{__name__}.guided_launcher")
    value = getattr(guided, name)
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
]
