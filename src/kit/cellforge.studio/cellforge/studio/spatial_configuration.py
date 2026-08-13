"""Pure spatial, configuration, and calibration edits for Cell Studio."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from cellforge_cli.projects import resolve_project_schema_directory
from cellforge_domain import FilesystemComponentRegistry, SchemaRegistry
from cellforge_domain.schemas import SchemaDocumentKind
from jsonschema import Draft202012Validator

from cellforge.studio.application import ProjectContents, SpatialEditResult, ValidationItem
from cellforge.studio.component_service import (
    _dump_yaml,
    _parse_cell,
    _ParsedCell,
    _prim_spans,
    _validate_pair,
    _validate_variants,
)


@dataclass(frozen=True, slots=True)
class SpatialComponent:
    """One selected component's inspectable spatial/configuration details."""

    instance_id: str
    alias: str
    usd_prim: str
    frames: tuple[str, ...]
    collision_asset: str
    transform: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SpatialBrowserResult:
    """Viewport-neutral selection, frame, and collision display data."""

    components: tuple[SpatialComponent, ...]
    validation: tuple[ValidationItem, ...] = ()


class SpatialConfigurationService:
    """Edit existing spatial/configuration records without direct Kit or filesystem writes."""

    def __init__(
        self,
        canonical_schema_directory: Path,
        *,
        new_uuid: Callable[[], UUID] = uuid4,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._canonical_schemas = canonical_schema_directory.resolve()
        self._new_uuid = new_uuid
        self._now = now

    def browse(self, project_path: Path, contents: ProjectContents) -> SpatialBrowserResult:
        """Return selected-component frame/collision data for a viewport adapter."""

        root = project_path.resolve()
        parsed = _parse_cell(contents.cell_yaml, root / "cell.yaml")
        if not isinstance(parsed, _ParsedCell):
            return SpatialBrowserResult(components=(), validation=parsed)
        registry = self._registry(root)
        components: list[SpatialComponent] = []
        findings: list[ValidationItem] = []
        for instance in sorted(parsed.model.components, key=lambda item: item.id):
            package = registry.get(instance.component, instance.version)
            if package is None:
                findings.append(
                    _finding(
                        "studio.spatial-component-missing",
                        root / "cell.yaml",
                        "A selected component package is unavailable.",
                    )
                )
                continue
            transform = _read_transform(contents.scene_usda, instance.usd_prim)
            if transform is None:
                findings.append(
                    _finding(
                        "studio.spatial-transform-unavailable",
                        root / parsed.model.scene.usd,
                        f"Could not inspect transform for '{instance.usd_prim}'.",
                    )
                )
                continue
            components.append(
                SpatialComponent(
                    instance_id=instance.id,
                    alias=instance.alias,
                    usd_prim=instance.usd_prim,
                    frames=tuple(frame.id for frame in package.manifest.frames),
                    collision_asset=package.manifest.assets.collision_usd,
                    transform=transform,
                )
            )
        return SpatialBrowserResult(components=tuple(components), validation=tuple(findings))

    def set_transform(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        matrix: tuple[float, ...],
    ) -> SpatialEditResult:
        """Set one finite, non-singular component Xform matrix in the paired candidate."""

        root, parsed = self._parsed(project_path, contents)
        if isinstance(parsed, SpatialEditResult):
            return parsed
        instance = next((item for item in parsed.model.components if item.id == instance_id), None)
        if instance is None:
            return _rejected(
                "studio.spatial-instance-not-found",
                root / "cell.yaml",
                "The selected component does not exist.",
            )
        if not _valid_matrix(matrix):
            return _rejected(
                "studio.spatial-transform-invalid",
                root / parsed.model.scene.usd,
                "Transforms require 16 finite values and a non-singular affine matrix.",
            )
        try:
            scene = _write_transform(contents.scene_usda, instance.usd_prim, matrix)
        except ValueError:
            return _rejected(
                "studio.spatial-transform-not-editable",
                root / parsed.model.scene.usd,
                "The selected USD Xform cannot be edited safely.",
            )
        return self._validated(
            root, parsed, ProjectContents(contents.cell_yaml, scene, contents.artifacts)
        )

    def set_component_configuration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        configuration: Mapping[str, Any],
    ) -> SpatialEditResult:
        """Apply an instance configuration after its component JSON schema accepts it."""

        root, parsed = self._parsed(project_path, contents)
        if isinstance(parsed, SpatialEditResult):
            return parsed
        index, instance = _instance_at(parsed, instance_id)
        if instance is None:
            return _rejected(
                "studio.spatial-instance-not-found",
                root / "cell.yaml",
                "The selected component does not exist.",
            )
        package = self._registry(root).get(instance.component, instance.version)
        if package is None:
            return _rejected(
                "studio.spatial-component-missing",
                root / "cell.yaml",
                "The selected component package is unavailable.",
            )
        findings = _configuration_findings(
            package.source_path.parent, package.manifest.config_schema, configuration
        )
        if findings:
            return SpatialEditResult(
                contents=None,
                validation=tuple(
                    _finding(
                        "studio.component-configuration-invalid",
                        root / "cell.yaml",
                        message,
                        fragment=f"/components/{index}/config",
                    )
                    for message in findings
                ),
            )
        data = dict(parsed.data)
        components = list(data["components"])
        changed = dict(components[index])
        changed["config"] = dict(configuration)
        components[index] = changed
        data["components"] = components
        return self._validated(
            root, parsed, ProjectContents(_dump_yaml(data), contents.scene_usda, contents.artifacts)
        )

    def set_component_variants(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        variants: Mapping[str, str],
    ) -> SpatialEditResult:
        """Apply exactly one declared selection for every component variant set."""

        root, parsed = self._parsed(project_path, contents)
        if isinstance(parsed, SpatialEditResult):
            return parsed
        index, instance = _instance_at(parsed, instance_id)
        if instance is None:
            return _rejected(
                "studio.spatial-instance-not-found",
                root / "cell.yaml",
                "The selected component does not exist.",
            )
        package = self._registry(root).get(instance.component, instance.version)
        if package is None:
            return _rejected(
                "studio.spatial-component-missing",
                root / "cell.yaml",
                "The selected component package is unavailable.",
            )
        finding = _validate_variants(package.manifest.variants, variants, root / "cell.yaml")
        if finding is not None:
            return SpatialEditResult(contents=None, validation=(finding,))
        data = dict(parsed.data)
        components = list(data["components"])
        changed = dict(components[index])
        changed["variants"] = dict(variants)
        components[index] = changed
        data["components"] = components
        return self._validated(
            root, parsed, ProjectContents(_dump_yaml(data), contents.scene_usda, contents.artifacts)
        )

    def import_calibration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        calibration: Mapping[str, Any],
    ) -> SpatialEditResult:
        """Validate, immutably stage, and bind one imported calibration artifact."""

        root, parsed = self._parsed(project_path, contents)
        if isinstance(parsed, SpatialEditResult):
            return parsed
        index, instance = _instance_at(parsed, instance_id)
        if instance is None:
            return _rejected(
                "studio.spatial-instance-not-found",
                root / "cell.yaml",
                "The selected component does not exist.",
            )
        errors = self._calibration_findings(root, instance_id, calibration)
        if errors:
            return SpatialEditResult(contents=None, validation=errors)
        calibration_id = str(calibration["calibration_id"])
        relative = f"calibration/{calibration_id}.json"
        artifacts = dict(contents.artifacts)
        encoded = _canonical_json(calibration)
        existing = artifacts.get(relative)
        if existing is None:
            disk_path = root / relative
            try:
                existing = disk_path.read_bytes() if disk_path.is_file() else None
            except OSError:
                existing = None
        if existing is not None and existing != encoded:
            return _rejected(
                "studio.calibration-immutable-conflict",
                root / relative,
                "A different calibration already uses this immutable calibration ID.",
            )
        artifacts[relative] = encoded
        data = dict(parsed.data)
        calibrations = list(data.get("calibrations", []))
        if relative not in calibrations:
            calibrations.append(relative)
        data["calibrations"] = calibrations
        components = list(data["components"])
        changed = dict(components[index])
        references = list(changed.get("calibration_refs", []))
        if relative not in references:
            references.append(relative)
        changed["calibration_refs"] = references
        components[index] = changed
        data["components"] = components
        return self._validated(
            root,
            parsed,
            ProjectContents(_dump_yaml(data), contents.scene_usda, artifacts),
            calibration_path=relative,
        )

    def create_calibration(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        instance_id: str,
        kind: str,
        valid_until: datetime,
        data: Mapping[str, Any],
    ) -> SpatialEditResult:
        """Create a content-addressed immutable calibration and bind it to one component."""

        created = self._now().astimezone(UTC)
        record: dict[str, Any] = {
            "schema_version": "0.1.0",
            "calibration_id": str(self._new_uuid()),
            "component_instance_id": instance_id,
            "kind": kind,
            "created_at": created.isoformat().replace("+00:00", "Z"),
            "valid_until": valid_until.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "data": dict(data),
        }
        record["sha256"] = _calibration_digest(record)
        return self.import_calibration(
            project_path, contents, instance_id=instance_id, calibration=record
        )

    def _parsed(
        self, project_path: Path, contents: ProjectContents
    ) -> tuple[Path, _ParsedCell | SpatialEditResult]:
        root = project_path.resolve()
        parsed = _parse_cell(contents.cell_yaml, root / "cell.yaml")
        if isinstance(parsed, _ParsedCell):
            return root, parsed
        return root, SpatialEditResult(contents=None, validation=parsed)

    def _validated(
        self,
        root: Path,
        parsed: _ParsedCell,
        contents: ProjectContents,
        calibration_path: str | None = None,
    ) -> SpatialEditResult:
        validation = _validate_pair(contents, root, root / parsed.model.scene.usd)
        return (
            SpatialEditResult(contents=None, validation=validation)
            if validation
            else SpatialEditResult(contents=contents, calibration_path=calibration_path)
        )

    def _registry(self, root: Path) -> FilesystemComponentRegistry:
        schemas = SchemaRegistry.from_directory(
            resolve_project_schema_directory(root, self._canonical_schemas)
        )
        return FilesystemComponentRegistry.from_directory(
            root / "components", schema_registry=schemas
        )

    def _calibration_findings(
        self, root: Path, instance_id: str, calibration: Mapping[str, Any]
    ) -> tuple[ValidationItem, ...]:
        registry = SchemaRegistry.from_directory(
            resolve_project_schema_directory(root, self._canonical_schemas)
        )
        findings = [
            _validation_item(item)
            for item in registry.validate(
                SchemaDocumentKind.CALIBRATION, calibration, root / "calibration"
            )
        ]
        if calibration.get("component_instance_id") != instance_id:
            findings.append(
                _finding(
                    "studio.calibration-component-mismatch",
                    root / "calibration",
                    "Calibration must bind to the selected immutable component instance ID.",
                )
            )
        if isinstance(calibration.get("sha256"), str) and calibration[
            "sha256"
        ] != _calibration_digest(calibration):
            findings.append(
                _finding(
                    "studio.calibration-digest-invalid",
                    root / "calibration",
                    "Calibration sha256 does not match its immutable payload.",
                )
            )
        try:
            valid_until = datetime.fromisoformat(
                str(calibration["valid_until"]).replace("Z", "+00:00")
            )
            created_at = datetime.fromisoformat(
                str(calibration["created_at"]).replace("Z", "+00:00")
            )
            if valid_until <= created_at or valid_until <= self._now().astimezone(UTC):
                findings.append(
                    _finding(
                        "studio.calibration-expired",
                        root / "calibration",
                        "Calibration validity must be after creation and current time.",
                    )
                )
        except (KeyError, TypeError, ValueError):
            pass
        return tuple(findings)


