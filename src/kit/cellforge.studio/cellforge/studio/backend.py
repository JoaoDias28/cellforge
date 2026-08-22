"""Adapter wiring the pure Studio state machine to project command services."""

import sys
from pathlib import Path

from cellforge.studio.application import StudioApplication


def _add_source_workspace_paths() -> None:
    """Use the checkout's locked packages when Kit is launched from this repository."""

    root = Path(__file__).resolve().parents[5]
    package_roots = (
        root / ".venv" / "Lib" / "site-packages",
        root / "src" / "python" / "cellforge_cli" / "src",
        root / "src" / "python" / "cellforge_domain" / "src",
        root / "src" / "python" / "cellforge_bundle" / "src",
    )
    for package_root in package_roots:
        if package_root.is_dir() and str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))


def create_default_application() -> StudioApplication:
    """Build an application with installed project services, or an explicit empty state."""

    _add_source_workspace_paths()
    try:
        from cellforge_cli.resources import CliResources, ResourceUnavailableError
        from cellforge_domain import SchemaRegistry, SchemaRegistryError

        from cellforge.studio.guided_launcher import GuidedProjectService
        from cellforge.studio.project_service import ProjectCommandService
    except ImportError:
        return StudioApplication(
            None,
            backend_unavailable_message=(
                "Install the CellForge Python workspace into the Isaac Sim 6 Python environment, "
                "then reload the extension."
            ),
        )

    try:
        resources = CliResources.discover()
        SchemaRegistry.from_directory(resources.schema_directory)
    except (ResourceUnavailableError, SchemaRegistryError):
        return StudioApplication(
            None,
            backend_unavailable_message=(
                "Canonical CellForge schemas are unavailable. Synchronize the locked workspace "
                "and reload the extension."
            ),
        )

    project_service = ProjectCommandService(resources.schema_directory)
    guided_service = GuidedProjectService(
        resources.schema_directory,
        project_service=project_service,
    )
    return StudioApplication(project_service, guided_service=guided_service)
