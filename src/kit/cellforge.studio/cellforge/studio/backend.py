"""Adapter wiring the pure Studio state machine to project command services."""

from cellforge.studio.application import StudioApplication


def create_default_application() -> StudioApplication:
    """Build an application with installed project services, or an explicit empty state."""

    try:
        from cellforge_cli.resources import CliResources, ResourceUnavailableError
        from cellforge_domain import SchemaRegistry, SchemaRegistryError

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

    return StudioApplication(ProjectCommandService(resources.schema_directory))
