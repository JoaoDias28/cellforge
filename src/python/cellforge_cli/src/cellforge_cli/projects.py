"""Filesystem operations and summaries for headless CellForge projects."""

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from cellforge_domain import (
    CellProject,
    FindingSeverity,
    SchemaRegistry,
    SourceLoadError,
    ValidationFinding,
    load_document,
)
from cellforge_domain.example_validation import (
    ExampleValidationReport,
    validate_example_tree,
)

from cellforge_cli.exit_codes import ExitCode


class ProjectOperationError(Exception):
    """A sanitized, stable filesystem failure suitable for CLI output."""

    def __init__(
        self,
        *,
        exit_code: ExitCode,
        code: str,
        path: Path,
        message: str,
    ) -> None:
        self.exit_code = exit_code
        self.finding = ValidationFinding(
            code=code,
            severity=FindingSeverity.ERROR,
            path=f"{path.resolve()}#",
            message=message,
        )
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """Stable inspection data derived only from the canonical cell document."""

    path: Path
    cell_id: UUID
    name: str
    scene: str
    component_count: int
    connection_count: int
    task_count: int
    recipe_count: int
    scenario_count: int
    deployment_profile_count: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible deterministic command result."""

        return {
            "cell_id": str(self.cell_id),
            "component_count": self.component_count,
            "connection_count": self.connection_count,
            "deployment_profile_count": self.deployment_profile_count,
            "name": self.name,
            "path": str(self.path),
            "recipe_count": self.recipe_count,
            "scenario_count": self.scenario_count,
            "scene": self.scene,
            "task_count": self.task_count,
        }


def validate_project(project: str | Path, registry: SchemaRegistry) -> ExampleValidationReport:
    """Validate one project tree after project-level input preflight checks."""

    project_path = Path(project).resolve()
    if not project_path.is_dir():
        return _preflight_report(
            project_path,
            "cli.project-not-found",
            "Project directory does not exist or is not a directory.",
        )
    cell_path = project_path / "cell.yaml"
    if not cell_path.is_file():
        return _preflight_report(
            cell_path,
            "cli.cell-document-not-found",
            "Project does not contain the required cell.yaml document.",
        )
    return validate_example_tree(project_path, registry)


def resolve_project_schema_directory(project: str | Path, canonical_schemas: str | Path) -> Path:
    """Select byte-identical project schemas when present, otherwise the canonical directory."""

    project_schemas = Path(project).resolve() / "schemas"
    canonical_directory = Path(canonical_schemas).resolve()
    if not (project_schemas / "cell.schema.json").is_file():
        return canonical_directory

    expected_names = {path.name for path in canonical_directory.glob("*.json")}
    actual_names = {path.name for path in project_schemas.glob("*.json")}
    if actual_names != expected_names:
        raise ProjectOperationError(
            exit_code=ExitCode.VALIDATION_FAILED,
            code="cli.project-schema-set-mismatch",
            path=project_schemas,
            message="Project-local schemas do not match the canonical schema file set.",
        )

    for name in sorted(expected_names):
        canonical_path = canonical_directory / name
        project_schema = project_schemas / name
        try:
            matches_canonical = project_schema.read_bytes() == canonical_path.read_bytes()
        except OSError:
            matches_canonical = False
        if not matches_canonical:
            raise ProjectOperationError(
                exit_code=ExitCode.VALIDATION_FAILED,
                code="cli.project-schema-mismatch",
                path=project_schema,
                message="Project-local schema differs from the canonical bundled schema.",
            )

    return project_schemas


def inspect_project(project: str | Path, registry: SchemaRegistry) -> ProjectSummary:
    """Load a previously validated project's canonical operational graph."""

    project_path = Path(project).resolve()
    cell_path = project_path / "cell.yaml"
    try:
        cell = load_document(cell_path, CellProject, schema_registry=registry)
    except SourceLoadError as error:
        finding = (
            error.findings[0]
            if error.findings
            else ValidationFinding(
                code=error.code,
                severity=FindingSeverity.ERROR,
                path=f"{error.source_path}#",
                message=error.message,
            )
        )
        raise ProjectOperationError(
            exit_code=ExitCode.VALIDATION_FAILED,
            code=str(finding.code),
            path=error.source_path,
            message=finding.message,
        ) from None
    return ProjectSummary(
        path=project_path,
        cell_id=cell.cell.id,
        name=cell.cell.name,
        scene=cell.scene.usd,
        component_count=len(cell.components),
        connection_count=len(cell.connections),
        task_count=len(cell.tasks),
        recipe_count=len(cell.recipes),
        scenario_count=len(cell.scenarios),
        deployment_profile_count=len(cell.deployment_profiles),
    )


def initialize_project(destination: str | Path) -> UUID:
    """Create a valid, capability-free, simulation-only starter project."""

    destination_path = Path(destination).resolve()
    cell_id = uuid4()

    def populate(staging: Path) -> None:
        _write_starter_project(staging, cell_id, destination_path.name)

    _materialize_new_tree(destination_path, populate)
    return cell_id