def _instance_at(parsed: _ParsedCell, instance_id: str) -> tuple[int, Any | None]:
    for index, instance in enumerate(parsed.model.components):
        if instance.id == instance_id:
            return index, instance
    return -1, None


def _configuration_findings(
    package_root: Path, schema_reference: str | None, value: Mapping[str, Any]
) -> tuple[str, ...]:
    if schema_reference is None:
        return ()
    schema_path = (package_root / schema_reference).resolve()
    try:
        schema_path.relative_to(package_root.resolve())
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = sorted(
            Draft202012Validator(schema).iter_errors(dict(value)),
            key=lambda item: (list(item.absolute_path), item.message),
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return ("The declared component configuration schema is unreadable.",)
    return tuple(error.message for error in errors)


def _read_transform(scene: str, prim_path: str) -> tuple[float, ...] | None:
    spans = [span for span in _prim_spans(scene) if span.path == prim_path.rstrip("/")]
    if len(spans) != 1:
        return None
    body = scene[spans[0].open_brace + 1 : spans[0].close_brace]
    marker = "xformOp:translate = ("
    start = body.find(marker)
    if start < 0:
        return (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    end = body.find(")", start)
    try:
        xyz = tuple(float(value.strip()) for value in body[start + len(marker) : end].split(","))
    except ValueError:
        return None
    return (
        (1.0, 0.0, 0.0, xyz[0], 0.0, 1.0, 0.0, xyz[1], 0.0, 0.0, 1.0, xyz[2], 0.0, 0.0, 0.0, 1.0)
        if len(xyz) == 3
        else None
    )


def _write_transform(scene: str, prim_path: str, matrix: tuple[float, ...]) -> str:
    spans = [span for span in _prim_spans(scene) if span.path == prim_path.rstrip("/")]
    if len(spans) != 1:
        raise ValueError
    span = spans[0]
    body = scene[span.open_brace + 1 : span.close_brace]
    if "xformOp:transform" in body:
        raise ValueError
    indent = "    "
    values = ", ".join(f"{value:.12g}" for value in matrix)
    replacement = (
        f"\n{indent}matrix4d xformOp:transform = ({values})\n"
        f'{indent}uniform token[] xformOpOrder = ["xformOp:transform"]\n'
    )
    return (
        f"{scene[: span.open_brace + 1]}{replacement}"
        f"{scene[span.open_brace + 1 : span.close_brace]}{scene[span.close_brace :]}"
    )


def _valid_matrix(matrix: tuple[float, ...]) -> bool:
    if len(matrix) != 16 or not all(math.isfinite(value) for value in matrix):
        return False
    determinant = (
        matrix[0] * (matrix[5] * matrix[10] - matrix[6] * matrix[9])
        - matrix[1] * (matrix[4] * matrix[10] - matrix[6] * matrix[8])
        + matrix[2] * (matrix[4] * matrix[9] - matrix[5] * matrix[8])
    )
    return abs(determinant) > 1e-12 and matrix[12:] == (0.0, 0.0, 0.0, 1.0)


def _calibration_digest(calibration: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in calibration.items() if key != "sha256"}
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _finding(code: str, source: Path, message: str, *, fragment: str = "") -> ValidationItem:
    return ValidationItem(
        code=code, severity="error", path=f"{source.resolve()}#{fragment}", message=message
    )


def _rejected(code: str, source: Path, message: str) -> SpatialEditResult:
    return SpatialEditResult(contents=None, validation=(_finding(code, source, message),))


def _validation_item(finding: Any) -> ValidationItem:
    return ValidationItem(
        code=finding.code,
        severity=finding.severity.value,
        path=finding.path,
        message=finding.message,
    )
