"""Adapter from the pure Studio application boundary to Task 004 project services."""

from pathlib import Path

from cellforge.studio.application import (
    BackendProject,
    BackendResult,
    StudioApplication,
    ValidationItem,
)


def create_default_application() -> StudioApplication:
    """Build an application with the installed CellForge backend, or an explicit empty state."""

    try:
        from cellforge_cli.projects import (
            ProjectOperationError,
            inspect_project,
            resolve_project_schema_directory,
            validate_project,
        )
        from cellforge_cli.resources import CliResources, ResourceUnavailableError
        from cellforge_domain import SchemaRegistry, SchemaRegistryError
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
        registry = SchemaRegistry.from_directory(resources.schema_directory)
    except (ResourceUnavailableError, SchemaRegistryError):
        return StudioApplication(
            None,
            backend_unavailable_message=(
                "Canonical CellForge schemas are unavailable. Synchronize the locked workspace "
                "and reload the extension."
            ),
        )

    class CliProjectBackend:
        """Read-only adapter that delegates every validation rule to Task 004 services."""

        def inspect(self, project_path: Path) -> BackendResult:
            try:
                schema_directory = resolve_project_schema_directory(
                    project_path, resources.schema_directory
                )
            except ProjectOperationError as error:
                finding = error.finding
                return BackendResult(
                    project=None,
                    validation=(
                        ValidationItem(
                            code=str(finding.code),
                            severity=finding.severity.value,
                            path=finding.path,
                            message=finding.message,
                        ),
                    ),
                )
            project_registry = (
                registry
                if schema_directory == resources.schema_directory.resolve()
                else SchemaRegistry.from_directory(schema_directory)
            )
            report = validate_project(project_path, project_registry)
            findings = tuple(
                ValidationItem(
                    code=str(finding.code),
                    severity=finding.severity.value,
                    path=finding.path,
                    message=finding.message,
                )
                for finding in report.findings
            )
            if findings:
                return BackendResult(project=None, validation=findings)

            summary = inspect_project(project_path, project_registry)
            return BackendResult(
                project=BackendProject(
                    path=summary.path,
                    cell_id=str(summary.cell_id),
                    name=summary.name,
                    scene=summary.scene,
                    component_count=summary.component_count,
                    connection_count=summary.connection_count,
                    task_count=summary.task_count,
                    recipe_count=summary.recipe_count,
                    scenario_count=summary.scenario_count,
                    deployment_profile_count=summary.deployment_profile_count,
                ),
                validation=(),
            )

    return StudioApplication(CliProjectBackend())