def copy_example(
    source: str | Path,
    schema_source: str | Path,
    destination: str | Path,
) -> None:
    """Copy a canonical example without overwriting any existing destination."""

    source_path = Path(source).resolve()
    schema_source_path = Path(schema_source).resolve()
    destination_path = Path(destination).resolve()
    if destination_path.is_relative_to(source_path):
        raise ProjectOperationError(
            exit_code=ExitCode.OPERATION_FAILED,
            code="cli.destination-inside-source",
            path=destination_path,
            message="Destination must not be inside the canonical example source.",
        )

    def populate(staging: Path) -> None:
        shutil.copytree(source_path, staging, dirs_exist_ok=True)
        shutil.copytree(schema_source_path, staging / "schemas")
        cell_path = staging / "cell.yaml"
        cell_text = cell_path.read_text(encoding="utf-8")
        cell_path.write_text(
            cell_text.replace(
                "schema: ../../schemas/recipe.schema.json",
                "schema: schemas/recipe.schema.json",
            ),
            encoding="utf-8",
            newline="\n",
        )

    _materialize_new_tree(destination_path, populate)


def _preflight_report(path: Path, code: str, message: str) -> ExampleValidationReport:
    return ExampleValidationReport(
        documents_checked=0,
        auxiliary_schemas_checked=0,
        findings=(
            ValidationFinding(
                code=code,
                severity=FindingSeverity.ERROR,
                path=f"{path.resolve()}#",
                message=message,
            ),
        ),
    )


def _materialize_new_tree(destination: Path, populate: Callable[[Path], None]) -> None:
    if os.path.lexists(destination):
        raise ProjectOperationError(
            exit_code=ExitCode.DESTINATION_EXISTS,
            code="cli.destination-exists",
            path=destination,
            message="Destination already exists; no files were overwritten.",
        )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.cellforge-", dir=destination.parent)
        )
    except OSError:
        raise ProjectOperationError(
            exit_code=ExitCode.OPERATION_FAILED,
            code="cli.destination-create-failed",
            path=destination,
            message="Could not create the destination parent or staging directory.",
        ) from None

    try:
        populate(staging)
        staging.rename(destination)
    except OSError:
        raise ProjectOperationError(
            exit_code=ExitCode.OPERATION_FAILED,
            code="cli.destination-write-failed",
            path=destination,
            message="Could not write the requested project tree.",
        ) from None
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _write_starter_project(root: Path, cell_id: UUID, project_name: str) -> None:
    component_root = root / "components" / "workspace"
    asset_root = component_root / "assets"
    for directory in (asset_root, root / "recipes", root / "calibration", root / "scenarios"):
        directory.mkdir(parents=True, exist_ok=True)

    quoted_name = json.dumps(project_name or "CellForge Project", ensure_ascii=False)
    files = {
        root / "cell.yaml": f"""schema_version: 0.1.0
cell:
  id: {cell_id}
  name: {quoted_name}
  description: Capability-free simulation starter generated by CellForge.
scene:
  usd: scene.usda
  root_prim: /World
components:
  - id: workspace-001
    alias: workspace
    component: cellforge.passive-workspace.empty
    version: 0.1.0
    usd_prim: /World/Workspace
    adapter_mode: simulation
    config: {{}}
connections: []
tasks: []
recipes: []
calibrations: []
scenarios: []
deployment_profiles:
  - deployment-sim.yaml
""",
        root / "deployment-sim.yaml": """schema_version: 0.1.0
profile:
  id: local-simulation
  name: Local simulation-only target
platform:
  arch: amd64
  os: ubuntu-24.04
  ros_distribution: jazzy
runtime:
  native_packages: []
  containers: []
network: {}
modes: [simulation]
external_prerequisites: []
""",
        root / "scene.usda": """#usda 1.0
(
    defaultPrim = "World"
)

def Xform "World"
{
    def Xform "Workspace"
    {
    }
}
""",
        root / "behavior_tree.xml": """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4">
  <!-- No task is defined until an engineer adds and validates one. -->
</root>
""",
        root / "README.md": """# CellForge starter project

This project is a capability-free, simulation-only engineering scaffold. Passing schema validation
does not authorize physical operation or implement any functional-safety behavior. Add supported
components, tasks, recipes, validation evidence, and independently engineered safety before any
commissioning or production use.
""",
        component_root / "component.yaml": """schema_version: 0.1.0
component:
  id: cellforge.passive-workspace.empty
  version: 0.1.0
  kind: passive_geometry
  name: Empty workspace marker
  description: Metadata-only spatial marker with no executable capabilities.
  license: internal-reference
assets:
  visual_usd: assets/workspace_visual.usda
  collision_usd: assets/workspace_collision.usda
frames:
  - id: root
    role: root
    usd_prim: /Workspace
ports:
  mechanical: []
  software: []
  industrial_io: []
  safety: []
capabilities: []
adapters:
  simulation: null
  hardware: null
support:
  level: metadata_only
  simulation_level: L0
""",
        asset_root / "workspace_visual.usda": """#usda 1.0
def Xform "Workspace"
{
}
""",
        asset_root / "workspace_collision.usda": """#usda 1.0
def Xform "Workspace"
{
}
""",
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8", newline="\n")
