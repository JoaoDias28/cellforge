"""Deterministic, headless CellForge project compiler."""

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from cellforge_domain import (
    BundleCapabilityReference,
    BundleComponentReference,
    BundleEvidenceSummary,
    BundleFile,
    BundleManifest,
    BundleRecipeReference,
    BundleTaskReference,
    CellProject,
    ComponentType,
    DeploymentProfile,
    ExecutionMode,
    FilesystemComponentRegistry,
    FindingSeverity,
    Recipe,
    RecipeStatus,
    ResolutionReport,
    SchemaRegistry,
    SchemaRegistryError,
    SourceLoadError,
    ValidationFinding,
    load_document,
    resolve_cell,
    to_canonical_json,
)
from cellforge_domain.example_validation import validate_example_tree

from cellforge_bundle.models import CompilationReport, CompilerStage, StageResult, StageStatus

_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
_OPERATOR_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_USD_PRIM = re.compile(r'\b(?:def|over|class)\s+\w+\s+"([^"\\]+)"')
_STAGE_ORDER = tuple(CompilerStage)


@dataclass(slots=True)
class _CompilerState:
    mode: ExecutionMode
    target_profile: str
    attempted: set[CompilerStage] = field(default_factory=set)
    findings_by_stage: dict[CompilerStage, list[ValidationFinding]] = field(default_factory=dict)

    def attempt(self, stage: CompilerStage) -> None:
        self.attempted.add(stage)

    def add(self, stage: CompilerStage, finding: ValidationFinding) -> None:
        self.attempted.add(stage)
        self.findings_by_stage.setdefault(stage, []).append(finding)

    @property
    def findings(self) -> tuple[ValidationFinding, ...]:
        return tuple(
            sorted(
                (item for values in self.findings_by_stage.values() for item in values),
                key=_finding_sort_key,
            )
        )

    def has_errors(self) -> bool:
        return any(item.severity == FindingSeverity.ERROR for item in self.findings)

    @property
    def stages(self) -> tuple[StageResult, ...]:
        results: list[StageResult] = []
        for stage in _STAGE_ORDER:
            findings = self.findings_by_stage.get(stage, [])
            has_errors = any(item.severity == FindingSeverity.ERROR for item in findings)
            status = (
                StageStatus.SKIPPED
                if stage not in self.attempted
                else StageStatus.FAILED
                if has_errors
                else StageStatus.PASSED
            )
            results.append(
                StageResult(
                    stage=stage,
                    status=status,
                    finding_codes=tuple(sorted({item.code for item in findings})),
                )
            )
        return tuple(results)


@dataclass(slots=True)
class _FileInventory:
    state: _CompilerState
    sources: dict[str, Path] = field(default_factory=dict)

    def add(self, manifest_path: str, source_path: Path, stage: CompilerStage) -> None:
        normalized = Path(manifest_path).as_posix().lstrip("/")
        existing = self.sources.get(normalized)
        if existing is not None and existing != source_path:
            self.state.add(
                stage,
                _finding(
                    "compiler.bundle-path-collision",
                    f"manifest.json#/files/{normalized}",
                    f"Multiple source files map to bundle path '{normalized}'.",
                ),
            )
            return
        self.sources[normalized] = source_path

    def freeze(self) -> tuple[BundleFile, ...]:
        files: list[BundleFile] = []
        for manifest_path, source_path in sorted(self.sources.items()):
            content = _read_bytes(
                source_path,
                self.state,
                CompilerStage.MANIFEST,
                "compiler.bundle-source-unreadable",
            )
            if content is None:
                continue
            files.append(
                BundleFile(
                    path=manifest_path,
                    sha256=_sha256(content),
                    size=len(content),
                )
            )
        return tuple(files)


