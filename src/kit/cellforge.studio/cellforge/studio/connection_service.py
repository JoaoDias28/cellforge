"""Pure typed connection browsing, validation, and paired YAML/USD transformations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cellforge_cli.projects import resolve_project_schema_directory
from cellforge_domain import (
    CellProject,
    ComponentType,
    Connection,
    ConnectionEndpoint,
    ConnectionKind,
    ExecutionMode,
    FilesystemComponentRegistry,
    Port,
    SchemaRegistry,
    resolve_cell,
)
from pydantic import ValidationError

from cellforge.studio.application import (
    ConnectionBrowserResult,
    ConnectionEdge,
    ConnectionEditResult,
    ConnectionPort,
    MechanicalSnapPreview,
    ProjectContents,
    ValidationItem,
)
from cellforge.studio.component_service import (
    _dump_yaml,
    _parse_cell,
    _ParsedCell,
    _prim_spans,
    _validate_pair,
)

SAFETY_DISCLAIMER = (
    "Modeled safety dependencies are engineering-review metadata only. They do not implement, "
    "replace, or authorize any safety-rated function or ordinary executable wiring."
)
_IDENTITY_MATRIX = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


@dataclass(frozen=True, slots=True)
class _ConnectionCandidate:
    cell: CellProject
    data: dict[str, Any]
    connection: Connection
    from_port: Port
    to_port: Port


class ConnectionAuthoringService:
    """Expose port graph data and create validated connection edits without Kit."""

    def __init__(self, canonical_schema_directory: Path) -> None:
        self._canonical_schemas = canonical_schema_directory.resolve()

    def browse(self, project_path: Path, contents: ProjectContents) -> ConnectionBrowserResult:
        """Return deterministic declared ports and existing typed graph edges."""

        root = project_path.resolve()
        parsed = _parse_cell(contents.cell_yaml, root / "cell.yaml")
        if not isinstance(parsed, _ParsedCell):
            return ConnectionBrowserResult(ports=(), edges=(), validation=parsed)
        cell = parsed.model
        registry = self._registry(root)
        report = resolve_cell(
            cell,
            registry,
            ExecutionMode.SIMULATION,
            source_name=str(root / "cell.yaml"),
        )
        findings = tuple(_validation_item(item) for item in report.findings)
        ports: list[ConnectionPort] = []
        packages: dict[str, Any] = {}
        for instance in sorted(cell.components, key=lambda item: item.id):
            package = registry.get(instance.component, instance.version)
            if package is None:
                continue
            packages[instance.id] = package
            for kind in ConnectionKind:
                for port in _ports_for_kind(package.manifest, kind):
                    ports.append(
                        ConnectionPort(
                            component_instance=instance.id,
                            component_alias=instance.alias,
                            kind=kind.value,
                            port=port.id,
                            direction=port.direction.value,
                            port_type=port.type,
                            frame=port.frame,
                            required=port.required,
                            modeled_only=kind is ConnectionKind.SAFETY,
                        )
                    )
        edges: list[ConnectionEdge] = []
        for connection in sorted(cell.connections, key=lambda item: item.id):
            package = packages.get(connection.from_.component)
            port_type = "unknown"
            if package is not None:
                edge_port = next(
                    (
                        candidate
                        for candidate in _ports_for_kind(package.manifest, connection.kind)
                        if candidate.id == connection.from_.port
                    ),
                    None,
                )
                if edge_port is not None:
                    port_type = edge_port.type
            edges.append(_edge(connection, port_type))
        return ConnectionBrowserResult(
            ports=tuple(
                sorted(
                    ports,
                    key=lambda item: (
                        item.kind,
                        item.component_alias,
                        item.component_instance,
                        item.port,
                    ),
                )
            ),
            edges=tuple(edges),
            validation=findings,
            safety_disclaimer=SAFETY_DISCLAIMER,
        )

    def preview_mechanical(
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
        """Validate and preview a mechanical snap without changing either source buffer."""

        candidate = self._candidate(
            project_path,
            contents,
            connection_id=connection_id,
            kind=ConnectionKind.MECHANICAL.value,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
        )
        if isinstance(candidate, ConnectionEditResult):
            return candidate
        preview = _mechanical_preview(candidate, project_path.resolve() / "cell.yaml")
        if isinstance(preview, ValidationItem):
            return ConnectionEditResult(contents=None, validation=(preview,))
        return ConnectionEditResult(contents=None, preview=preview)

    def connect(
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
        """Create one validated edge and any required paired spatial edit in memory."""

        root = project_path.resolve()
        candidate = self._candidate(
            root,
            contents,
            connection_id=connection_id,
            kind=kind,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
        )
        if isinstance(candidate, ConnectionEditResult):
            return candidate

        preview: MechanicalSnapPreview | None = None
        scene_text = contents.scene_usda
        if candidate.connection.kind is ConnectionKind.MECHANICAL:
            mechanical = _mechanical_preview(candidate, root / "cell.yaml")
            if isinstance(mechanical, ValidationItem):
                return ConnectionEditResult(contents=None, validation=(mechanical,))
            preview = mechanical
            try:
                scene_text, path_updates = _apply_mechanical_snap(
                    scene_text,
                    source_prim=mechanical.source_prim,
                    target_prim=mechanical.current_target_prim,
                    snapped_target_prim=mechanical.snapped_target_prim,
                    connection_id=connection_id,
                    transform=mechanical.transform,
                )
            except ValueError as error:
                return _rejected(
                    "studio.mechanical-snap-failed",
                    root / candidate.cell.scene.usd,
                    str(error),
                )
            for component in candidate.data.get("components", []):
                current_path = component.get("usd_prim")
                if isinstance(current_path, str):
                    for old_prefix, new_prefix in path_updates:
                        if current_path == old_prefix or current_path.startswith(f"{old_prefix}/"):
                            component["usd_prim"] = f"{new_prefix}{current_path[len(old_prefix) :]}"
                            break

        connections = list(candidate.data.get("connections", []))
        connections.append(
            candidate.connection.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        candidate.data["connections"] = connections
        changed = ProjectContents(cell_yaml=_dump_yaml(candidate.data), scene_usda=scene_text)
        validation = _validate_pair(changed, root, root / candidate.cell.scene.usd)
        if validation:
            return ConnectionEditResult(contents=None, validation=validation)
        return ConnectionEditResult(
            contents=changed,
            connection_id=connection_id,
            edge=_edge(candidate.connection, candidate.from_port.type),
            preview=preview,
        )

    def _candidate(
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
    ) -> _ConnectionCandidate | ConnectionEditResult:
        root = project_path.resolve()
        parsed = _parse_cell(contents.cell_yaml, root / "cell.yaml")
        if not isinstance(parsed, _ParsedCell):
            return ConnectionEditResult(contents=None, validation=parsed)
        cell, data = parsed.model, parsed.data
        try:
            connection_kind = ConnectionKind(kind)
            config: dict[str, Any] = {}
            if connection_kind is ConnectionKind.SAFETY:
                config = {
                    "modeled_only": True,
                    "implementation": "external_rated_hardware",
                }
            connection = Connection(
                id=connection_id,
                kind=connection_kind,
                **{
                    "from": ConnectionEndpoint(component=from_component, port=from_port),
                    "to": ConnectionEndpoint(component=to_component, port=to_port),
                },
                config=config,
            )
        except (ValidationError, ValueError):
            return _rejected(
                "studio.connection-input-invalid",
                root / "cell.yaml",
                "Connection ID, kind, component IDs, and port IDs must be valid stable values.",
            )

        registry = self._registry(root)
        candidate_cell = cell.model_copy(update={"connections": (*cell.connections, connection)})
        report = resolve_cell(
            candidate_cell,
            registry,
            ExecutionMode.SIMULATION,
            source_name=str(root / "cell.yaml"),
        )
        index = len(cell.connections)
        candidate_path = f"#/connections/{index}"
        findings = tuple(
            _validation_item(item) for item in report.findings if candidate_path in item.path
        )
        resolved = next(
            (
                item
                for item in report.connections
                if item.id == connection.id
                and item.from_ == connection.from_
                and item.to == connection.to
                and item.kind is connection.kind
            ),
            None,
        )
        if findings or resolved is None:
            if not findings:
                findings = (
                    ValidationItem(
                        code="studio.connection-unresolved",
                        severity="error",
                        path=f"{root / 'cell.yaml'}{candidate_path}",
                        message="The domain resolver did not accept the proposed connection.",
                    ),
                )
            return ConnectionEditResult(contents=None, validation=findings)

        packages = {
            instance.id: registry.get(instance.component, instance.version)
            for instance in cell.components
        }
        from_package = packages.get(from_component)
        to_package = packages.get(to_component)
        if from_package is None or to_package is None:
            return _rejected(
                "studio.connection-component-unregistered",
                root / "cell.yaml",
                "Both connection endpoints must reference registered component instances.",
            )
        resolved_from = next(
            port
            for port in _ports_for_kind(from_package.manifest, connection_kind)
            if port.id == from_port
        )
        resolved_to = next(
            port
            for port in _ports_for_kind(to_package.manifest, connection_kind)
            if port.id == to_port
        )
        return _ConnectionCandidate(cell, data, connection, resolved_from, resolved_to)

    def _registry(self, project_path: Path) -> FilesystemComponentRegistry:
        schema_directory = resolve_project_schema_directory(project_path, self._canonical_schemas)
        schemas = SchemaRegistry.from_directory(schema_directory)
        return FilesystemComponentRegistry.from_directory(
            project_path / "components", schema_registry=schemas
        )


def _ports_for_kind(component: ComponentType, kind: ConnectionKind) -> tuple[Port, ...]:
    if kind is ConnectionKind.MECHANICAL:
        return component.ports.mechanical
    if kind is ConnectionKind.SOFTWARE:
        return component.ports.software
    if kind is ConnectionKind.INDUSTRIAL_IO:
        return component.ports.industrial_io
    return component.ports.safety


def _edge(connection: Connection, port_type: str) -> ConnectionEdge:
    modeled_only = connection.kind is ConnectionKind.SAFETY
    return ConnectionEdge(
        connection_id=connection.id,
        kind=connection.kind.value,
        from_component=connection.from_.component,
        from_port=connection.from_.port,
        to_component=connection.to.component,
        to_port=connection.to.port,
        port_type=port_type,
        modeled_only=modeled_only,
        executable=connection.kind in {ConnectionKind.SOFTWARE, ConnectionKind.INDUSTRIAL_IO},
    )


def _mechanical_preview(
    candidate: _ConnectionCandidate, source: Path
) -> MechanicalSnapPreview | ValidationItem:
    source_instance = next(
        item
        for item in candidate.cell.components
        if item.id == candidate.connection.from_.component
    )
    target_instance = next(
        item for item in candidate.cell.components if item.id == candidate.connection.to.component
    )
    if source_instance.id == target_instance.id:
        return ValidationItem(
            code="studio.mechanical-snap-cycle",
            severity="error",
            path=f"{source.resolve()}#/connections",
            message="A mechanical component instance cannot be snapped beneath itself.",
        )
    source_transform = _snap_transform(candidate.from_port)
    target_transform = _snap_transform(candidate.to_port)
    if source_transform is None or target_transform is None:
        return ValidationItem(
            code="studio.mechanical-snap-transform-missing",
            severity="error",
            path=f"{source.resolve()}#/connections",
            message=(
                "Both mechanical ports must declare metadata.snap_transform as 16 finite numbers "
                "before Cell Studio can preview or author a spatial snap."
            ),
        )
    try:
        relative = _matrix_multiply(source_transform, _matrix_inverse(target_transform))
    except ValueError:
        return ValidationItem(
            code="studio.mechanical-snap-transform-invalid",
            severity="error",
            path=f"{source.resolve()}#/connections",
            message="The target mechanical port snap transform is singular.",
        )
    leaf = target_instance.usd_prim.rstrip("/").rsplit("/", 1)[-1]
    snapped = f"{source_instance.usd_prim.rstrip('/')}/{leaf}"
    if source_instance.usd_prim.startswith(f"{target_instance.usd_prim.rstrip('/')}/"):
        return ValidationItem(
            code="studio.mechanical-snap-cycle",
            severity="error",
            path=f"{source.resolve()}#/connections",
            message="Mechanical snapping would create a cyclic USD prim hierarchy.",
        )
    return MechanicalSnapPreview(
        connection_id=candidate.connection.id,
        source_prim=source_instance.usd_prim,
        current_target_prim=target_instance.usd_prim,
        snapped_target_prim=snapped,
        source_frame=candidate.from_port.frame or candidate.from_port.id,
        target_frame=candidate.to_port.frame or candidate.to_port.id,
        transform=relative,
        adapter_required=False,
    )


def _snap_transform(port: Port) -> tuple[float, ...] | None:
    value = port.metadata.get("snap_transform")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 16:
        return None
    numbers: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            return None
        number = float(item)
        if not (-1.0e100 < number < 1.0e100):
            return None
        numbers.append(number)
    return tuple(numbers)


def _matrix_multiply(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(
        sum(left[row * 4 + index] * right[index * 4 + column] for index in range(4))
        for row in range(4)
        for column in range(4)
    )


def _matrix_inverse(matrix: tuple[float, ...]) -> tuple[float, ...]:
    augmented = [
        [*matrix[row * 4 : row * 4 + 4], *_IDENTITY_MATRIX[row * 4 : row * 4 + 4]]
        for row in range(4)
    ]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1.0e-12:
            raise ValueError("singular matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(4):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return tuple(value for row in augmented for value in row[4:])


def _apply_mechanical_snap(
    text: str,
    *,
    source_prim: str,
    target_prim: str,
    snapped_target_prim: str,
    connection_id: str,
    transform: tuple[float, ...],
) -> tuple[str, tuple[tuple[str, str], ...]]:
    spans = _prim_spans(text)
    source_matches = [item for item in spans if item.path == source_prim.rstrip("/")]
    target_matches = [item for item in spans if item.path == target_prim.rstrip("/")]
    if len(source_matches) != 1 or len(target_matches) != 1:
        raise ValueError(
            "The source and target component prims must each be editable exactly once."
        )
    if any(
        item.path == snapped_target_prim and item.path != target_prim.rstrip("/") for item in spans
    ):
        raise ValueError(f"The snapped USD prim path '{snapped_target_prim}' already exists.")

    target = target_matches[0]
    block_end = _line_end_after(text, target.close_brace + 1)
    block = text[target.start : block_end]
    block = _author_snap_metadata(block, connection_id, transform)
    if target_prim.rstrip("/") == snapped_target_prim.rstrip("/"):
        return f"{text[: target.start]}{block}{text[block_end:]}", ()

    without_target = f"{text[: target.start]}{text[block_end:]}"
    source_matches = [
        item for item in _prim_spans(without_target) if item.path == source_prim.rstrip("/")
    ]
    if len(source_matches) != 1:
        raise ValueError("The source component prim became unavailable during the snap edit.")
    source = source_matches[0]
    source_indent = without_target[without_target.rfind("\n", 0, source.start) + 1 : source.start]
    child_block = _reindent(block, f"{source_indent}    ")
    changed = (
        f"{without_target[: source.close_brace]}{child_block}{without_target[source.close_brace :]}"
    )
    return changed, ((target_prim.rstrip("/"), snapped_target_prim.rstrip("/")),)


def _author_snap_metadata(block: str, connection_id: str, transform: tuple[float, ...]) -> str:
    opening = block.find("{")
    if opening < 0:
        raise ValueError("The target component prim has no editable body.")
    line_start = block.rfind("\n", 0, opening) + 1
    opening_line = block[line_start:opening]
    base_indent = opening_line[: len(opening_line) - len(opening_line.lstrip())]
    indent = f"{base_indent}    "
    rows = [transform[index : index + 4] for index in range(0, 16, 4)]
    matrix = ", ".join("(" + ", ".join(f"{value:.12g}" for value in row) + ")" for row in rows)
    metadata = (
        f'\n{indent}custom string cellforge:mechanicalConnection = "{connection_id}"'
        f"\n{indent}matrix4d xformOp:transform = ({matrix})"
        f'\n{indent}uniform token[] xformOpOrder = ["xformOp:transform"]'
    )
    return f"{block[: opening + 1]}{metadata}{block[opening + 1 :]}"


def _line_end_after(text: str, position: int) -> int:
    if position < len(text) and text[position] == "\r":
        position += 1
    if position < len(text) and text[position] == "\n":
        position += 1
    return position


def _reindent(block: str, indent: str) -> str:
    lines = block.splitlines(keepends=True)
    nonempty = [line for line in lines if line.strip()]
    original = min(len(line) - len(line.lstrip()) for line in nonempty)
    return "".join(f"{indent}{line[original:]}" if line.strip() else line for line in lines)


def _rejected(code: str, source: Path, message: str) -> ConnectionEditResult:
    return ConnectionEditResult(
        contents=None,
        validation=(
            ValidationItem(
                code=code,
                severity="error",
                path=f"{source.resolve()}#",
                message=message,
            ),
        ),
    )


def _validation_item(finding: Any) -> ValidationItem:
    severity = finding.severity.value if hasattr(finding.severity, "value") else finding.severity
    return ValidationItem(
        code=finding.code,
        severity=severity,
        path=finding.path,
        message=finding.message,
    )
