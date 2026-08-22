"""Pure project command service for synchronized CellForge YAML and USD sources."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from cellforge_cli.projects import (
    ProjectOperationError,
    ProjectSummary,
    initialize_project,
    inspect_project,
    resolve_project_schema_directory,
    validate_project,
)
from cellforge_domain import CellProject, SchemaRegistry, ValidationFinding
from cellforge_domain.schemas import SchemaDocumentKind
from pydantic import ValidationError

from cellforge.studio.application import (
    BackendProject,
    BackendResult,
    BrowserResult,
    ComponentEditResult,
    ComponentFilters,
    ConnectionBrowserResult,
    ConnectionEditResult,
    ConnectionLayoutMetadata,
    ProjectContents,
    SpatialBrowserResult,
    SpatialEditResult,
    ValidationItem,
)
from cellforge.studio.component_service import ComponentPlacementService
from cellforge.studio.connection_service import ConnectionAuthoringService
from cellforge.studio.deployment_service import (
    AgentPaths,
    BundleAssemblyResult,
    BundleDiffResult,
    DeploymentBrowserResult,
    DeploymentInstallResult,
    DeploymentProfileDetail,
    DeploymentRollbackResult,
    DeploymentService,
    DeploymentStatusResult,
    SignatureVerificationResult,
    TargetCompatibilityResult,
)
from cellforge.studio.recipe_service import (
    RecipeAuthoringService,
    RecipeBrowserResult,
    RecipeDetail,
    RecipeDiffResult,
    RecipeEditResult,
)
from cellforge.studio.scenario_service import (
    EvidenceDetail,
    EvidenceSummary,
    ScenarioAssertionSpec,
    ScenarioBrowserResult,
    ScenarioDetail,
    ScenarioEvidenceService,
    ScenarioExecutionResult,
    ScenarioFaultSpec,
    ScenarioReplayResult,
)
from cellforge.studio.scene import inspect_scene, validate_scene_cross_references
from cellforge.studio.schema_authoring import (
    AuthoringCandidate,
    AuthoringSaveResult,
    SchemaAuthoringService,
    SchemaFormModel,
)
from cellforge.studio.spatial_configuration import SpatialConfigurationService
from cellforge.studio.task_service import (
    TaskAuthoringService,
    TaskBrowserResult,
    TaskEditResult,
    TaskTreeModel,
)

RECOVERY_FILE = ".cellforge-save-recovery.json"


class ProjectSaveError(Exception):
    """Sanitized project transaction failure returned to the application boundary."""


@dataclass(frozen=True, slots=True)
class _OpenedCandidate:
    contents: ProjectContents
    cell_data: Mapping[str, Any]
    scene_path: Path


@dataclass(frozen=True, slots=True)
class _ParsedCell:
    model: CellProject
    data: Mapping[str, Any]


class ProjectCommandService:
    """Create, open, validate, and explicitly save synchronized project sources."""

    def __init__(
        self,
        canonical_schema_directory: Path,
        *,
        replace_file: Callable[[str | Path, str | Path], None] = os.replace,
        component_service: ComponentPlacementService | None = None,
        connection_service: ConnectionAuthoringService | None = None,
        spatial_service: SpatialConfigurationService | None = None,
        task_service: TaskAuthoringService | None = None,
        recipe_service: RecipeAuthoringService | None = None,
        scenario_service: ScenarioEvidenceService | None = None,
        deployment_service: DeploymentService | None = None,
        authoring_service: SchemaAuthoringService | None = None,
    ) -> None:
        self._canonical_schemas = canonical_schema_directory.resolve()
        self._replace_file = replace_file
        self._components = component_service or ComponentPlacementService(self._canonical_schemas)
        self._connections = connection_service or ConnectionAuthoringService(
            self._canonical_schemas
        )
        self._spatial = spatial_service or SpatialConfigurationService(self._canonical_schemas)
        self._tasks = task_service or TaskAuthoringService(self._canonical_schemas)
        self._recipes = recipe_service or RecipeAuthoringService(self._canonical_schemas)
        self._scenarios = scenario_service or ScenarioEvidenceService(self._canonical_schemas)
        self._deployments = deployment_service or DeploymentService(self._canonical_schemas)
        self._authoring = authoring_service or SchemaAuthoringService(
            self._canonical_schemas,
            project_service=self,
            replace_file=self._replace_file,
        )

    def create(self, project_path: Path) -> BackendResult:
        """Explicitly create a starter project and return its validated buffers."""

        initialize_project(project_path)
        return self.inspect(project_path)

    def save_new_project(
        self,
        project_path: Path,
        files: Mapping[str, bytes],
        *,
        validate_studio_extensions: bool = True,
    ) -> BackendResult:
        """Validate and atomically materialize a new complete project tree.

        Guided Studio candidates are assembled in memory and handed to this existing project
        service only after explicit confirmation.  The complete tree is first inspected in a
        sibling staging directory, then written through Task 015's recovery-journal transaction.
        An existing destination is never overwritten.
        """

        root = project_path.resolve()
        if os.path.lexists(root):
            return BackendResult(
                project=None,
                validation=(
                    ValidationItem(
                        code="studio.destination-exists",
                        severity="error",
                        path=f"{root}#",
                        message="The destination already exists; no files were overwritten.",
                    ),
                ),
            )
        required = {"cell.yaml", "scene.usda", "behavior_tree.xml"}
        missing = sorted(required - set(files))
        if missing:
            return BackendResult(
                project=None,
                validation=(
                    ValidationItem(
                        code="studio.canonical-file-missing",
                        severity="error",
                        path=f"{root}#",
                        message=f"New project is missing canonical files: {', '.join(missing)}.",
                    ),
                ),
            )

        normalized: dict[str, bytes] = {}
        for relative, content in sorted(files.items()):
            relative_path = Path(relative)
            target = (root / relative_path).resolve()
            if (
                relative_path.is_absolute()
                or not target.is_relative_to(root)
                or not isinstance(content, bytes)
            ):
                return BackendResult(
                    project=None,
                    validation=(
                        ValidationItem(
                            code="studio.candidate-path-invalid",
                            severity="error",
                            path=f"{root}#",
                            message="New project candidate paths must remain project-relative.",
                        ),
                    ),
                )
            normalized[relative_path.as_posix()] = content

        staging: Path | None = None
        root_created = False
        try:
            root.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(
                tempfile.mkdtemp(prefix=f".{root.name}.cellforge-guided-", dir=root.parent)
            )
            for relative, content in normalized.items():
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            inspected = self.inspect_candidate(
                staging,
                validate_studio_extensions=validate_studio_extensions,
            )
            if inspected.project is None or inspected.contents is None:
                return _remap_backend_result(inspected, staging, root)
            root.mkdir()
            root_created = True
            self._transactional_replace(
                root,
                {root / relative: content for relative, content in normalized.items()},
            )
            shutil.rmtree(staging, ignore_errors=True)
            staging = None
            result = self.inspect_candidate(
                root,
                validate_studio_extensions=validate_studio_extensions,
            )
            if result.project is None or result.contents is None:
                if not (root / RECOVERY_FILE).exists():
                    shutil.rmtree(root, ignore_errors=True)
            return result
        except (OSError, ProjectSaveError) as error:
            if root_created and not (root / RECOVERY_FILE).exists():
                shutil.rmtree(root, ignore_errors=True)
            return BackendResult(
                project=None,
                validation=(
                    ValidationItem(
                        code="studio.new-project-save-failed",
                        severity="error",
                        path=f"{root}#",
                        message=(
                            f"New project save failed ({type(error).__name__}); no partial "
                            "project was accepted."
                        ),
                    ),
                ),
            )
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)

    def inspect(self, project_path: Path) -> BackendResult:
        """Open and validate a project byte-for-byte without modifying any file."""

        root = project_path.resolve()
        try:
            registry = self._registry_for(root)
        except ProjectOperationError as error:
            return BackendResult(project=None, validation=(_validation_item(error.finding),))

        report = validate_project(root, registry)
        findings = [_validation_item(item) for item in report.findings]
        candidate = self._read_candidate(root)
        if isinstance(candidate, _OpenedCandidate):
            contents = candidate.contents
            scene, scene_findings = inspect_scene(contents.scene_usda, candidate.scene_path)
            findings.extend(scene_findings)
            findings.extend(self._spatial.validate_calibrations(root, contents))
            findings.extend(self._tasks.browse(root, contents).validation)
            findings.extend(self._recipes.browse(root, contents).validation)
            findings.extend(self._scenarios.browse_scenarios(root, contents).validation)
            findings.extend(self._deployments.browse_deployment_profiles(root, contents).validation)
            if scene is not None:
                findings.extend(
                    validate_scene_cross_references(
                        candidate.cell_data,
                        scene,
                        cell_path=root / "cell.yaml",
                        scene_path=candidate.scene_path,
                    )
                )
        else:
            contents = None
            findings.extend(candidate)

        findings = list(_unique_findings(findings))
        if findings or contents is None:
            return BackendResult(project=None, validation=tuple(findings))
        summary = inspect_project(root, registry)
        return BackendResult(
            project=_backend_project(summary),
            validation=(),
            contents=contents,
        )

    def inspect_candidate(
        self,
        project_path: Path,
        *,
        validate_studio_extensions: bool = True,
    ) -> BackendResult:
        """Inspect an isolated candidate with optional task-editor extension checks.

        Canonical schema, recipe, scenario, deployment, and YAML/USD identity checks are always
        applied. Task 038's reusable kitting XML is an executable simulation contract but does
        not declare a Studio task-editor plugin manifest, so the guided launcher can deliberately
        omit only the editor-plugin inventory check while preserving the source validator.
        """

        if validate_studio_extensions:
            return self.inspect(project_path)
        root = project_path.resolve()
        try:
            registry = self._registry_for(root)
        except ProjectOperationError as error:
            return BackendResult(project=None, validation=(_validation_item(error.finding),))

        report = validate_project(root, registry)
        findings = [_validation_item(item) for item in report.findings]
        candidate = self._read_candidate(root)
        if isinstance(candidate, _OpenedCandidate):
            scene, scene_findings = inspect_scene(
                candidate.contents.scene_usda, candidate.scene_path
            )
            findings.extend(scene_findings)
            findings.extend(self._spatial.validate_calibrations(root, candidate.contents))
            findings.extend(self._recipes.browse(root, candidate.contents).validation)
            findings.extend(self._scenarios.browse_scenarios(root, candidate.contents).validation)
            findings.extend(
                self._deployments.browse_deployment_profiles(root, candidate.contents).validation
            )
            if scene is not None:
                findings.extend(
                    validate_scene_cross_references(
                        candidate.cell_data,
                        scene,
                        cell_path=root / "cell.yaml",
                        scene_path=candidate.scene_path,
                    )
                )
            contents = candidate.contents
        else:
            contents = None
            findings.extend(candidate)
        findings = list(_unique_findings(findings))
        if findings or contents is None:
            return BackendResult(project=None, validation=tuple(findings))
        summary = inspect_project(root, registry)
        return BackendResult(
            project=_backend_project(summary),
            validation=(),
            contents=contents,
        )

    def save(self, project_path: Path, contents: ProjectContents) -> BackendResult:
        """Validate candidates, journal previous bytes, and replace both files transactionally."""

        root = project_path.resolve()
        current = self.inspect(root)
        if current.project is None or current.contents is None:
            return current

        registry = self._registry_for(root)
        cell_path = root / "cell.yaml"
        candidate = _parse_cell_candidate(contents.cell_yaml, cell_path, registry)
        if isinstance(candidate, _ParsedCell):
            cell_model = candidate.model
            cell_data = candidate.data
        else:
            return BackendResult(project=None, validation=candidate)

        if cell_model.scene.usd != current.project.scene:
            return BackendResult(
                project=None,
                validation=(
                    ValidationItem(
                        code="studio.scene-reference-change-unsupported",
                        severity="error",
                        path=f"{cell_path}#/scene/usd",
                        message=(
                            "Task 015 does not rename the canonical scene during save; "
                            "keep the existing scene reference."
                        ),
                    ),
                ),
            )
        scene_path = _contained_scene_path(root, cell_model.scene.usd)
        if scene_path is None:
            return BackendResult(
                project=None,
                validation=(
                    ValidationItem(
                        code="studio.scene-reference-outside-project",
                        severity="error",
                        path=f"{cell_path}#/scene/usd",
                        message="The canonical scene reference must remain inside the project.",
                    ),
                ),
            )

        project_findings = self._validate_candidate_tree(
            root,
            contents,
            cell_model.scene.usd,
        )
        project_findings = (
            *project_findings,
            *self._spatial.validate_calibrations(root, contents),
            *self._tasks.browse(root, contents).validation,
            *self._recipes.browse(root, contents).validation,
        )
        if project_findings:
            return BackendResult(project=None, validation=project_findings)

        scene, scene_findings = inspect_scene(contents.scene_usda, scene_path)
        findings = list(scene_findings)
        if scene is not None:
            findings.extend(
                validate_scene_cross_references(
                    cell_data,
                    scene,
                    cell_path=cell_path,
                    scene_path=scene_path,
                )
            )
        if findings:
            return BackendResult(project=None, validation=tuple(findings))

        self._resolve_recovery(root)
        artifacts = _artifact_candidates(root, contents.artifacts)
        if isinstance(artifacts, BackendResult):
            return artifacts
        self._transactional_replace(
            root,
            {
                cell_path: contents.cell_yaml.encode("utf-8"),
                scene_path: contents.scene_usda.encode("utf-8"),
                **artifacts,
            },
        )
        summary = _summary_from_model(root, cell_model)
        return BackendResult(
            project=summary,
            validation=(),
            contents=contents,
        )

    def build_schema_form(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        schema: Mapping[str, Any] | str | Path,
        source_path: str | Path | None = None,
        schema_kind: str | SchemaDocumentKind | None = None,
        allocator_seed: str | None = None,
        required_choices: Mapping[str, Sequence[str]] | None = None,
        artifact_path: str | None = None,
    ) -> SchemaFormModel:
        """Build a schema form from staged project buffers without writing files."""

        return self._authoring.BuildSchemaForm(
            schema,
            source_path=source_path,
            schema_kind=schema_kind,
            allocator_seed=allocator_seed,
            required_choices=required_choices,
            project_path=project_path,
            project_contents=contents,
            artifact_path=artifact_path,
        )

    def update_schema_form(
        self,
        form: SchemaFormModel,
        values: Mapping[str, Any] | None = None,
        *,
        changes: Mapping[str, Any] | None = None,
    ) -> SchemaFormModel:
        """Apply deterministic form changes without changing project files."""

        return self._authoring.UpdateSchemaForm(form, values, changes=changes)

    def preview_source_edit(
        self,
        form_or_candidate: SchemaFormModel | AuthoringCandidate,
        source: str | bytes | Path | None = None,
        *,
        source_path: str | Path | None = None,
        artifact_path: str | None = None,
        project_path: Path | None = None,
        project_contents: ProjectContents | None = None,
    ) -> AuthoringCandidate:
        """Parse and validate advanced source text without changing project files."""

        return self._authoring.PreviewSourceEdit(
            form_or_candidate,
            source,
            source_path=source_path,
            artifact_path=artifact_path,
            project_path=project_path,
            project_contents=project_contents,
        )

    def merge_source_edit(
        self,
        form_or_candidate: SchemaFormModel | AuthoringCandidate,
        source_or_candidate: str | bytes | Path | AuthoringCandidate,
        *,
        project_path: Path | None = None,
        project_contents: ProjectContents | None = None,
    ) -> AuthoringCandidate:
        """Three-way merge a source candidate and report conflicts without writing."""

        return self._authoring.MergeSourceEdit(
            form_or_candidate,
            source_or_candidate,
            project_path=project_path,
            project_contents=project_contents,
        )

    def save_authoring_candidate(
        self,
        candidate: AuthoringCandidate,
        confirmation_token: str | None = None,
        *,
        confirmed: bool = False,
        project_path: Path | None = None,
        project_contents: ProjectContents | None = None,
    ) -> AuthoringSaveResult:
        """Save a confirmed schema candidate through the existing paired transaction."""

        return self._authoring.SaveAuthoringCandidate(
            candidate,
            confirmation_token,
            confirmed=confirmed,
            project_path=project_path,
            project_contents=project_contents,
        )

    def recover(self, project_path: Path) -> None:
        """Explicitly resolve a retained recovery journal after an interrupted process."""

        self._resolve_recovery(project_path.resolve())

    def browse_components(
        self, project_path: Path, filters: ComponentFilters = ComponentFilters()
    ) -> BrowserResult:
        """Delegate registry filtering and compatibility details to the pure component service."""

        return self._components.browse(project_path, filters)

    def place_component(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        component: str,
        version: str,
        alias: str,
        variants: Mapping[str, str],
    ) -> ComponentEditResult:
        """Return an in-memory linked YAML/USD placement without writing project files."""

        return self._components.place(
            project_path,
            contents,
            component=component,
            version=version,
            alias=alias,
            variants=variants,
        )

    def remove_component(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        remove_connections: bool,
    ) -> ComponentEditResult:
        """Return an in-memory linked removal with explicit connection resolution."""

        return self._components.remove(
            project_path,
            contents,
            instance_id=instance_id,
            remove_connections=remove_connections,
        )

    def browse_connections(
        self, project_path: Path, contents: ProjectContents
    ) -> ConnectionBrowserResult:
        """Return typed ports and graph edges from the current in-memory sources."""

        return self._connections.browse(project_path, contents)

    def browse_spatial(self, project_path: Path, contents: ProjectContents) -> SpatialBrowserResult:
        """Return viewport-neutral transforms, frames, and collision display data."""

        return self._spatial.browse(project_path, contents)

    def preview_mechanical_connection(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        connection_id: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
    ) -> ConnectionEditResult:
        """Return a validated mechanical snap preview without changing sources."""

        return self._connections.preview_mechanical(
            project_path,
            contents,
            connection_id=connection_id,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
        )

    def connect_ports(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        connection_id: str,
        kind: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
    ) -> ConnectionEditResult:
        """Return a validated logical or paired mechanical connection edit."""

        return self._connections.connect(
            project_path,
            contents,
            connection_id=connection_id,
            kind=kind,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
        )

    def PreviewCellConnection(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        kind: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
        connection_id: str | None = None,
    ) -> ConnectionEditResult:
        """Preview a typed connection through the pure connection service."""

        return self._connections.PreviewCellConnection(
            project_path,
            contents,
            kind=kind,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
            connection_id=connection_id,
        )

    def StageCellConnection(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        kind: str,
        from_component: str,
        from_port: str,
        to_component: str,
        to_port: str,
        connection_id: str | None = None,
    ) -> ConnectionEditResult:
        """Stage a typed connection through the pure connection service."""

        return self._connections.StageCellConnection(
            project_path,
            contents,
            kind=kind,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
            connection_id=connection_id,
        )

    def RemoveCellConnection(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        connection_id: str,
    ) -> ConnectionEditResult:
        """Stage removal of one typed connection without writing canonical files."""

        return self._connections.RemoveCellConnection(
            project_path,
            contents,
            connection_id=connection_id,
        )

    def ValidateCellConnections(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        query: str = "",
        selected_endpoint_id: str | None = None,
        layout: ConnectionLayoutMetadata | None = None,
    ) -> ConnectionBrowserResult:
        """Validate the complete typed connection graph through the pure service."""

        return self._connections.ValidateCellConnections(
            project_path,
            contents,
            query=query,
            selected_endpoint_id=selected_endpoint_id,
            layout=layout,
        )

    def set_component_transform(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        matrix: tuple[float, ...],
    ) -> SpatialEditResult:
        """Return an in-memory validated component transform edit."""

        return self._spatial.set_transform(
            project_path, contents, instance_id=instance_id, matrix=matrix
        )

    def set_component_configuration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        configuration: Mapping[str, object],
    ) -> SpatialEditResult:
        """Return an in-memory schema-backed component configuration edit."""

        return self._spatial.set_component_configuration(
            project_path, contents, instance_id=instance_id, configuration=configuration
        )

    def set_component_variants(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        variants: Mapping[str, str],
    ) -> SpatialEditResult:
        """Return an in-memory declared variant selection edit."""

        return self._spatial.set_component_variants(
            project_path, contents, instance_id=instance_id, variants=variants
        )

    def create_calibration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        kind: str,
        valid_until: str,
        data: Mapping[str, object],
    ) -> SpatialEditResult:
        """Create a staged calibration after parsing its explicit validity deadline."""

        try:
            deadline = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        except ValueError:
            return SpatialEditResult(
                contents=None,
                validation=(
                    ValidationItem(
                        code="studio.calibration-valid-until-invalid",
                        severity="error",
                        path=f"{project_path.resolve() / 'calibration'}#",
                        message="Calibration valid-until must be an ISO-8601 timestamp.",
                    ),
                ),
            )
        return self._spatial.create_calibration(
            project_path,
            contents,
            instance_id=instance_id,
            kind=kind,
            valid_until=deadline,
            data=data,
        )

    def import_calibration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        calibration: Mapping[str, object],
    ) -> SpatialEditResult:
        """Stage an existing immutable calibration and bind it to one component."""

        return self._spatial.import_calibration(
            project_path,
            contents,
            instance_id=instance_id,
            calibration=calibration,
        )

    def browse_tasks(self, project_path: Path, contents: ProjectContents) -> TaskBrowserResult:
        """Return tasks and node manifests for current project sources."""
        return self._tasks.browse(project_path, contents)

    def set_task_tree(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        task_id: str,
        tree: TaskTreeModel | str,
    ) -> TaskEditResult:
        """Edit a task's BehaviorTree XML in staged project artifacts."""
        return self._tasks.set_task_tree(project_path, contents, task_id=task_id, tree=tree)

    def browse_recipes(self, project_path: Path, contents: ProjectContents) -> RecipeBrowserResult:
        """Return recipes and validation findings for current project sources."""
        return self._recipes.browse(project_path, contents)

    def inspect_recipe(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int | None = None,
    ) -> RecipeDetail | None:
        """Inspect specific recipe version fields and form schema metadata."""
        return self._recipes.inspect_recipe(
            project_path, contents, recipe_id=recipe_id, version=version
        )

    def edit_recipe(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int,
        data: Mapping[str, Any],
    ) -> RecipeEditResult:
        """Edit a draft recipe document in memory."""
        return self._recipes.edit_recipe(
            project_path, contents, recipe_id=recipe_id, version=version, data=data
        )

    def create_recipe_version(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        base_version: int | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> RecipeEditResult:
        """Create a new immutable recipe version without mutating its predecessor."""
        return self._recipes.create_recipe_version(
            project_path,
            contents,
            recipe_id=recipe_id,
            base_version=base_version,
            overrides=overrides,
        )

    def transition_recipe_lifecycle(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int,
        target_status: str,
        evidence: Sequence[str] | None = None,
    ) -> RecipeEditResult:
        """Transition a recipe version to a new lifecycle state."""
        return self._recipes.transition_lifecycle(
            project_path,
            contents,
            recipe_id=recipe_id,
            version=version,
            target_status=target_status,
            evidence=evidence,
        )

    def diff_recipes(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version_a: int,
        version_b: int,
    ) -> RecipeDiffResult | None:
        """Diff two recipe versions in the current project sources."""
        rec_a = self.inspect_recipe(project_path, contents, recipe_id=recipe_id, version=version_a)
        rec_b = self.inspect_recipe(project_path, contents, recipe_id=recipe_id, version=version_b)
        if rec_a is None or rec_b is None:
            return None
        return self._recipes.diff(rec_a.data, rec_b.data)

    def browse_scenarios(
        self, project_path: Path, contents: ProjectContents
    ) -> ScenarioBrowserResult:
        """Enumerate and summarize all scenarios declared in the project."""
        return self._scenarios.browse_scenarios(project_path, contents)

    def inspect_scenario(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        scenario_id: str,
    ) -> ScenarioDetail | None:
        """Inspect full scenario definition and parameters."""
        return self._scenarios.inspect_scenario(
            project_path, contents, scenario_id_or_path=scenario_id
        )

    def execute_scenario(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        scenario_id: str,
        seed_override: int | None = None,
        injected_faults: Sequence[ScenarioFaultSpec] | None = None,
        available_backend_fidelity: str = "L0",
        has_cuda_gpu: bool = False,
        actual_physx_executed: bool = False,
    ) -> ScenarioExecutionResult:
        """Execute a scenario and produce evidence."""
        return self._scenarios.execute_scenario(
            project_path,
            contents,
            scenario_id_or_path=scenario_id,
            seed_override=seed_override,
            injected_faults=injected_faults,
            available_backend_fidelity=available_backend_fidelity,
            has_cuda_gpu=has_cuda_gpu,
            actual_physx_executed=actual_physx_executed,
        )

    def browse_evidence(self, project_path: Path) -> tuple[EvidenceSummary, ...]:
        """Scan and summarize evidence files in the project."""
        return self._scenarios.browse_evidence(project_path)

    def inspect_evidence(self, project_path: Path, *, evidence_path: str) -> EvidenceDetail | None:
        """Inspect full simulation evidence document."""
        return self._scenarios.inspect_evidence(project_path, evidence_path)

    def replay_evidence(
        self,
        project_path: Path,
        *,
        evidence_path: str,
        expected_assertions: ScenarioAssertionSpec | None = None,
    ) -> ScenarioReplayResult | None:
        """Replay and verify recorded evidence for deterministic consistency."""
        detail = self._scenarios.inspect_evidence(project_path, evidence_path)
        if detail is None:
            return None
        return self._scenarios.replay_evidence(detail.data, expected_assertions)

    def browse_deployment_profiles(
        self, project_path: Path, contents: ProjectContents
    ) -> DeploymentBrowserResult:
        """Enumerate all deployment profiles declared in the project."""
        return self._deployments.browse_deployment_profiles(project_path, contents)

    def inspect_deployment_profile(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        profile_id: str,
    ) -> DeploymentProfileDetail | None:
        """Inspect full deployment profile configuration."""
        return self._deployments.inspect_deployment_profile(
            project_path, contents, profile_id_or_path=profile_id
        )

    def assemble_bundle(
        self,
        project_path: Path,
        schemas_path: Path,
        *,
        target_profile: str,
        mode: str,
        source_revision: str,
        output_dir: Path,
        signing_key_path: Path,
    ) -> BundleAssemblyResult:
        """Assemble an immutable signed release bundle."""
        return self._deployments.assemble_bundle_release(
            project_path,
            schemas_path,
            target_profile=target_profile,
            mode=mode,
            source_revision=source_revision,
            output_dir=output_dir,
            signing_key_path=signing_key_path,
        )

    def diff_bundles(
        self,
        base_bundle_path: Path,
        candidate_bundle_path: Path,
    ) -> BundleDiffResult:
        """Compute deterministic differences between two bundle directories."""
        return self._deployments.diff_bundles(base_bundle_path, candidate_bundle_path)

    def verify_bundle_signature(
        self,
        bundle_root: Path,
        trusted_keys_root: Path | None = None,
    ) -> SignatureVerificationResult:
        """Verify the Ed25519 signature of a release bundle."""
        return self._deployments.verify_bundle_signature(bundle_root, trusted_keys_root)

    def preflight_target_compatibility(
        self,
        bundle_root: Path,
        target_facts_path: Path,
    ) -> TargetCompatibilityResult:
        """Check bundle compatibility against target facts."""
        return self._deployments.preflight_target_compatibility(bundle_root, target_facts_path)

    def get_deployment_status(self, agent_paths: AgentPaths) -> DeploymentStatusResult:
        """Query deployment agent status."""
        return self._deployments.get_agent_status(agent_paths)

    def install_bundle(
        self,
        bundle_root: Path,
        agent_paths: AgentPaths,
        *,
        systemd_runner: Any | None = None,
        health_checker: Any | None = None,
    ) -> DeploymentInstallResult:
        """Install a release bundle to target."""
        return self._deployments.install_bundle(
            bundle_root, agent_paths, systemd_runner=systemd_runner, health_checker=health_checker
        )

    def rollback_deployment(
        self,
        agent_paths: AgentPaths,
        *,
        systemd_runner: Any | None = None,
        health_checker: Any | None = None,
    ) -> DeploymentRollbackResult:
        """Rollback to previous release."""
        return self._deployments.rollback_deployment(
            agent_paths, systemd_runner=systemd_runner, health_checker=health_checker
        )

    def _registry_for(self, project_path: Path) -> SchemaRegistry:
        directory = resolve_project_schema_directory(project_path, self._canonical_schemas)
        return SchemaRegistry.from_directory(directory)

    def _read_candidate(self, root: Path) -> _OpenedCandidate | tuple[ValidationItem, ...]:
        cell_path = root / "cell.yaml"
        try:
            cell_text = cell_path.read_text(encoding="utf-8")
            raw = yaml.safe_load(cell_text)
        except (OSError, UnicodeError, yaml.YAMLError):
            return (
                ValidationItem(
                    code="studio.cell-read-failed",
                    severity="error",
                    path=f"{cell_path}#",
                    message="Could not read a valid UTF-8 cell.yaml document.",
                ),
            )
        if not isinstance(raw, Mapping):
            return (
                ValidationItem(
                    code="studio.cell-root-invalid",
                    severity="error",
                    path=f"{cell_path}#",
                    message="cell.yaml must contain an object at its document root.",
                ),
            )
        scene_reference = _scene_reference(raw)
        scene_path = _contained_scene_path(root, scene_reference) if scene_reference else None
        if scene_path is None:
            return (
                ValidationItem(
                    code="studio.scene-reference-invalid",
                    severity="error",
                    path=f"{cell_path}#/scene/usd",
                    message="cell.yaml must reference a scene inside the project.",
                ),
            )
        if scene_path.suffix.lower() != ".usda":
            return (
                ValidationItem(
                    code="studio.scene-openusd-required",
                    severity="error",
                    path=f"{scene_path}#",
                    message=(
                        "This headless host can round-trip text USDA stages; binary USD requires "
                        "the Isaac Sim 6 OpenUSD runtime."
                    ),
                ),
            )
        try:
            scene_text = scene_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return (
                ValidationItem(
                    code="studio.scene-read-failed",
                    severity="error",
                    path=f"{scene_path}#",
                    message="Could not read the canonical USDA scene.",
                ),
            )
        return _OpenedCandidate(
            contents=ProjectContents(
                cell_yaml=cell_text,
                scene_usda=scene_text,
                artifacts=_read_calibration_artifacts(root, raw),
            ),
            cell_data=raw,
            scene_path=scene_path,
        )

    def _transactional_replace(self, root: Path, candidates: Mapping[Path, bytes]) -> None:
        journal_path = root / RECOVERY_FILE
        originals: dict[Path, bytes | None] = {
            path: path.read_bytes() if path.exists() else None for path in candidates
        }
        journal_files: dict[str, dict[str, str | None]] = {}
        for path, content in candidates.items():
            original = originals[path]
            journal_files[path.relative_to(root).as_posix()] = {
                "before": base64.b64encode(original).decode("ascii")
                if isinstance(original, bytes)
                else None,
                "candidate_sha256": hashlib.sha256(content).hexdigest(),
            }
        journal = {
            "version": 1,
            "files": journal_files,
        }
        temporary: list[Path] = []
        created_directories: list[Path] = []
        try:
            _write_temporary(journal_path, _json_bytes(journal), temporary, os.replace)
            prepared: dict[Path, Path] = {}
            for target, content in candidates.items():
                if not target.parent.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    created_directories.append(target.parent)
                prepared[target] = _prepare_temporary(target, content, temporary)
            for target, source in prepared.items():
                self._replace_file(source, target)
                temporary.remove(source)
            journal_path.unlink(missing_ok=True)
        except Exception as error:
            try:
                for target, original_content in originals.items():
                    if original_content is None:
                        target.unlink(missing_ok=True)
                    else:
                        _write_temporary(target, original_content, temporary, os.replace)
                journal_path.unlink(missing_ok=True)
            except Exception as rollback_error:
                raise ProjectSaveError(
                    f"Project save failed and requires explicit recovery from {journal_path}."
                ) from rollback_error
            raise ProjectSaveError(
                "Project save failed; the previous cell.yaml and USD scene were restored."
            ) from error
        finally:
            for path in temporary:
                path.unlink(missing_ok=True)
            for directory in reversed(created_directories):
                try:
                    directory.rmdir()
                except OSError:
                    pass

    def _validate_candidate_tree(
        self,
        root: Path,
        contents: ProjectContents,
        scene_reference: str,
    ) -> tuple[ValidationItem, ...]:
        with tempfile.TemporaryDirectory(prefix="cellforge-studio-validation-") as temporary:
            staged = Path(temporary) / "project"
            shutil.copytree(
                root,
                staged,
                ignore=shutil.ignore_patterns(RECOVERY_FILE, ".git", "__pycache__"),
            )
            (staged / "cell.yaml").write_text(
                contents.cell_yaml,
                encoding="utf-8",
                newline="\n",
            )
            staged_scene = _contained_scene_path(staged, scene_reference)
            if staged_scene is None:
                return (
                    ValidationItem(
                        code="studio.scene-reference-outside-project",
                        severity="error",
                        path=f"{root / 'cell.yaml'}#/scene/usd",
                        message="The canonical scene reference must remain inside the project.",
                    ),
                )
            staged_scene.write_text(contents.scene_usda, encoding="utf-8", newline="\n")
            for relative, content in contents.artifacts.items():
                target = (staged / relative).resolve()
                if not target.is_relative_to(staged):
                    return (
                        ValidationItem(
                            code="studio.artifact-path-invalid",
                            severity="error",
                            path=f"{root}#",
                            message="Staged artifact paths must remain inside the project.",
                        ),
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            report = validate_project(staged, self._registry_for(staged))
            staged_prefix = str(staged.resolve())
            root_prefix = str(root.resolve())
            return tuple(
                ValidationItem(
                    code=str(finding.code),
                    severity=finding.severity.value,
                    path=finding.path.replace(staged_prefix, root_prefix, 1),
                    message=finding.message,
                )
                for finding in report.findings
            )

    def _resolve_recovery(self, root: Path) -> None:
        journal_path = root / RECOVERY_FILE
        if not journal_path.exists():
            return
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            files = journal["files"]
            if not isinstance(files, Mapping):
                raise ValueError
            candidates_complete = bool(files)
            for relative, metadata in files.items():
                if not isinstance(relative, str) or not isinstance(metadata, Mapping):
                    raise ValueError
                target = (root / relative).resolve()
                if not target.is_relative_to(root):
                    raise ValueError
                try:
                    matches = hashlib.sha256(target.read_bytes()).hexdigest() == str(
                        metadata["candidate_sha256"]
                    )
                except OSError:
                    matches = False
                candidates_complete = candidates_complete and matches
            if candidates_complete:
                journal_path.unlink()
                return
            for relative, metadata in files.items():
                if not isinstance(relative, str) or not isinstance(metadata, Mapping):
                    raise ValueError
                target = (root / relative).resolve()
                if not target.is_relative_to(root):
                    raise ValueError
                before = metadata["before"]
                if before is None:
                    target.unlink(missing_ok=True)
                else:
                    decoded = base64.b64decode(str(before), validate=True)
                    temporary: list[Path] = []
                    _write_temporary(target, decoded, temporary, os.replace)
            journal_path.unlink()
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ProjectSaveError(
                f"Could not resolve the project recovery journal at {journal_path}."
            ) from error


def _parse_cell_candidate(
    text: str,
    cell_path: Path,
    registry: SchemaRegistry,
) -> _ParsedCell | tuple[ValidationItem, ...]:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError:
        return (
            ValidationItem(
                code="source.parse-failed",
                severity="error",
                path=f"{cell_path}#",
                message="Document syntax is invalid.",
            ),
        )
    if not isinstance(raw, Mapping):
        return (
            ValidationItem(
                code="source.root-not-object",
                severity="error",
                path=f"{cell_path}#",
                message="Document root must be an object.",
            ),
        )
    document = dict(raw)
    schema_findings = registry.validate(SchemaDocumentKind.CELL, document, cell_path)
    if schema_findings:
        return tuple(_validation_item(item) for item in schema_findings)
    try:
        model = CellProject.model_validate(document)
    except ValidationError as error:
        return tuple(
            ValidationItem(
                code=f"model.{str(item['type']).replace('_', '-')}",
                severity="error",
                path=f"{cell_path}#/{'/'.join(str(part) for part in item['loc'])}",
                message=str(item["msg"]),
            )
            for item in error.errors(
                include_context=False,
                include_input=False,
                include_url=False,
            )
        )
    return _ParsedCell(model=model, data=raw)


def _scene_reference(cell: Mapping[str, Any]) -> str | None:
    scene = cell.get("scene")
    if not isinstance(scene, Mapping):
        return None
    reference = scene.get("usd")
    return reference if isinstance(reference, str) else None


def _contained_scene_path(root: Path, reference: str | None) -> Path | None:
    if reference is None:
        return None
    raw = Path(reference)
    target = (root / raw).resolve()
    if raw.is_absolute() or not target.is_relative_to(root):
        return None
    return target


def _backend_project(summary: ProjectSummary) -> BackendProject:
    return BackendProject(
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
    )


def _summary_from_model(root: Path, cell: CellProject) -> BackendProject:
    return BackendProject(
        path=root,
        cell_id=str(cell.cell.id),
        name=cell.cell.name,
        scene=cell.scene.usd,
        component_count=len(cell.components),
        connection_count=len(cell.connections),
        task_count=len(cell.tasks),
        recipe_count=len(cell.recipes),
        scenario_count=len(cell.scenarios),
        deployment_profile_count=len(cell.deployment_profiles),
    )


def _validation_item(finding: ValidationFinding) -> ValidationItem:
    return ValidationItem(
        code=str(finding.code),
        severity=finding.severity.value,
        path=finding.path,
        message=finding.message,
    )


def _remap_backend_result(
    result: BackendResult, source_root: Path, destination_root: Path
) -> BackendResult:
    """Map validation paths from an isolated candidate tree to its future destination."""

    source_prefix = str(source_root.resolve())
    destination_prefix = str(destination_root.resolve())
    return BackendResult(
        project=None,
        validation=tuple(
            ValidationItem(
                code=item.code,
                severity=item.severity,
                path=item.path.replace(source_prefix, destination_prefix, 1),
                message=item.message,
            )
            for item in result.validation
        ),
    )


def _unique_findings(findings: list[ValidationItem]) -> tuple[ValidationItem, ...]:
    unique = {(item.code, item.severity, item.path, item.message): item for item in findings}
    return tuple(sorted(unique.values(), key=lambda item: (item.path, item.code, item.message)))


def _prepare_temporary(target: Path, content: bytes, tracked: list[Path]) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.cellforge-", dir=target.parent)
    temporary = Path(name)
    tracked.append(temporary)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return temporary


def _write_temporary(
    target: Path,
    content: bytes,
    tracked: list[Path],
    replace: Callable[[str | Path, str | Path], None],
) -> None:
    temporary = _prepare_temporary(target, content, tracked)
    replace(temporary, target)
    tracked.remove(temporary)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _artifact_candidates(
    root: Path, artifacts: Mapping[str, bytes]
) -> dict[Path, bytes] | BackendResult:
    """Resolve only project-contained staged immutable artifact paths."""

    candidates: dict[Path, bytes] = {}
    for relative, content in artifacts.items():
        target = (root / relative).resolve()
        if (
            Path(relative).is_absolute()
            or not target.is_relative_to(root)
            or target.suffix.lower() not in {".json", ".xml", ".yaml", ".yml"}
            or not isinstance(content, bytes)
        ):
            return BackendResult(
                project=None,
                validation=(
                    ValidationItem(
                        code="studio.artifact-path-invalid",
                        severity="error",
                        path=f"{root}#",
                        message="Staged artifact paths and content must remain inside the project.",
                    ),
                ),
            )
        candidates[target] = content
    return candidates


def _read_calibration_artifacts(root: Path, cell: Mapping[str, Any]) -> dict[str, bytes]:
    """Load existing declared immutable calibration bytes into reopened working state."""

    artifacts: dict[str, bytes] = {}
    paths = cell.get("calibrations", [])
    if not isinstance(paths, list):
        return artifacts
    for relative in paths:
        if not isinstance(relative, str):
            continue
        path = (root / relative).resolve()
        try:
            if not path.is_relative_to(root) or not path.is_file():
                continue
            artifacts[relative] = path.read_bytes()
        except OSError:
            continue
    return artifacts