def compile_project(
    project: str | Path,
    schemas: str | Path,
    *,
    target_profile: str,
    mode: ExecutionMode,
    source_revision: str,
) -> CompilationReport:
    """Compile a source tree into an immutable plan without building or installing it."""

    state = _CompilerState(mode=mode, target_profile=target_profile)
    project_root = Path(project).resolve()
    cell_path = project_root / "cell.yaml"

    state.attempt(CompilerStage.SCHEMA)
    if not project_root.is_dir():
        state.add(
            CompilerStage.SCHEMA,
            _finding(
                "compiler.project-not-found",
                f"{project_root}#",
                "Project directory does not exist or is not a directory.",
            ),
        )
        return _report(state)
    if not cell_path.is_file():
        state.add(
            CompilerStage.SCHEMA,
            _finding(
                "compiler.cell-not-found",
                f"{cell_path}#",
                "Project does not contain cell.yaml.",
            ),
        )
        return _report(state)

    try:
        schema_registry = SchemaRegistry.from_directory(schemas)
    except SchemaRegistryError as error:
        state.add(
            CompilerStage.SCHEMA,
            _finding(
                "compiler.schema-registry-unavailable",
                f"{error.source_path.resolve()}#",
                error.message,
            ),
        )
        return _report(state)

    validation = validate_example_tree(project_root, schema_registry)
    for finding in validation.findings:
        state.add(CompilerStage.SCHEMA, finding)
    if state.has_errors():
        return _report(state)

    try:
        cell = load_document(cell_path, CellProject, schema_registry=schema_registry)
    except SourceLoadError as error:
        _add_load_error(state, CompilerStage.SCHEMA, error)
        return _report(state)

    if _GIT_REVISION.fullmatch(source_revision) is None:
        state.add(
            CompilerStage.MANIFEST,
            _finding(
                "compiler.source-revision-invalid",
                "manifest.json#/source_revision",
                "Source revision must be an exact lowercase 40-character Git commit hash.",
            ),
        )

    inventory = _FileInventory(state)
    inventory.add("config/cell.yaml", cell_path, CompilerStage.SCHEMA)
    _add_schema_files(inventory, schema_registry)

    profile, profile_path = _resolve_target_profile(
        project_root, cell_path, cell, schema_registry, state
    )

    state.attempt(CompilerStage.LINK)
    state.attempt(CompilerStage.CAPABILITY)
    component_registry = FilesystemComponentRegistry.from_directory(
        project_root / "components", schema_registry=schema_registry
    )
    resolution = resolve_cell(cell, component_registry, mode, source_name=str(cell_path))
    for finding in resolution.findings:
        stage = (
            CompilerStage.CAPABILITY
            if finding.code.startswith("resolver.capability")
            else CompilerStage.LINK
        )
        state.add(stage, finding)

    scene_path = _validate_spatial(project_root, cell_path, cell, state)
    if scene_path is not None:
        inventory.add(f"assets/{scene_path.name}", scene_path, CompilerStage.SPATIAL)

    tasks = _freeze_tasks(project_root, cell_path, cell, state, inventory)
    recipes = _freeze_recipes(
        project_root,
        cell_path,
        cell,
        schema_registry,
        resolution,
        mode,
        state,
        inventory,
    )
    components, adapter_packages = _freeze_components(
        cell,
        component_registry,
        mode,
        state,
        inventory,
    )
    _freeze_calibrations(project_root, cell_path, cell, state, inventory)
    _freeze_operator_recovery(project_root, state, inventory)

    state.attempt(CompilerStage.EVIDENCE)
    if mode == ExecutionMode.PRODUCTION:
        state.add(
            CompilerStage.EVIDENCE,
            _finding(
                "compiler.production-evidence-unverified",
                "evidence-summary.json#",
                (
                    "Production evidence is required, but evidence verification is not "
                    "implemented; compilation fails closed."
                ),
            ),
        )

    if profile is None or profile_path is None:
        return _report(state, resolution=resolution)

    inventory.add("config/target-profile.yaml", profile_path, CompilerStage.TARGET)
    files = inventory.freeze()
    if state.has_errors():
        return _report(state, resolution=resolution)

    state.attempt(CompilerStage.MANIFEST)
    native_packages = tuple(sorted(set(profile.runtime.native_packages) | adapter_packages))
    draft = BundleManifest(
        schema_version="0.1.0",
        bundle_id="0" * 64,
        source_revision=source_revision,
        cell_id=cell.cell.id,
        target_profile=profile.profile.id,
        execution_mode=mode,
        capabilities=tuple(
            BundleCapabilityReference(
                task_id=item.task_id,
                contract=item.contract,
                version=item.version,
                provider_instance=item.provider_instance,
                endpoint=item.endpoint,
            )
            for item in resolution.capabilities
        ),
        components=components,
        recipes=recipes,
        tasks=tasks,
        calibrations=tuple(sorted(cell.calibrations)),
        native_packages=native_packages,
        containers=tuple(sorted(profile.runtime.containers)),
        external_prerequisites=tuple(sorted(profile.external_prerequisites)),
        evidence=BundleEvidenceSummary(required=False, status="not-required"),
        files=files,
    )
    hash_input = draft.model_dump(mode="json", by_alias=True, exclude={"bundle_id"})
    canonical_hash_input = json.dumps(
        hash_input,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    manifest = draft.model_copy(update={"bundle_id": _sha256(canonical_hash_input)})
    return _report(
        state,
        resolution=resolution,
        manifest=manifest,
        manifest_json=to_canonical_json(manifest),
    )


def _resolve_target_profile(
    project_root: Path,
    cell_path: Path,
    cell: CellProject,
    schemas: SchemaRegistry,
    state: _CompilerState,
) -> tuple[DeploymentProfile | None, Path | None]:
    state.attempt(CompilerStage.TARGET)
    matches: list[tuple[DeploymentProfile, Path]] = []
    for index, reference in enumerate(cell.deployment_profiles):
        source = _project_reference(
            project_root,
            reference,
            state,
            CompilerStage.TARGET,
            f"{cell_path}#/deployment_profiles/{index}",
        )
        if source is None:
            continue
        try:
            profile = load_document(source, DeploymentProfile, schema_registry=schemas)
        except SourceLoadError as error:
            _add_load_error(state, CompilerStage.TARGET, error)
            continue
        if profile.profile.id == state.target_profile:
            matches.append((profile, source))

    if not matches:
        state.add(
            CompilerStage.TARGET,
            _finding(
                "compiler.target-profile-not-found",
                f"{cell_path}#/deployment_profiles",
                f"Target profile '{state.target_profile}' is not declared by the cell.",
            ),
        )
        return None, None
    if len(matches) > 1:
        state.add(
            CompilerStage.TARGET,
            _finding(
                "compiler.target-profile-ambiguous",
                f"{cell_path}#/deployment_profiles",
                f"Target profile '{state.target_profile}' is declared more than once.",
            ),
        )
        return None, None

    profile, source = matches[0]
    if state.mode not in profile.modes:
        state.add(
            CompilerStage.TARGET,
            _finding(
                "compiler.target-mode-unsupported",
                f"{source}#/modes",
                f"Target profile '{profile.profile.id}' does not permit '{state.mode.value}'.",
            ),
        )
    return profile, source


def _validate_spatial(
    project_root: Path,
    cell_path: Path,
    cell: CellProject,
    state: _CompilerState,
) -> Path | None:
    state.attempt(CompilerStage.SPATIAL)
    scene_path = _project_reference(
        project_root,
        cell.scene.usd,
        state,
        CompilerStage.SPATIAL,
        f"{cell_path}#/scene/usd",
    )
    if scene_path is None:
        return None

    root = cell.scene.root_prim.rstrip("/")
    prim_paths = [item.usd_prim.rstrip("/") for item in cell.components]
    for index, prim_path in enumerate(prim_paths):
        if not prim_path.startswith(f"{root}/"):
            state.add(
                CompilerStage.SPATIAL,
                _finding(
                    "compiler.component-prim-outside-root",
                    f"{cell_path}#/components/{index}/usd_prim",
                    f"Component prim '{prim_path}' is not below scene root '{root}'.",
                ),
            )
    for duplicate in _duplicates(prim_paths):
        state.add(
            CompilerStage.SPATIAL,
            _finding(
                "compiler.component-prim-duplicate",
                f"{cell_path}#/components",
                f"USD prim '{duplicate}' is assigned to multiple component instances.",
            ),
        )

    if scene_path.suffix.lower() == ".usda":
        text = _read_text(
            scene_path,
            state,
            CompilerStage.SPATIAL,
            "compiler.scene-unreadable",
        )
        if text is not None:
            declared_names = set(_USD_PRIM.findall(text))
            root_name = root.rsplit("/", 1)[-1]
            if root_name not in declared_names:
                state.add(
                    CompilerStage.SPATIAL,
                    _finding(
                        "compiler.scene-root-missing",
                        f"{scene_path}#",
                        f"USDA scene does not declare root prim '{root}'.",
                    ),
                )
    return scene_path


def _freeze_tasks(
    project_root: Path,
    cell_path: Path,
    cell: CellProject,
    state: _CompilerState,
    inventory: _FileInventory,
) -> tuple[BundleTaskReference, ...]:
    state.attempt(CompilerStage.BEHAVIOR_TREE)
    frozen: list[BundleTaskReference] = []
    parsed: dict[Path, tuple[str, set[str]] | None] = {}
    for index, task in sorted(enumerate(cell.tasks), key=lambda item: item[1].id):
        source = _project_reference(
            project_root,
            task.behavior_tree,
            state,
            CompilerStage.BEHAVIOR_TREE,
            f"{cell_path}#/tasks/{index}/behavior_tree",
        )
        if source is None:
            continue
        if source not in parsed:
            parsed[source] = _parse_behavior_tree(source, state)
        if parsed[source] is None:
            continue
        content = _read_bytes(
            source,
            state,
            CompilerStage.BEHAVIOR_TREE,
            "compiler.behavior-tree-unreadable",
        )
        if content is None:
            continue
        bundle_path = f"config/behavior-trees/{task.id}.xml"
        inventory.add(bundle_path, source, CompilerStage.BEHAVIOR_TREE)
        frozen.append(BundleTaskReference(id=task.id, path=bundle_path, sha256=_sha256(content)))
    return tuple(frozen)


def _parse_behavior_tree(source: Path, state: _CompilerState) -> tuple[str, set[str]] | None:
    try:
        root = ElementTree.parse(source).getroot()
    except (OSError, ElementTree.ParseError):
        state.add(
            CompilerStage.BEHAVIOR_TREE,
            _finding(
                "compiler.behavior-tree-invalid",
                f"{source}#",
                "Behavior tree XML is missing, unreadable, or not well formed.",
            ),
        )
        return None
    tree_ids = {
        identifier
        for element in root.findall(".//BehaviorTree")
        if (identifier := element.get("ID"))
    }
    main_tree = root.get("main_tree_to_execute", "")
    if main_tree and main_tree not in tree_ids:
        state.add(
            CompilerStage.BEHAVIOR_TREE,
            _finding(
                "compiler.behavior-tree-main-missing",
                f"{source}#/main_tree_to_execute",
                f"Main behavior tree '{main_tree}' is not declared in the XML document.",
            ),
        )
    return main_tree, tree_ids


def _freeze_recipes(
    project_root: Path,
    cell_path: Path,
    cell: CellProject,
    schemas: SchemaRegistry,
    resolution: ResolutionReport,
    mode: ExecutionMode,
    state: _CompilerState,
    inventory: _FileInventory,
) -> tuple[BundleRecipeReference, ...]:
    state.attempt(CompilerStage.RECIPE)
    frozen: list[BundleRecipeReference] = []
    seen: set[tuple[str, int]] = set()
    resolved_capabilities = {item.contract for item in resolution.capabilities}
    for index, binding in enumerate(cell.recipes):
        source = _project_reference(
            project_root,
            binding.path,
            state,
            CompilerStage.RECIPE,
            f"{cell_path}#/recipes/{index}/path",
        )
        if source is None:
            continue
        try:
            recipe = load_document(source, Recipe, schema_registry=schemas)
        except SourceLoadError as error:
            _add_load_error(state, CompilerStage.RECIPE, error)
            continue
        key = (recipe.recipe.id, recipe.recipe.version)
        if key in seen:
            state.add(
                CompilerStage.RECIPE,
                _finding(
                    "compiler.recipe-duplicate",
                    f"{cell_path}#/recipes/{index}",
                    f"Recipe '{key[0]}' version '{key[1]}' is bound more than once.",
                ),
            )
        seen.add(key)

        missing = sorted(set(recipe.compatibility.required_capabilities) - resolved_capabilities)
        if missing:
            state.add(
                CompilerStage.RECIPE,
                _finding(
                    "compiler.recipe-capability-unresolved",
                    f"{source}#/compatibility/required_capabilities",
                    f"Recipe requires unresolved capabilities: {', '.join(missing)}.",
                ),
            )
        if mode == ExecutionMode.PRODUCTION:
            if recipe.recipe.status != RecipeStatus.APPROVED:
                state.add(
                    CompilerStage.RECIPE,
                    _finding(
                        "compiler.production-recipe-unapproved",
                        f"{source}#/recipe/status",
                        (
                            f"Recipe '{recipe.recipe.id}' version '{recipe.recipe.version}' is not "
                            "APPROVED for production."
                        ),
                    ),
                )
            material = recipe.product.get("material")
            if not isinstance(material, str) or not material.strip() or material == "unknown":
                state.add(
                    CompilerStage.RECIPE,
                    _finding(
                        "compiler.production-material-unknown",
                        f"{source}#/product/material",
                        "Production recipes require a known material classification.",
                    ),
                )

        content = _read_bytes(
            source,
            state,
            CompilerStage.RECIPE,
            "compiler.recipe-unreadable",
        )
        if content is None:
            continue
        bundle_path = f"recipes/{recipe.recipe.id}/{recipe.recipe.version}/{source.name}"
        inventory.add(bundle_path, source, CompilerStage.RECIPE)
        frozen.append(
            BundleRecipeReference(
                id=recipe.recipe.id,
                version=recipe.recipe.version,
                status=recipe.recipe.status,
                path=bundle_path,
                sha256=_sha256(content),
            )
        )
    return tuple(sorted(frozen, key=lambda item: (item.id, item.version)))


def _freeze_components(
    cell: CellProject,
    registry: FilesystemComponentRegistry,
    mode: ExecutionMode,
    state: _CompilerState,
    inventory: _FileInventory,
) -> tuple[tuple[BundleComponentReference, ...], set[str]]:
    state.attempt(CompilerStage.TARGET)
    frozen: list[BundleComponentReference] = []
    adapter_packages: set[str] = set()
    for instance in sorted(cell.components, key=lambda item: item.id):
        package = registry.get(instance.component, instance.version)
        if package is None:
            continue
        adapter = (
            package.manifest.adapters.simulation
            if mode == ExecutionMode.SIMULATION
            else package.manifest.adapters.hardware
        )
        if adapter is None:
            continue
        adapter_packages.add(adapter.package)
        frozen.append(
            BundleComponentReference(
                instance_id=instance.id,
                component=instance.component,
                version=instance.version,
                package_path=package.package_path,
                adapter_package=adapter.package,
                adapter_entrypoint=adapter.entrypoint,
                adapter_minimum_version=adapter.minimum_version,
            )
        )
        _add_component_files(package.manifest, package.source_path, inventory, state)
    return tuple(frozen), adapter_packages


def _add_component_files(
    component: ComponentType,
    manifest_path: Path,
    inventory: _FileInventory,
    state: _CompilerState,
) -> None:
    package_root = manifest_path.parent.resolve()
    prefix = f"components/{component.component.id}/{component.component.version}"
    inventory.add(f"{prefix}/component.yaml", manifest_path, CompilerStage.TARGET)
    references = [
        component.assets.visual_usd,
        component.assets.collision_usd,
        component.assets.urdf,
        component.assets.srdf,
        component.config_schema,
        component.fault_catalog,
    ]
    for reference in sorted(item for item in references if item is not None):
        source = _contained_reference(
            package_root,
            reference,
            state,
            CompilerStage.TARGET,
            f"{manifest_path}#",
        )
        if source is not None:
            inventory.add(f"{prefix}/{Path(reference).as_posix()}", source, CompilerStage.TARGET)


def _freeze_calibrations(
    project_root: Path,
    cell_path: Path,
    cell: CellProject,
    state: _CompilerState,
    inventory: _FileInventory,
) -> None:
    for index, reference in enumerate(cell.calibrations):
        source = _project_reference(
            project_root,
            reference,
            state,
            CompilerStage.TARGET,
            f"{cell_path}#/calibrations/{index}",
        )
        if source is not None:
            inventory.add(f"calibration/{source.name}", source, CompilerStage.TARGET)


def _freeze_operator_recovery(
    project_root: Path,
    state: _CompilerState,
    inventory: _FileInventory,
) -> None:
    source = project_root / "operator" / "operator-recovery.json"
    if not source.exists():
        return
    content = _read_bytes(
        source,
        state,
        CompilerStage.SCHEMA,
        "compiler.operator-recovery-unreadable",
    )
    if content is None:
        return
    try:
        document: object = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        document = None
    if not _valid_operator_recovery_document(document):
        state.add(
            CompilerStage.SCHEMA,
            _finding(
                "compiler.operator-recovery-invalid",
                f"{source}#",
                "Operator recovery catalog is invalid or contains non-semantic control fields.",
            ),
        )
        return
    inventory.add("config/operator-recovery.json", source, CompilerStage.SCHEMA)


def _valid_operator_recovery_document(document: object) -> bool:
    if not isinstance(document, dict) or set(document) != {"schema_version", "actions"}:
        return False
    if document.get("schema_version") != "0.1.0":
        return False
    actions = document.get("actions")
    if not isinstance(actions, list):
        return False
    seen: set[str] = set()
    allowed_fields = {
        "action_id",
        "fault_codes",
        "kind",
        "label",
        "instructions",
        "required_role",
        "confirmation",
    }
    for action in actions:
        if not isinstance(action, dict) or not set(action) <= allowed_fields:
            return False
        if not allowed_fields - {"confirmation"} <= set(action):
            return False
        action_id = action.get("action_id")
        fault_codes = action.get("fault_codes")
        kind = action.get("kind")
        required_role = action.get("required_role")
        if (
            not isinstance(action_id, str)
            or _OPERATOR_ID.fullmatch(action_id) is None
            or action_id in seen
        ):
            return False
        if (
            not isinstance(fault_codes, list)
            or not fault_codes
            or not all(
                isinstance(code, str) and _OPERATOR_ID.fullmatch(code) for code in fault_codes
            )
            or len(set(fault_codes)) != len(fault_codes)
        ):
            return False
        if kind not in {
            "acknowledge_fault",
            "request_supervisor_recovery",
            "enter_maintenance",
        }:
            return False
        if required_role not in {"operator", "maintainer", "administrator"}:
            return False
        if kind == "enter_maintenance" and required_role == "operator":
            return False
        if not all(
            isinstance(action.get(field), str) and bool(str(action[field]).strip())
            for field in ("label", "instructions")
        ):
            return False
        if "confirmation" in action and not isinstance(action["confirmation"], str):
            return False
        seen.add(action_id)
    return True


def _add_schema_files(inventory: _FileInventory, schemas: SchemaRegistry) -> None:
    for key in schemas.keys:
        registered = schemas.get(key.kind, key.version)
        inventory.add(
            f"schemas/{registered.path.name}",
            registered.path,
            CompilerStage.SCHEMA,
        )


def _project_reference(
    project_root: Path,
    reference: str,
    state: _CompilerState,
    stage: CompilerStage,
    finding_path: str,
) -> Path | None:
    return _contained_reference(project_root, reference, state, stage, finding_path)


def _contained_reference(
    root: Path,
    reference: str,
    state: _CompilerState,
    stage: CompilerStage,
    finding_path: str,
) -> Path | None:
    raw = Path(reference)
    source = (root / raw).resolve()
    if raw.is_absolute() or not source.is_relative_to(root.resolve()):
        state.add(
            stage,
            _finding(
                "compiler.reference-outside-root",
                finding_path,
                f"Reference '{reference}' escapes its allowed source root.",
            ),
        )
        return None
    if not source.is_file():
        state.add(
            stage,
            _finding(
                "compiler.reference-not-found",
                finding_path,
                f"Referenced file '{reference}' does not exist.",
            ),
        )
        return None
    return source


def _read_text(
    source: Path,
    state: _CompilerState,
    stage: CompilerStage,
    code: str,
) -> str | None:
    try:
        return source.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        state.add(stage, _finding(code, f"{source}#", "Referenced text file is unreadable."))
        return None


def _read_bytes(
    source: Path,
    state: _CompilerState,
    stage: CompilerStage,
    code: str,
) -> bytes | None:
    try:
        return source.read_bytes()
    except OSError:
        state.add(stage, _finding(code, f"{source}#", "Referenced source file is unreadable."))
        return None


def _add_load_error(state: _CompilerState, stage: CompilerStage, error: SourceLoadError) -> None:
    if error.findings:
        for finding in error.findings:
            state.add(stage, finding)
        return
    state.add(stage, _finding(error.code, f"{error.source_path}#", error.message))


def _report(
    state: _CompilerState,
    *,
    resolution: ResolutionReport | None = None,
    manifest: BundleManifest | None = None,
    manifest_json: str | None = None,
) -> CompilationReport:
    return CompilationReport(
        valid=manifest is not None and not state.has_errors(),
        execution_mode=state.mode,
        requested_target_profile=state.target_profile,
        stages=state.stages,
        resolution=resolution,
        manifest=manifest,
        manifest_json=manifest_json,
        findings=state.findings,
    )


def _finding(code: str, path: str, message: str) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        severity=FindingSeverity.ERROR,
        path=path,
        message=message,
    )


def _finding_sort_key(finding: ValidationFinding) -> tuple[str, str, str]:
    return finding.path, finding.code, finding.message


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates
