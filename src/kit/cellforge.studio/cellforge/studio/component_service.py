"""Pure component registry browser and paired YAML/USD placement transformations."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml
from cellforge_cli.projects import resolve_project_schema_directory
from cellforge_domain import (
    AdapterMode,
    CellProject,
    ComponentInstance,
    ComponentKind,
    ExecutionMode,
    FilesystemComponentRegistry,
    SchemaRegistry,
    SimulationLevel,
    SupportLevel,
    component_mode_findings,
)
from pydantic import ValidationError

from cellforge.studio.application import (
    BrowserComponent,
    BrowserResult,
    ComponentEditResult,
    ComponentFilters,
    ComponentVariant,
    ProjectContents,
    ValidationItem,
)
from cellforge.studio.scene import inspect_scene, validate_scene_cross_references

_PRIM_DEFINITION = re.compile(r'\b(?:def|over|class)\s+\w+\s+"([^"]+)"')
_SIMULATION_LEVEL_RANK = {level.value: index for index, level in enumerate(SimulationLevel)}


@dataclass(frozen=True, slots=True)
class _PrimSpan:
    path: str
    start: int
    open_brace: int
    close_brace: int


@dataclass(frozen=True, slots=True)
class _ParsedCell:
    model: CellProject
    data: dict[str, Any]


class ComponentPlacementService:
    """Browse project-local packages and transform exact canonical source buffers."""

    def __init__(
        self,
        canonical_schema_directory: Path,
        *,
        new_uuid: Callable[[], UUID] = uuid4,
    ) -> None:
        self._canonical_schemas = canonical_schema_directory.resolve()
        self._new_uuid = new_uuid

    def browse(
        self, project_path: Path, filters: ComponentFilters = ComponentFilters()
    ) -> BrowserResult:
        """Return deterministic package details matching every supplied filter."""

        root = project_path.resolve()
        invalid = _invalid_filters(filters)
        if invalid:
            return BrowserResult(components=(), validation=invalid)
        registry = self._registry(root)
        findings = tuple(_validation_item(item) for item in registry.findings)
        components: list[BrowserComponent] = []
        for entry in registry.components:
            package = registry.get(entry.component, entry.version)
            assert package is not None
            manifest = package.manifest
            capabilities = tuple(sorted({item.contract for item in manifest.capabilities}))
            if filters.kind and manifest.component.kind.value != filters.kind:
                continue
            if filters.capability and filters.capability not in capabilities:
                continue
            if filters.support_level and manifest.support.level.value != filters.support_level:
                continue
            if (
                filters.simulation_level
                and _SIMULATION_LEVEL_RANK[manifest.support.simulation_level.value]
                < _SIMULATION_LEVEL_RANK[filters.simulation_level]
            ):
                continue

            compatible_modes: list[str] = []
            warnings: list[str] = []
            probe = ComponentInstance(
                id="browser-probe",
                alias="browser-probe",
                component=manifest.component.id,
                version=manifest.component.version,
                usd_prim="/World/BrowserProbe",
                adapter_mode=AdapterMode.TARGET_SELECTED,
                config={},
            )
            for mode in ExecutionMode:
                mode_findings = component_mode_findings(
                    probe, manifest, mode, f"registry:{package.package_path}"
                )
                if not mode_findings:
                    compatible_modes.append(mode.value)
                elif mode is ExecutionMode.PRODUCTION:
                    warnings.extend(item.message for item in mode_findings)

            components.append(
                BrowserComponent(
                    component=manifest.component.id,
                    version=manifest.component.version,
                    kind=manifest.component.kind.value,
                    name=manifest.component.name,
                    manufacturer=manifest.component.manufacturer,
                    model=manifest.component.model,
                    description=manifest.component.description,
                    license=manifest.component.license,
                    package_path=package.package_path,
                    capabilities=capabilities,
                    support_level=manifest.support.level.value,
                    simulation_level=manifest.support.simulation_level.value,
                    compatible_modes=tuple(compatible_modes),
                    warnings=tuple(sorted(set(warnings))),
                    variants=tuple(
                        ComponentVariant(name=name, selections=tuple(selections))
                        for name, selections in sorted(manifest.variants.items())
                    ),
                )
            )
        return BrowserResult(
            components=tuple(
                sorted(
                    components,
                    key=lambda item: (item.kind, item.name, item.component, item.version),
                )
            ),
            validation=findings,
        )

    def place(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        component: str,
        version: str,
        alias: str,
        variants: Mapping[str, str],
    ) -> ComponentEditResult:
        """Create one linked instance record and referenced USD prim in memory."""

        root = project_path.resolve()
        parsed = _parse_cell(contents.cell_yaml, root / "cell.yaml")
        if not isinstance(parsed, _ParsedCell):
            return ComponentEditResult(contents=None, validation=parsed)
        cell, data = parsed.model, parsed.data
        registry = self._registry(root)
        package = registry.get(component, version)
        if package is None:
            return _rejected(
                "studio.component-not-found",
                root / "components",
                f"Component '{component}' version '{version}' is not registered in this project.",
            )
        if any(item.alias == alias for item in cell.components):
            return _rejected(
                "studio.component-alias-duplicate",
                root / "cell.yaml",
                f"Component alias '{alias}' is already in use.",
                fragment="/components",
            )
        variant_finding = _validate_variants(
            package.manifest.variants, variants, root / "cell.yaml"
        )
        if variant_finding is not None:
            return ComponentEditResult(contents=None, validation=(variant_finding,))

        asset = (package.source_path.parent / package.manifest.assets.visual_usd).resolve()
        try:
            asset.relative_to(package.source_path.parent.resolve())
        except ValueError:
            return _rejected(
                "studio.component-asset-outside-package",
                package.source_path,
                "The component visual asset must remain inside its package.",
            )
        if not asset.is_file():
            return _rejected(
                "studio.component-asset-missing",
                package.source_path,
                f"The declared visual asset '{package.manifest.assets.visual_usd}' does not exist.",
            )

        instance_id = f"component-{self._new_uuid().hex}"
        prim_name = f"Component_{instance_id.removeprefix('component-')[:16]}"
        prim_path = f"{cell.scene.root_prim.rstrip('/')}/{prim_name}"
        try:
            instance = ComponentInstance(
                id=instance_id,
                alias=alias,
                component=component,
                version=version,
                usd_prim=prim_path,
                variants=dict(variants),
                adapter_mode=AdapterMode.TARGET_SELECTED,
                config={},
            )
        except ValidationError:
            return _rejected(
                "studio.component-instance-invalid",
                root / "cell.yaml",
                "Alias, component identity, version, or selected variants are invalid.",
                fragment="/components",
            )

        components = list(data.get("components", []))
        components.append(instance.model_dump(mode="json", by_alias=True, exclude_none=True))
        data["components"] = components
        scene_path = root / cell.scene.usd
        reference = Path(os.path.relpath(asset, scene_path.parent)).as_posix()
        try:
            scene_text = _insert_component_prim(
                contents.scene_usda,
                root_path=cell.scene.root_prim,
                prim_name=prim_name,
                instance_id=instance_id,
                component=component,
                version=version,
                reference=reference,
            )
        except ValueError:
            return _rejected(
                "studio.scene-root-not-editable",
                scene_path,
                f"Could not locate an editable USD root prim '{cell.scene.root_prim}'.",
            )
        changed = ProjectContents(cell_yaml=_dump_yaml(data), scene_usda=scene_text)
        validation = _validate_pair(changed, root, scene_path)
        if validation:
            return ComponentEditResult(contents=None, validation=validation)
        return ComponentEditResult(contents=changed, instance_id=instance_id)

    def remove(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        remove_connections: bool,
    ) -> ComponentEditResult:
        """Remove linked records, refusing implicit deletion of incident connections."""

        root = project_path.resolve()
        parsed = _parse_cell(contents.cell_yaml, root / "cell.yaml")
        if not isinstance(parsed, _ParsedCell):
            return ComponentEditResult(contents=None, validation=parsed)
        cell, data = parsed.model, parsed.data
        matches = [item for item in cell.components if item.id == instance_id]
        if not matches:
            return _rejected(
                "studio.component-instance-not-found",
                root / "cell.yaml",
                f"Component instance '{instance_id}' does not exist.",
                fragment="/components",
            )
        instance = matches[0]
        incident = tuple(
            item.id
            for item in cell.connections
            if item.from_.component == instance_id or item.to.component == instance_id
        )
        if incident and not remove_connections:
            return _rejected(
                "studio.component-removal-connections-require-resolution",
                root / "cell.yaml",
                (
                    f"Component '{instance_id}' has connections ({', '.join(sorted(incident))}); "
                    "explicitly remove those connections or cancel removal."
                ),
                fragment="/connections",
            )

        data["components"] = [
            item for item in data.get("components", []) if item.get("id") != instance_id
        ]
        if remove_connections:
            data["connections"] = [
                item
                for item in data.get("connections", [])
                if item.get("from", {}).get("component") != instance_id
                and item.get("to", {}).get("component") != instance_id
            ]
        scene_path = root / cell.scene.usd
        try:
            scene_text = _remove_component_prim(contents.scene_usda, instance.usd_prim)
        except ValueError:
            return _rejected(
                "studio.scene-prim-remove-failed",
                scene_path,
                f"Could not remove the linked USD prim '{instance.usd_prim}'.",
            )
        changed = ProjectContents(cell_yaml=_dump_yaml(data), scene_usda=scene_text)
        validation = _validate_pair(changed, root, scene_path)
        if validation:
            return ComponentEditResult(contents=None, validation=validation)
        return ComponentEditResult(
            contents=changed,
            instance_id=instance_id,
            removed_connections=tuple(sorted(incident)) if remove_connections else (),
        )

    def _registry(self, project_path: Path) -> FilesystemComponentRegistry:
        schema_directory = resolve_project_schema_directory(project_path, self._canonical_schemas)
        schemas = SchemaRegistry.from_directory(schema_directory)
        return FilesystemComponentRegistry.from_directory(
            project_path / "components", schema_registry=schemas
        )


def _invalid_filters(filters: ComponentFilters) -> tuple[ValidationItem, ...]:
    allowed = {
        "kind": {item.value for item in ComponentKind},
        "support_level": {item.value for item in SupportLevel},
        "simulation_level": {item.value for item in SimulationLevel},
    }
    findings = []
    for name, choices in allowed.items():
        value = getattr(filters, name)
        if value and value not in choices:
            findings.append(
                ValidationItem(
                    code="studio.component-filter-invalid",
                    severity="error",
                    path=f"component-browser#/{name}",
                    message=f"Unknown {name.replace('_', ' ')} filter '{value}'.",
                )
            )
    return tuple(findings)


def _validate_variants(
    declared: Mapping[str, Sequence[str]], selected: Mapping[str, str], source: Path
) -> ValidationItem | None:
    if set(selected) != set(declared):
        return ValidationItem(
            code="studio.component-variants-incomplete",
            severity="error",
            path=f"{source.resolve()}#/components/variants",
            message="Select exactly one value for every declared component variant set.",
        )
    invalid = sorted(
        f"{name}={value}" for name, value in selected.items() if value not in declared.get(name, ())
    )
    if invalid:
        return ValidationItem(
            code="studio.component-variant-invalid",
            severity="error",
            path=f"{source.resolve()}#/components/variants",
            message=f"Unsupported component variant selection(s): {', '.join(invalid)}.",
        )
    return None


def _parse_cell(text: str, source: Path) -> _ParsedCell | tuple[ValidationItem, ...]:
    try:
        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError
        model = CellProject.model_validate(raw)
    except (yaml.YAMLError, ValidationError, ValueError):
        return (
            ValidationItem(
                code="studio.component-edit-cell-invalid",
                severity="error",
                path=f"{source.resolve()}#",
                message="Component editing requires a valid canonical cell.yaml buffer.",
            ),
        )
    return _ParsedCell(model=model, data=raw)


def _dump_yaml(data: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True, width=1000)


def _validate_pair(
    contents: ProjectContents, root: Path, scene_path: Path
) -> tuple[ValidationItem, ...]:
    parsed = _parse_cell(contents.cell_yaml, root / "cell.yaml")
    if not isinstance(parsed, _ParsedCell):
        return parsed
    data = parsed.data
    scene, findings = inspect_scene(contents.scene_usda, scene_path)
    if scene is None:
        return findings
    return (
        *findings,
        *validate_scene_cross_references(
            data, scene, cell_path=root / "cell.yaml", scene_path=scene_path
        ),
    )


def _prim_spans(text: str) -> tuple[_PrimSpan, ...]:
    spans: list[_PrimSpan] = []
    stack: list[_PrimSpan] = []
    for match in _PRIM_DEFINITION.finditer(text):
        while stack and match.start() > stack[-1].close_brace:
            stack.pop()
        open_brace = text.find("{", match.end())
        if open_brace < 0:
            continue
        close_brace = _matching_brace(text, open_brace)
        if close_brace < 0:
            continue
        parent = stack[-1].path if stack else ""
        path = f"{parent}/{match.group(1)}"
        line_start = text.rfind("\n", 0, match.start()) + 1
        span = _PrimSpan(
            path=path, start=line_start, open_brace=open_brace, close_brace=close_brace
        )
        spans.append(span)
        stack.append(span)
    return tuple(spans)


def _matching_brace(text: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _insert_component_prim(
    text: str,
    *,
    root_path: str,
    prim_name: str,
    instance_id: str,
    component: str,
    version: str,
    reference: str,
) -> str:
    roots = [span for span in _prim_spans(text) if span.path == root_path.rstrip("/")]
    if len(roots) != 1:
        raise ValueError
    root = roots[0]
    line_start = text.rfind("\n", 0, root.start) + 1
    root_indent = text[line_start : root.start]
    indent = f"{root_indent}    "
    block = (
        f'{indent}def Xform "{prim_name}" (\n'
        f"{indent}    prepend references = @{reference}@\n"
        f"{indent}) {{\n"
        f'{indent}    custom string cellforge:instanceId = "{instance_id}"\n'
        f'{indent}    custom string cellforge:componentType = "{component}"\n'
        f'{indent}    custom string cellforge:componentVersion = "{version}"\n'
        f"{indent}}}\n"
    )
    return f"{text[: root.close_brace]}{block}{text[root.close_brace :]}"


def _remove_component_prim(text: str, prim_path: str) -> str:
    matches = [span for span in _prim_spans(text) if span.path == prim_path.rstrip("/")]
    if len(matches) != 1:
        raise ValueError
    span = matches[0]
    end = span.close_brace + 1
    if end < len(text) and text[end] == "\r":
        end += 1
    if end < len(text) and text[end] == "\n":
        end += 1
    return f"{text[: span.start]}{text[end:]}"


def _rejected(code: str, source: Path, message: str, *, fragment: str = "") -> ComponentEditResult:
    suffix = f"#{fragment}" if fragment else "#"
    return ComponentEditResult(
        contents=None,
        validation=(
            ValidationItem(
                code=code,
                severity="error",
                path=f"{source.resolve()}{suffix}",
                message=message,
            ),
        ),
    )


def _validation_item(finding: Any) -> ValidationItem:
    return ValidationItem(
        code=finding.code,
        severity=finding.severity.value,
        path=finding.path,
        message=finding.message,
    )
