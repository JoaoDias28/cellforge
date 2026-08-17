"""Pure schema-driven recipe authoring, lifecycle, versioning, and diffing service."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from cellforge_cli.projects import resolve_project_schema_directory
from cellforge_domain import (
    FilesystemComponentRegistry,
    Recipe,
    SchemaRegistry,
)
from pydantic import ValidationError

from cellforge.studio.application import ProjectContents, ValidationItem


class RecipeStatusEnum(StrEnum):
    """Lifecycle states for process recipes."""

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    TESTED = "TESTED"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class RecipeFieldMeta:
    """Declared metadata for schema-driven forms with units and limits."""

    path: str
    field_type: str
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class RecipeSummary:
    """High-level summary of one recipe version."""

    id: str
    version: int
    name: str
    status: str
    path: str
    schema_path: str
    required_capabilities: tuple[str, ...]
    parameter_count: int
    is_immutable: bool
    valid: bool


@dataclass(frozen=True, slots=True)
class RecipeDetail:
    """Full recipe data with form schema metadata and validation findings."""

    summary: RecipeSummary
    data: Mapping[str, Any]
    field_metadata: tuple[RecipeFieldMeta, ...]
    validation: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class RecipeDiffEntry:
    """One atomic difference between two recipe versions."""

    section: str
    key: str
    old_value: Any
    new_value: Any
    change_type: str  # "added" | "removed" | "modified"


@dataclass(frozen=True, slots=True)
class RecipeDiffResult:
    """Structured comparison between two recipe versions."""

    recipe_id: str
    version_a: int
    version_b: int
    differences: tuple[RecipeDiffEntry, ...]
    is_breaking: bool


@dataclass(frozen=True, slots=True)
class RecipeBrowserResult:
    """Result of querying all recipes bound in a project."""

    recipes: tuple[RecipeSummary, ...]
    validation: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class RecipeEditResult:
    """Result of modifying, versioning, or transitioning a recipe in memory."""

    contents: ProjectContents | None
    recipe_id: str | None = None
    version: int | None = None
    path: str | None = None
    validation: tuple[ValidationItem, ...] = ()
    recipe: RecipeDetail | None = None


DEFAULT_RECIPE_FIELD_METADATA: tuple[RecipeFieldMeta, ...] = (
    RecipeFieldMeta("recipe.name", "string", description="Human-readable recipe name"),
    RecipeFieldMeta("recipe.status", "string", description="Lifecycle state"),
    RecipeFieldMeta("product.sku", "string", description="Product SKU code"),
    RecipeFieldMeta("product.material", "string", description="Material classification"),
    RecipeFieldMeta(
        "parameters.robot_speed_scale",
        "number",
        unit="scale",
        minimum=0.01,
        maximum=1.0,
        description="Global robot velocity scaling factor",
    ),
    RecipeFieldMeta("parameters.laser_program", "string", description="Process program identifier"),
    RecipeFieldMeta("parameters.fixture_id", "string", description="Target fixture identifier"),
    RecipeFieldMeta(
        "parameters.engraving_frame", "string", description="Reference frame for engraving"
    ),
    RecipeFieldMeta(
        "limits.max_pose_correction_mm",
        "number",
        unit="mm",
        minimum=0.0,
        description="Maximum allowed translational adjustment",
    ),
    RecipeFieldMeta(
        "limits.max_rotation_correction_deg",
        "number",
        unit="deg",
        minimum=0.0,
        description="Maximum allowed rotational adjustment",
    ),
    RecipeFieldMeta(
        "limits.max_text_length",
        "integer",
        unit="characters",
        minimum=1,
        description="Maximum input text character count",
    ),
    RecipeFieldMeta(
        "timeouts.locate", "number", unit="s", minimum=0.1, description="Locate timeout"
    ),
    RecipeFieldMeta(
        "timeouts.robot_motion", "number", unit="s", minimum=0.1, description="Motion timeout"
    ),
    RecipeFieldMeta(
        "timeouts.fixture", "number", unit="s", minimum=0.1, description="Fixture timeout"
    ),
    RecipeFieldMeta(
        "timeouts.process", "number", unit="s", minimum=0.1, description="Process timeout"
    ),
    RecipeFieldMeta(
        "timeouts.inspection", "number", unit="s", minimum=0.1, description="Inspection timeout"
    ),
    RecipeFieldMeta(
        "retry_policy.locate_attempts",
        "integer",
        unit="attempts",
        minimum=0,
        description="Vision retry attempts",
    ),
    RecipeFieldMeta(
        "retry_policy.pick_attempts",
        "integer",
        unit="attempts",
        minimum=0,
        description="Grasp retry attempts",
    ),
    RecipeFieldMeta(
        "retry_policy.process_attempts",
        "integer",
        unit="attempts",
        minimum=0,
        description="Process retry attempts",
    ),
    RecipeFieldMeta(
        "inspection.minimum_contrast",
        "number",
        unit="ratio",
        minimum=0.0,
        maximum=1.0,
        description="Minimum visual contrast ratio",
    ),
    RecipeFieldMeta(
        "inspection.text_must_match",
        "boolean",
        description="Strict optical character recognition verification",
    ),
)


VALID_TRANSITIONS: dict[RecipeStatusEnum, set[RecipeStatusEnum]] = {
    RecipeStatusEnum.DRAFT: {RecipeStatusEnum.VALIDATED},
    RecipeStatusEnum.VALIDATED: {RecipeStatusEnum.DRAFT, RecipeStatusEnum.TESTED},
    RecipeStatusEnum.TESTED: {RecipeStatusEnum.DRAFT, RecipeStatusEnum.APPROVED},
    RecipeStatusEnum.APPROVED: {RecipeStatusEnum.RETIRED},
    RecipeStatusEnum.RETIRED: set(),
}


class RecipeAuthoringService:
    """Pure domain service for recipe forms, validation, diffing, and immutable versioning."""

    def __init__(self, canonical_schema_directory: Path) -> None:
        self._canonical_schemas = canonical_schema_directory.resolve()

    def browse(
        self,
        project_path: Path,
        contents: ProjectContents,
    ) -> RecipeBrowserResult:
        """Discover and summarize all recipe versions bound to the project."""
        root = project_path.resolve()
        registry = SchemaRegistry.from_directory(
            resolve_project_schema_directory(root, self._canonical_schemas)
        )

        try:
            cell_data = yaml.safe_load(contents.cell_yaml)
        except (yaml.YAMLError, UnicodeError):
            return RecipeBrowserResult(
                recipes=(),
                validation=(
                    ValidationItem(
                        code="studio.recipe.cell_yaml_invalid",
                        severity="error",
                        path=f"{root / 'cell.yaml'}#",
                        message="cell.yaml could not be parsed.",
                    ),
                ),
            )

        if not isinstance(cell_data, dict):
            return RecipeBrowserResult(recipes=(), validation=())

        raw_recipes = cell_data.get("recipes", [])
        if not isinstance(raw_recipes, list):
            raw_recipes = []

        summaries: list[RecipeSummary] = []
        validation_items: list[ValidationItem] = []

        for binding in raw_recipes:
            if not isinstance(binding, dict):
                continue
            schema_ref = str(binding.get("schema", "schemas/recipe.schema.json"))
            recipe_rel_path = str(binding.get("path", ""))
            if not recipe_rel_path:
                continue

            raw_text = None
            if recipe_rel_path in contents.artifacts:
                try:
                    raw_text = contents.artifacts[recipe_rel_path].decode("utf-8")
                except UnicodeError:
                    pass
            elif (root / recipe_rel_path).is_file():
                try:
                    raw_text = (root / recipe_rel_path).read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    pass

            if raw_text is None:
                summaries.append(
                    RecipeSummary(
                        id="unknown",
                        version=0,
                        name=recipe_rel_path,
                        status="UNKNOWN",
                        path=recipe_rel_path,
                        schema_path=schema_ref,
                        required_capabilities=(),
                        parameter_count=0,
                        is_immutable=False,
                        valid=False,
                    )
                )
                validation_items.append(
                    ValidationItem(
                        code="studio.recipe.file_missing",
                        severity="error",
                        path=f"{root / recipe_rel_path}#",
                        message=f"Recipe document '{recipe_rel_path}' could not be read.",
                    )
                )
                continue

            try:
                recipe_data = yaml.safe_load(raw_text)
                if not isinstance(recipe_data, dict):
                    raise ValueError("Recipe document root must be a mapping")

                rec_info = recipe_data.get("recipe", {})
                rec_id = str(rec_info.get("id", "unnamed"))
                rec_version = int(rec_info.get("version", 1))
                rec_name = str(rec_info.get("name", rec_id))
                rec_status = str(rec_info.get("status", "DRAFT"))

                compat = recipe_data.get("compatibility", {})
                req_caps = tuple(str(c) for c in compat.get("required_capabilities", []))
                param_count = len(recipe_data.get("parameters", {}))
                is_imm = rec_status in {RecipeStatusEnum.APPROVED, RecipeStatusEnum.RETIRED}

                findings = self.validate_recipe_data(
                    recipe_data,
                    registry=registry,
                    cell_data=cell_data,
                    project_root=root,
                    recipe_path=root / recipe_rel_path,
                )
                validation_items.extend(findings)

                summaries.append(
                    RecipeSummary(
                        id=rec_id,
                        version=rec_version,
                        name=rec_name,
                        status=rec_status,
                        path=recipe_rel_path,
                        schema_path=schema_ref,
                        required_capabilities=req_caps,
                        parameter_count=param_count,
                        is_immutable=is_imm,
                        valid=len(findings) == 0,
                    )
                )
            except Exception as e:
                summaries.append(
                    RecipeSummary(
                        id="invalid",
                        version=0,
                        name=recipe_rel_path,
                        status="ERROR",
                        path=recipe_rel_path,
                        schema_path=schema_ref,
                        required_capabilities=(),
                        parameter_count=0,
                        is_immutable=False,
                        valid=False,
                    )
                )
                validation_items.append(
                    ValidationItem(
                        code="studio.recipe.parse_failed",
                        severity="error",
                        path=f"{root / recipe_rel_path}#",
                        message=f"Failed to parse recipe '{recipe_rel_path}': {e}",
                    )
                )

        return RecipeBrowserResult(
            recipes=tuple(summaries),
            validation=tuple(validation_items),
        )

    def inspect_recipe(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int | None = None,
    ) -> RecipeDetail | None:
        """Return detailed fields and form metadata for a specific recipe version."""
        browser = self.browse(project_path, contents)
        target_summary = None
        for s in browser.recipes:
            if s.id == recipe_id:
                if version is None or s.version == version:
                    target_summary = s
                    break

        if target_summary is None:
            return None

        root = project_path.resolve()
        raw_text = None
        if target_summary.path in contents.artifacts:
            raw_text = contents.artifacts[target_summary.path].decode("utf-8")
        elif (root / target_summary.path).is_file():
            raw_text = (root / target_summary.path).read_text(encoding="utf-8")

        if raw_text is None:
            return None

        recipe_data = yaml.safe_load(raw_text)
        registry = SchemaRegistry.from_directory(
            resolve_project_schema_directory(root, self._canonical_schemas)
        )
        cell_data = yaml.safe_load(contents.cell_yaml)
        findings = self.validate_recipe_data(
            recipe_data,
            registry=registry,
            cell_data=cell_data,
            project_root=root,
            recipe_path=root / target_summary.path,
        )

        return RecipeDetail(
            summary=target_summary,
            data=recipe_data,
            field_metadata=DEFAULT_RECIPE_FIELD_METADATA,
            validation=findings,
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
        """Edit an existing draft recipe. Refuses direct editing of released/retired versions."""
        root = project_path.resolve()
        registry = SchemaRegistry.from_directory(
            resolve_project_schema_directory(root, self._canonical_schemas)
        )
        browser = self.browse(project_path, contents)

        target_summary = None
        for s in browser.recipes:
            if s.id == recipe_id and s.version == version:
                target_summary = s
                break

        if target_summary is None:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=version,
                validation=(
                    ValidationItem(
                        code="studio.recipe.not_found",
                        severity="error",
                        path=f"{root}#",
                        message=f"Recipe '{recipe_id}' version {version} not found in project.",
                    ),
                ),
            )

        if target_summary.is_immutable:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=version,
                path=target_summary.path,
                validation=(
                    ValidationItem(
                        code="studio.recipe.released_immutable",
                        severity="error",
                        path=f"{root / target_summary.path}#/recipe/status",
                        message=(
                            f"Recipe '{recipe_id}' version {version} is "
                            f"{target_summary.status} and immutable. "
                            "Create a new recipe version to make modifications."
                        ),
                    ),
                ),
            )

        # Mutate draft data
        updated_data = copy.deepcopy(dict(data))
        # Ensure recipe id and version are preserved
        if "recipe" not in updated_data or not isinstance(updated_data["recipe"], dict):
            updated_data["recipe"] = {}
        updated_data["recipe"]["id"] = recipe_id
        updated_data["recipe"]["version"] = version

        # If previously VALIDATED or TESTED, reset to DRAFT upon data modification
        current_status = target_summary.status
        if current_status in {RecipeStatusEnum.VALIDATED, RecipeStatusEnum.TESTED}:
            updated_data["recipe"]["status"] = RecipeStatusEnum.DRAFT.value

        cell_data = yaml.safe_load(contents.cell_yaml)
        findings = self.validate_recipe_data(
            updated_data,
            registry=registry,
            cell_data=cell_data,
            project_root=root,
            recipe_path=root / target_summary.path,
        )

        if any(f.severity == "error" for f in findings):
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=version,
                path=target_summary.path,
                validation=findings,
            )

        new_yaml = yaml.safe_dump(updated_data, sort_keys=False)
        new_artifacts = dict(contents.artifacts)
        new_artifacts[target_summary.path] = new_yaml.encode("utf-8")

        new_contents = ProjectContents(
            cell_yaml=contents.cell_yaml,
            scene_usda=contents.scene_usda,
            artifacts=new_artifacts,
        )

        new_summary = RecipeSummary(
            id=recipe_id,
            version=version,
            name=str(updated_data["recipe"].get("name", target_summary.name)),
            status=str(updated_data["recipe"].get("status", "DRAFT")),
            path=target_summary.path,
            schema_path=target_summary.schema_path,
            required_capabilities=tuple(
                str(c)
                for c in updated_data.get("compatibility", {}).get("required_capabilities", [])
            ),
            parameter_count=len(updated_data.get("parameters", {})),
            is_immutable=False,
            valid=len(findings) == 0,
        )

        return RecipeEditResult(
            contents=new_contents,
            recipe_id=recipe_id,
            version=version,
            path=target_summary.path,
            validation=findings,
            recipe=RecipeDetail(
                summary=new_summary,
                data=updated_data,
                field_metadata=DEFAULT_RECIPE_FIELD_METADATA,
                validation=findings,
            ),
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
        """Create a new draft version of a recipe without mutating its predecessor."""
        root = project_path.resolve()
        registry = SchemaRegistry.from_directory(
            resolve_project_schema_directory(root, self._canonical_schemas)
        )
        browser = self.browse(project_path, contents)

        matching = [s for s in browser.recipes if s.id == recipe_id]
        if not matching:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                validation=(
                    ValidationItem(
                        code="studio.recipe.not_found",
                        severity="error",
                        path=f"{root}#",
                        message=f"Recipe '{recipe_id}' does not exist to version.",
                    ),
                ),
            )

        if base_version is not None:
            base_summary = next((s for s in matching if s.version == base_version), None)
        else:
            base_summary = max(matching, key=lambda s: s.version)

        if base_summary is None:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=base_version,
                validation=(
                    ValidationItem(
                        code="studio.recipe.base_version_not_found",
                        severity="error",
                        path=f"{root}#",
                        message=f"Base version {base_version} for recipe '{recipe_id}' not found.",
                    ),
                ),
            )

        raw_base_text = None
        if base_summary.path in contents.artifacts:
            raw_base_text = contents.artifacts[base_summary.path].decode("utf-8")
        elif (root / base_summary.path).is_file():
            raw_base_text = (root / base_summary.path).read_text(encoding="utf-8")

        if raw_base_text is None:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                validation=(
                    ValidationItem(
                        code="studio.recipe.read_failed",
                        severity="error",
                        path=f"{root / base_summary.path}#",
                        message="Base recipe source could not be read.",
                    ),
                ),
            )

        base_data = yaml.safe_load(raw_base_text)
        new_data = copy.deepcopy(base_data)

        new_version_num = max(s.version for s in matching) + 1
        new_data["recipe"]["version"] = new_version_num
        new_data["recipe"]["status"] = RecipeStatusEnum.DRAFT.value

        if overrides:
            for k, v in overrides.items():
                if isinstance(v, Mapping) and k in new_data and isinstance(new_data[k], dict):
                    new_data[k].update(v)
                else:
                    new_data[k] = v

        # Determine target file path
        base_path = Path(base_summary.path)
        if base_path.parent == Path("."):
            new_rel_path = f"recipes/{recipe_id}_v{new_version_num}.yaml"
        else:
            new_rel_path = f"{base_path.parent.as_posix()}/{recipe_id}_v{new_version_num}.yaml"

        cell_data = yaml.safe_load(contents.cell_yaml)
        findings = self.validate_recipe_data(
            new_data,
            registry=registry,
            cell_data=cell_data,
            project_root=root,
            recipe_path=root / new_rel_path,
        )

        if any(f.severity == "error" for f in findings):
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=new_version_num,
                path=new_rel_path,
                validation=findings,
            )

        # Stage artifact
        new_yaml = yaml.safe_dump(new_data, sort_keys=False)
        new_artifacts = dict(contents.artifacts)
        new_artifacts[new_rel_path] = new_yaml.encode("utf-8")

        # Update cell.yaml recipes list to include the new version binding
        updated_cell_data = copy.deepcopy(cell_data)
        recipes_list = updated_cell_data.setdefault("recipes", [])
        recipes_list.append(
            {
                "schema": base_summary.schema_path,
                "path": new_rel_path,
            }
        )
        new_cell_yaml = yaml.safe_dump(updated_cell_data, sort_keys=False)

        new_contents = ProjectContents(
            cell_yaml=new_cell_yaml,
            scene_usda=contents.scene_usda,
            artifacts=new_artifacts,
        )

        new_summary = RecipeSummary(
            id=recipe_id,
            version=new_version_num,
            name=str(new_data["recipe"].get("name", base_summary.name)),
            status=RecipeStatusEnum.DRAFT,
            path=new_rel_path,
            schema_path=base_summary.schema_path,
            required_capabilities=tuple(
                str(c) for c in new_data.get("compatibility", {}).get("required_capabilities", [])
            ),
            parameter_count=len(new_data.get("parameters", {})),
            is_immutable=False,
            valid=len(findings) == 0,
        )

        return RecipeEditResult(
            contents=new_contents,
            recipe_id=recipe_id,
            version=new_version_num,
            path=new_rel_path,
            validation=findings,
            recipe=RecipeDetail(
                summary=new_summary,
                data=new_data,
                field_metadata=DEFAULT_RECIPE_FIELD_METADATA,
                validation=findings,
            ),
        )

    def transition_lifecycle(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        recipe_id: str,
        version: int,
        target_status: str,
        evidence: Sequence[str] | None = None,
    ) -> RecipeEditResult:
        """Transition a recipe version to a new lifecycle state if valid."""
        root = project_path.resolve()
        registry = SchemaRegistry.from_directory(
            resolve_project_schema_directory(root, self._canonical_schemas)
        )
        browser = self.browse(project_path, contents)

        target_summary = None
        for s in browser.recipes:
            if s.id == recipe_id and s.version == version:
                target_summary = s
                break

        if target_summary is None:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=version,
                validation=(
                    ValidationItem(
                        code="studio.recipe.not_found",
                        severity="error",
                        path=f"{root}#",
                        message=f"Recipe '{recipe_id}' version {version} not found in project.",
                    ),
                ),
            )

        current_status_enum = RecipeStatusEnum(target_summary.status)
        try:
            target_status_enum = RecipeStatusEnum(target_status)
        except ValueError:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=version,
                validation=(
                    ValidationItem(
                        code="studio.recipe.invalid_lifecycle_status",
                        severity="error",
                        path=f"{root / target_summary.path}#/recipe/status",
                        message=f"Invalid target recipe status '{target_status}'.",
                    ),
                ),
            )

        allowed = VALID_TRANSITIONS.get(current_status_enum, set())
        if target_status_enum not in allowed:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=version,
                validation=(
                    ValidationItem(
                        code="studio.recipe.disallowed_lifecycle_transition",
                        severity="error",
                        path=f"{root / target_summary.path}#/recipe/status",
                        message=(
                            f"Cannot transition recipe from '{current_status_enum}' "
                            f"to '{target_status_enum}'. "
                            f"Allowed transitions: {[s.value for s in allowed]}"
                        ),
                    ),
                ),
            )

        # Load recipe data
        raw_text = None
        if target_summary.path in contents.artifacts:
            raw_text = contents.artifacts[target_summary.path].decode("utf-8")
        elif (root / target_summary.path).is_file():
            raw_text = (root / target_summary.path).read_text(encoding="utf-8")

        if raw_text is None:
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                validation=(
                    ValidationItem(
                        code="studio.recipe.read_failed",
                        severity="error",
                        path=f"{root / target_summary.path}#",
                        message="Recipe source could not be read.",
                    ),
                ),
            )

        recipe_data = yaml.safe_load(raw_text)
        updated_data = copy.deepcopy(recipe_data)

        # Handle TESTED/APPROVED requirement: evidence attached
        if target_status_enum in {RecipeStatusEnum.TESTED, RecipeStatusEnum.APPROVED}:
            if evidence:
                updated_data.setdefault("approval", {})["evidence"] = list(evidence)
            app_evidence = updated_data.get("approval", {}).get("evidence", [])
            if not app_evidence:
                return RecipeEditResult(
                    contents=None,
                    recipe_id=recipe_id,
                    version=version,
                    validation=(
                        ValidationItem(
                            code="studio.recipe.requires_evidence",
                            severity="error",
                            path=f"{root / target_summary.path}#/approval/evidence",
                            message=(
                                f"Transition to {target_status_enum.value} "
                                "requires simulation or test scenario evidence."
                            ),
                        ),
                    ),
                )

        updated_data["recipe"]["status"] = target_status_enum.value

        cell_data = yaml.safe_load(contents.cell_yaml)
        findings = self.validate_recipe_data(
            updated_data,
            registry=registry,
            cell_data=cell_data,
            project_root=root,
            recipe_path=root / target_summary.path,
        )

        if any(f.severity == "error" for f in findings):
            return RecipeEditResult(
                contents=None,
                recipe_id=recipe_id,
                version=version,
                path=target_summary.path,
                validation=findings,
            )

        new_yaml = yaml.safe_dump(updated_data, sort_keys=False)
        new_artifacts = dict(contents.artifacts)
        new_artifacts[target_summary.path] = new_yaml.encode("utf-8")

        new_contents = ProjectContents(
            cell_yaml=contents.cell_yaml,
            scene_usda=contents.scene_usda,
            artifacts=new_artifacts,
        )

        is_imm = target_status_enum in {RecipeStatusEnum.APPROVED, RecipeStatusEnum.RETIRED}
        new_summary = RecipeSummary(
            id=recipe_id,
            version=version,
            name=str(updated_data["recipe"].get("name", target_summary.name)),
            status=target_status_enum.value,
            path=target_summary.path,
            schema_path=target_summary.schema_path,
            required_capabilities=target_summary.required_capabilities,
            parameter_count=target_summary.parameter_count,
            is_immutable=is_imm,
            valid=len(findings) == 0,
        )

        return RecipeEditResult(
            contents=new_contents,
            recipe_id=recipe_id,
            version=version,
            path=target_summary.path,
            validation=findings,
            recipe=RecipeDetail(
                summary=new_summary,
                data=updated_data,
                field_metadata=DEFAULT_RECIPE_FIELD_METADATA,
                validation=findings,
            ),
        )

    def diff(
        self,
        recipe_a: Mapping[str, Any],
        recipe_b: Mapping[str, Any],
    ) -> RecipeDiffResult:
        """Compute structured semantic differences between two recipe versions."""
        rec_id_a = recipe_a.get("recipe", {}).get("id", "unknown")
        ver_a = int(recipe_a.get("recipe", {}).get("version", 1))
        ver_b = int(recipe_b.get("recipe", {}).get("version", 1))

        diffs: list[RecipeDiffEntry] = []
        is_breaking = False

        sections = [
            "recipe",
            "compatibility",
            "product",
            "parameters",
            "limits",
            "timeouts",
            "retry_policy",
            "inspection",
            "traceability",
            "approval",
        ]

        for sec in sections:
            sec_a = recipe_a.get(sec, {})
            sec_b = recipe_b.get(sec, {})
            if not isinstance(sec_a, dict) or not isinstance(sec_b, dict):
                if sec_a != sec_b:
                    diffs.append(
                        RecipeDiffEntry(
                            section=sec,
                            key=sec,
                            old_value=sec_a,
                            new_value=sec_b,
                            change_type="modified",
                        )
                    )
                continue

            all_keys = set(sec_a.keys()) | set(sec_b.keys())
            for k in sorted(all_keys):
                if k not in sec_a:
                    diffs.append(
                        RecipeDiffEntry(
                            section=sec,
                            key=k,
                            old_value=None,
                            new_value=sec_b[k],
                            change_type="added",
                        )
                    )
                    if sec == "compatibility":
                        is_breaking = True
                elif k not in sec_b:
                    diffs.append(
                        RecipeDiffEntry(
                            section=sec,
                            key=k,
                            old_value=sec_a[k],
                            new_value=None,
                            change_type="removed",
                        )
                    )
                    if sec in {"compatibility", "limits", "inspection"}:
                        is_breaking = True
                elif sec_a[k] != sec_b[k]:
                    diffs.append(
                        RecipeDiffEntry(
                            section=sec,
                            key=k,
                            old_value=sec_a[k],
                            new_value=sec_b[k],
                            change_type="modified",
                        )
                    )
                    if sec == "product" and k in {"material", "sku"}:
                        is_breaking = True
                    elif sec == "limits":
                        is_breaking = True
                    elif sec == "compatibility":
                        is_breaking = True
                    elif sec == "inspection" and k in {"method", "minimum_contrast"}:
                        is_breaking = True

        return RecipeDiffResult(
            recipe_id=rec_id_a,
            version_a=ver_a,
            version_b=ver_b,
            differences=tuple(diffs),
            is_breaking=is_breaking,
        )

    def validate_recipe_data(
        self,
        data: Mapping[str, Any],
        *,
        registry: SchemaRegistry,
        cell_data: Mapping[str, Any] | None = None,
        project_root: Path | None = None,
        recipe_path: Path | None = None,
    ) -> tuple[ValidationItem, ...]:
        """Validate recipe against canonical schema, parameter ranges, and cell capabilities."""
        findings: list[ValidationItem] = []
        path_str = str(recipe_path) if recipe_path else "recipe.yaml"

        # 1. Pydantic / JSON schema validation
        try:
            Recipe.model_validate(data)
        except ValidationError as error:
            for err in error.errors():
                loc = "/".join(str(p) for p in err["loc"])
                findings.append(
                    ValidationItem(
                        code="studio.recipe.schema_violation",
                        severity="error",
                        path=f"{path_str}#/{loc}",
                        message=err["msg"],
                    )
                )

        # 2. Field range / units check
        for meta in DEFAULT_RECIPE_FIELD_METADATA:
            parts = meta.path.split(".")
            curr: Any = data
            for part in parts:
                if isinstance(curr, dict) and part in curr:
                    curr = curr[part]
                else:
                    curr = None
                    break
            if curr is not None and isinstance(curr, (int, float)):
                if meta.minimum is not None and curr < meta.minimum:
                    findings.append(
                        ValidationItem(
                            code="studio.recipe.range_underflow",
                            severity="error",
                            path=f"{path_str}#/{meta.path.replace('.', '/')}",
                            message=(
                                f"Value {curr} is below minimum allowed "
                                f"{meta.minimum} {meta.unit or ''}."
                            ),
                        )
                    )
                if meta.maximum is not None and curr > meta.maximum:
                    findings.append(
                        ValidationItem(
                            code="studio.recipe.range_overflow",
                            severity="error",
                            path=f"{path_str}#/{meta.path.replace('.', '/')}",
                            message=(
                                f"Value {curr} exceeds maximum allowed "
                                f"{meta.maximum} {meta.unit or ''}."
                            ),
                        )
                    )

        # 3. Capability and cell compatibility checks
        if cell_data and isinstance(cell_data, dict):
            cell_info = cell_data.get("cell", {})
            cell_id = cell_info.get("id")
            compat = data.get("compatibility", {})
            compat_cell_ids = compat.get("cell_ids", [])
            if (
                compat_cell_ids
                and cell_id
                and str(cell_id) not in [str(i) for i in compat_cell_ids]
            ):
                findings.append(
                    ValidationItem(
                        code="studio.recipe.cell_incompatible",
                        severity="error",
                        path=f"{path_str}#/compatibility/cell_ids",
                        message=f"Recipe is not declared compatible with cell ID '{cell_id}'.",
                    )
                )

            # Placed components capabilities
            if project_root:
                comp_registry = FilesystemComponentRegistry.from_directory(
                    project_root / "components", schema_registry=registry
                )
                provided_caps: set[str] = set()
                raw_components = cell_data.get("components", [])
                for c in raw_components:
                    if isinstance(c, dict):
                        c_type = c.get("component")
                        c_ver = c.get("version")
                        if c_type and c_ver:
                            pkg = comp_registry.get(c_type, c_ver)
                            if pkg:
                                for cap in pkg.manifest.capabilities:
                                    provided_caps.add(cap.contract)

                req_caps = compat.get("required_capabilities", [])
                missing = sorted(set(req_caps) - provided_caps)
                if missing:
                    findings.append(
                        ValidationItem(
                            code="compiler.recipe-capability-unresolved",
                            severity="error",
                            path=f"{path_str}#/compatibility/required_capabilities",
                            message=(
                                f"Recipe requires unresolved capabilities: {', '.join(missing)}."
                            ),
                        )
                    )

        return tuple(findings)
