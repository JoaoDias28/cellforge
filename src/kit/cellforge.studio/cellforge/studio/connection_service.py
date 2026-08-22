"""Pure typed connection browsing, validation, and paired YAML/USD transformations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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
    ConnectionCanvas,
    ConnectionEdge,
    ConnectionEditResult,
    ConnectionEndpointRef,
    ConnectionLayerView,
    ConnectionLayoutEntry,
    ConnectionLayoutMetadata,
    ConnectionPort,
    ConnectionPreview,
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
_LAYER_LABELS = {
    ConnectionKind.MECHANICAL.value: "MECHANICAL MOUNTS",
    ConnectionKind.SOFTWARE.value: "SOFTWARE / CAPABILITY",
    ConnectionKind.INDUSTRIAL_IO.value: "INDUSTRIAL I/O",
    ConnectionKind.SAFETY.value: "MODELED SAFETY (NON-EXECUTABLE)",
}
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


def deterministic_connection_id(
    kind: str,
    from_component: str,
    from_port: str,
    to_component: str,
    to_port: str,
) -> str:
    """Return the stable edge ID generated from immutable endpoint identities."""

    canonical = json.dumps(
        [kind, from_component, from_port, to_component, to_port],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{kind}-{hashlib.sha256(canonical).hexdigest()}"


DeterministicConnectionId = deterministic_connection_id


@dataclass(frozen=True, slots=True)
class _ConnectionCandidate:
    cell: CellProject
    data: dict[str, Any]
    connection: Connection
    from_port: Port
    to_port: Port
    scene_usda: str
    from_collision_asset: Path | None = None
    to_collision_asset: Path | None = None
    from_frames: tuple[str, ...] = ()
    to_frames: tuple[str, ...] = ()


class ConnectionAuthoringService:
    """Expose port graph data and create validated connection edits without Kit."""

    def __init__(self, canonical_schema_directory: Path) -> None:
        self._canonical_schemas = canonical_schema_directory.resolve()

    def browse(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        query: str = "",
        selected_endpoint_id: str | None = None,
        layout: ConnectionLayoutMetadata | None = None,
    ) -> ConnectionBrowserResult:
        """Return deterministic declared ports, graph edges, and derived canvas metadata."""

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
        findings = list(_validation_item(item) for item in report.findings)
        findings.extend(_safety_findings(cell, root))
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
        findings.extend(
            _existing_mechanical_findings(
                cell,
                parsed.data,
                packages,
                contents.scene_usda,
                root / "cell.yaml",
            )
        )
        sorted_ports = tuple(
            sorted(
                ports,
                key=lambda item: (
                    item.kind,
                    item.component_alias,
                    item.component_instance,
                    item.port,
                ),
            )
        )
        sorted_edges = tuple(edges)
        canvas = _build_canvas(
            sorted_ports,
            sorted_edges,
            query=query,
            selected_endpoint_id=selected_endpoint_id,
            layout=layout,
        )
        return ConnectionBrowserResult(
            ports=sorted_ports,
            edges=sorted_edges,
            validation=tuple(findings),
            safety_disclaimer=SAFETY_DISCLAIMER,
            canvas=canvas,
        )

    def search_ports(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        query: str,
        selected_endpoint_id: str | None = None,
        layout: ConnectionLayoutMetadata | None = None,
    ) -> ConnectionBrowserResult:
        """Return the same validated graph with DTO-driven palette filtering/highlighting."""

        return self.browse(
            project_path,
            contents,
            query=query,
            selected_endpoint_id=selected_endpoint_id,
            layout=layout,
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
        """Preview a typed edge and return candidate hashes without changing sources."""

        staged = self.connect(
            project_path,
            contents,
            connection_id=connection_id,
            kind=kind,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
        )
        if staged.contents is None:
            return staged
        return replace(staged, contents=None)

    def preview_connection(
        self,
        project_path: Path,
        contents: ProjectContents,
        **kwargs: Any,
    ) -> ConnectionEditResult:
        """Snake-case alias for :meth:`PreviewCellConnection`."""

        return self.PreviewCellConnection(project_path, contents, **kwargs)

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
        """Stage a validated edge in immutable in-memory canonical buffers."""

        return self.connect(
            project_path,
            contents,
            connection_id=connection_id,
            kind=kind,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
        )

    def stage_connection(
        self,
        project_path: Path,
        contents: ProjectContents,
        **kwargs: Any,
    ) -> ConnectionEditResult:
        """Snake-case alias for :meth:`StageCellConnection`."""

        return self.StageCellConnection(project_path, contents, **kwargs)

    def RemoveCellConnection(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        connection_id: str,
    ) -> ConnectionEditResult:
        """Remove one edge from an in-memory candidate, restoring a reversible mechanical snap."""

        root = project_path.resolve()
        parsed = _parse_cell(contents.cell_yaml, root / "cell.yaml")
        if not isinstance(parsed, _ParsedCell):
            return ConnectionEditResult(contents=None, validation=parsed)
        connection = next(
            (item for item in parsed.model.connections if item.id == connection_id), None
        )
        if connection is None:
            return _rejected(
                "studio.connection-not-found",
                root / "cell.yaml",
                f"Connection '{connection_id}' is not present in the candidate graph.",
            )

        scene_text = contents.scene_usda
        path_updates: tuple[tuple[str, str], ...] = ()
        if connection.kind is ConnectionKind.MECHANICAL:
            try:
                scene_text, path_updates = _restore_mechanical_snap(
                    scene_text,
                    parsed.model,
                    connection,
                )
            except ValueError as error:
                return _rejected(
                    "studio.mechanical-removal-not-reversible",
                    root / parsed.model.scene.usd,
                    str(error),
                )

        data = dict(parsed.data)
        data["connections"] = [
            item
            for item in data.get("connections", [])
            if not isinstance(item, Mapping) or item.get("id") != connection_id
        ]
        updated_components: list[dict[str, Any]] = []
        for raw_component in data.get("components", []):
            if not isinstance(raw_component, Mapping):
                continue
            component = dict(raw_component)
            current_path = component.get("usd_prim")
            if not isinstance(current_path, str):
                updated_components.append(component)
                continue
            for old_prefix, new_prefix in path_updates:
                if current_path == old_prefix or current_path.startswith(f"{old_prefix}/"):
                    component["usd_prim"] = f"{new_prefix}{current_path[len(old_prefix) :]}"
                    break
            updated_components.append(component)
        data["components"] = updated_components

        changed = ProjectContents(
            cell_yaml=_dump_yaml(data),
            scene_usda=scene_text,
            artifacts=contents.artifacts,
        )
        validation = _validate_pair(changed, root, root / parsed.model.scene.usd)
        if validation:
            return ConnectionEditResult(contents=None, validation=validation)
        warnings = _connection_removal_warnings(connection)
        return ConnectionEditResult(
            contents=changed,
            connection_id=connection_id,
            warnings=warnings,
        )

    def remove_connection(
        self,
        project_path: Path,
        contents: ProjectContents,
        **kwargs: Any,
    ) -> ConnectionEditResult:
        """Snake-case alias for :meth:`RemoveCellConnection`."""

        return self.RemoveCellConnection(project_path, contents, **kwargs)

    def ValidateCellConnections(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        query: str = "",
        selected_endpoint_id: str | None = None,
        layout: ConnectionLayoutMetadata | None = None,
    ) -> ConnectionBrowserResult:
        """Validate all connection layers through the existing resolver and spatial metadata."""

        return self.browse(
            project_path,
            contents,
            query=query,
            selected_endpoint_id=selected_endpoint_id,
            layout=layout,
        )

    def ValidateCellConnectionsForSave(
        self,
        project_path: Path,
        contents: ProjectContents,
    ) -> tuple[ValidationItem, ...]:
        """Return connection findings that must block canonical transactional replacement."""

        result = self.ValidateCellConnections(project_path, contents)
        save_codes = {
            "resolver.duplicate-connection-id",
            "resolver.duplicate-connection-endpoints",
            "studio.connection-safety-kind-mismatch",
            "studio.safety-edge-not-modeled-only",
        }
        return tuple(
            item
            for item in result.validation
            if item.code in save_codes or item.code.startswith("studio.mechanical-")
        )

    def validate_connections(
        self,
        project_path: Path,
        contents: ProjectContents,
        **kwargs: Any,
    ) -> ConnectionBrowserResult:
        """Snake-case alias for :meth:`ValidateCellConnections`."""

        return self.ValidateCellConnections(project_path, contents, **kwargs)

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

        return self.PreviewCellConnection(
            project_path,
            contents,
            connection_id=connection_id,
            kind=ConnectionKind.MECHANICAL.value,
            from_component=from_component,
            from_port=from_port,
            to_component=to_component,
            to_port=to_port,
        )

    def connect(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        connection_id: str | None,
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
        collision_findings: tuple[ValidationItem, ...] = ()
        payload_findings: tuple[ValidationItem, ...] = ()
        scene_text = contents.scene_usda
        if candidate.connection.kind is ConnectionKind.MECHANICAL:
            mechanical = _mechanical_preview(candidate, root / "cell.yaml")
            if isinstance(mechanical, ValidationItem):
                return ConnectionEditResult(contents=None, validation=(mechanical,))
            preview = mechanical
            collision_findings = mechanical.collision_findings
            payload_findings = mechanical.payload_findings
            try:
                scene_text, path_updates = _apply_mechanical_snap(
                    scene_text,
                    source_prim=mechanical.source_prim,
                    target_prim=mechanical.current_target_prim,
                    snapped_target_prim=mechanical.snapped_target_prim,
                    connection_id=candidate.connection.id,
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
        connection = candidate.connection
        if connection.kind is ConnectionKind.MECHANICAL and preview is not None:
            connection = connection.model_copy(
                update={
                    "config": {
                        **connection.config,
                        "_cellforge_spatial": {
                            "source_prim": preview.source_prim,
                            "previous_target_prim": preview.current_target_prim,
                            "snapped_target_prim": preview.snapped_target_prim,
                            "transform": list(preview.transform),
                            "authored_properties": list(
                                _snap_metadata_properties(
                                    candidate.connection.id, preview.transform
                                )
                            ),
                        },
                    }
                }
            )
        connections.append(connection.model_dump(mode="json", by_alias=True, exclude_none=True))
        candidate.data["connections"] = connections
        changed = ProjectContents(
            cell_yaml=_dump_yaml(candidate.data),
            scene_usda=scene_text,
            artifacts=contents.artifacts,
        )
        validation = _validate_pair(changed, root, root / candidate.cell.scene.usd)
        if validation:
            return ConnectionEditResult(contents=None, validation=validation)
        connection_preview = _connection_preview(
            connection,
            preview,
            changed,
            collision_findings=collision_findings,
            payload_findings=payload_findings,
        )
        return ConnectionEditResult(
            contents=changed,
            connection_id=connection.id,
            edge=_edge(connection, candidate.from_port.type),
            preview=preview,
            connection_preview=connection_preview,
        )

    def _candidate(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        connection_id: str | None,
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
            normalized_id = connection_id or deterministic_connection_id(
                connection_kind.value,
                from_component,
                from_port,
                to_component,
                to_port,
            )
            config: dict[str, Any] = {}
            modeled_only: bool | None = None
            if connection_kind is ConnectionKind.SAFETY:
                config = {
                    "modeled_only": True,
                    "implementation": "external_rated_hardware",
                }
                modeled_only = True
            connection = Connection(
                id=normalized_id,
                kind=connection_kind,
                **{
                    "from": ConnectionEndpoint(component=from_component, port=from_port),
                    "to": ConnectionEndpoint(component=to_component, port=to_port),
                },
                config=config,
                modeled_only=modeled_only,
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
            (
                port
                for port in _ports_for_kind(from_package.manifest, connection_kind)
                if port.id == from_port
            ),
            None,
        )
        resolved_to = next(
            (
                port
                for port in _ports_for_kind(to_package.manifest, connection_kind)
                if port.id == to_port
            ),
            None,
        )
        if resolved_from is None or resolved_to is None:
            return _rejected(
                "studio.connection-endpoint-ambiguous",
                root / "cell.yaml",
                "Each endpoint must resolve to exactly one declared port.",
            )
        capability_findings = _capability_findings(
            connection_kind,
            from_package.manifest,
            resolved_from,
            to_package.manifest,
            resolved_to,
            root / "cell.yaml",
        )
        if capability_findings:
            return ConnectionEditResult(contents=None, validation=capability_findings)
        return _ConnectionCandidate(
            cell,
            data,
            connection,
            resolved_from,
            resolved_to,
            contents.scene_usda,
            from_package.source_path.parent / from_package.manifest.assets.collision_usd,
            to_package.source_path.parent / to_package.manifest.assets.collision_usd,
            tuple(frame.id for frame in from_package.manifest.frames),
            tuple(frame.id for frame in to_package.manifest.frames),
        )

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


def _build_canvas(
    ports: tuple[ConnectionPort, ...],
    edges: tuple[ConnectionEdge, ...],
    *,
    query: str,
    selected_endpoint_id: str | None,
    layout: ConnectionLayoutMetadata | None,
) -> ConnectionCanvas:
    """Assemble presentation DTOs without interpreting any domain compatibility rule."""

    tokens = tuple(token.casefold() for token in query.split() if token.strip())
    palette = tuple(
        port for port in ports if all(token in _port_search_text(port) for token in tokens)
    )
    connected_to_selection = {
        endpoint_id
        for edge in edges
        if selected_endpoint_id
        and selected_endpoint_id in {edge.from_endpoint_id, edge.to_endpoint_id}
        for endpoint_id in (edge.from_endpoint_id, edge.to_endpoint_id)
    }
    highlighted = tuple(
        port.endpoint_id
        for port in ports
        if (tokens and port in palette)
        or port.endpoint_id == selected_endpoint_id
        or port.endpoint_id in connected_to_selection
    )
    layers = tuple(
        ConnectionLayerView(
            kind=kind,
            label=_LAYER_LABELS[kind],
            ports=tuple(port for port in ports if port.kind == kind),
            edges=tuple(edge for edge in edges if edge.kind == kind),
            modeled_only=kind == ConnectionKind.SAFETY.value,
        )
        for kind in (
            ConnectionKind.MECHANICAL.value,
            ConnectionKind.SOFTWARE.value,
            ConnectionKind.INDUSTRIAL_IO.value,
            ConnectionKind.SAFETY.value,
        )
    )
    normalized_layout = _normalize_layout(ports, edges, layout, selected_endpoint_id)
    return ConnectionCanvas(
        layers=layers,
        ports=ports,
        edges=edges,
        palette_ports=palette,
        query=query,
        highlighted_endpoint_ids=highlighted,
        layout=normalized_layout,
        safety_disclaimer=SAFETY_DISCLAIMER,
    )


def _port_search_text(port: ConnectionPort) -> str:
    return " ".join(
        (
            port.component_alias,
            port.component_instance,
            port.kind,
            port.port,
            port.direction,
            port.port_type,
            port.frame or "",
        )
    ).casefold()


def _normalize_layout(
    ports: tuple[ConnectionPort, ...],
    edges: tuple[ConnectionEdge, ...],
    layout: ConnectionLayoutMetadata | None,
    selected_endpoint_id: str | None,
) -> ConnectionLayoutMetadata:
    by_id = {entry.endpoint_id: entry for entry in (layout.entries if layout else ())}
    entries: list[ConnectionLayoutEntry] = []
    for index, port in enumerate(ports):
        existing = by_id.get(port.endpoint_id)
        if existing is not None:
            entries.append(existing)
            continue
        column = 0.0 if port.direction in {"output", "bidirectional"} else 420.0
        entries.append(
            ConnectionLayoutEntry(endpoint_id=port.endpoint_id, x=column, y=index * 36.0)
        )
    position_by_id = {entry.endpoint_id: (entry.x, entry.y) for entry in entries}
    routes: list[tuple[str, tuple[tuple[float, float], ...]]] = []
    requested_routes = dict(layout.routes) if layout else {}
    for edge in edges:
        route = requested_routes.get(edge.edge_id)
        if route is None:
            source = position_by_id.get(edge.from_endpoint_id, (0.0, 0.0))
            target = position_by_id.get(edge.to_endpoint_id, (420.0, 0.0))
            midpoint = ((source[0] + target[0]) / 2.0, (source[1] + target[1]) / 2.0)
            route = (source, midpoint, target)
        routes.append((edge.edge_id, tuple(route)))
    return ConnectionLayoutMetadata(
        entries=tuple(entries),
        routes=tuple(routes),
        selected_endpoint_id=(
            selected_endpoint_id
            if selected_endpoint_id is not None
            else (layout.selected_endpoint_id if layout else None)
        ),
    )


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


def _existing_mechanical_findings(
    cell: CellProject,
    data: dict[str, Any],
    packages: Mapping[str, Any],
    scene_usda: str,
    source: Path,
) -> tuple[ValidationItem, ...]:
    """Run the same non-mutating spatial checks for every persisted mechanical edge."""

    findings: list[ValidationItem] = []
    for index, connection in enumerate(cell.connections):
        if connection.kind is not ConnectionKind.MECHANICAL:
            continue
        from_package = packages.get(connection.from_.component)
        to_package = packages.get(connection.to.component)
        if from_package is None or to_package is None:
            continue
        from_port = next(
            (
                port
                for port in _ports_for_kind(from_package.manifest, connection.kind)
                if port.id == connection.from_.port
            ),
            None,
        )
        to_port = next(
            (
                port
                for port in _ports_for_kind(to_package.manifest, connection.kind)
                if port.id == connection.to.port
            ),
            None,
        )
        if from_port is None or to_port is None:
            continue
        candidate = _ConnectionCandidate(
            cell=cell,
            data=data,
            connection=connection,
            from_port=from_port,
            to_port=to_port,
            scene_usda=scene_usda,
            from_collision_asset=(
                from_package.source_path.parent / from_package.manifest.assets.collision_usd
            ),
            to_collision_asset=(
                to_package.source_path.parent / to_package.manifest.assets.collision_usd
            ),
            from_frames=tuple(frame.id for frame in from_package.manifest.frames),
            to_frames=tuple(frame.id for frame in to_package.manifest.frames),
        )
        result = _mechanical_preview(candidate, source)
        if isinstance(result, ValidationItem):
            findings.append(
                replace(
                    result,
                    path=f"{source.resolve()}#/connections/{index}",
                )
            )
            continue
        current_target = next(
            item.usd_prim.rstrip("/")
            for item in cell.components
            if item.id == connection.to.component
        )
        if current_target != result.snapped_target_prim.rstrip("/"):
            findings.append(
                ValidationItem(
                    code="studio.mechanical-snap-target-mismatch",
                    severity="error",
                    path=f"{source.resolve()}#/connections/{index}/to",
                    message=(
                        f"Mechanical connection '{connection.id}' expects target prim "
                        f"'{result.snapped_target_prim}', but the canonical component path is "
                        f"'{current_target}'."
                    ),
                )
            )
    return tuple(findings)


def _connection_preview(
    connection: Connection,
    mechanical: MechanicalSnapPreview | None,
    candidate: ProjectContents,
    *,
    collision_findings: tuple[ValidationItem, ...] = (),
    payload_findings: tuple[ValidationItem, ...] = (),
) -> ConnectionPreview:
    """Create a stable preview DTO from a fully validated in-memory candidate."""

    return ConnectionPreview(
        edge_id=connection.id,
        kind=connection.kind.value,
        from_endpoint=ConnectionEndpointRef(
            component_instance_id=connection.from_.component,
            port_id=connection.from_.port,
            kind=connection.kind.value,
        ),
        to_endpoint=ConnectionEndpointRef(
            component_instance_id=connection.to.component,
            port_id=connection.to.port,
            kind=connection.kind.value,
        ),
        candidate_cell_sha256=hashlib.sha256(candidate.cell_yaml.encode("utf-8")).hexdigest(),
        candidate_scene_sha256=hashlib.sha256(candidate.scene_usda.encode("utf-8")).hexdigest(),
        proposed_transform=mechanical.transform if mechanical else None,
        source_prim=mechanical.source_prim if mechanical else None,
        current_target_prim=mechanical.current_target_prim if mechanical else None,
        proposed_target_prim=mechanical.snapped_target_prim if mechanical else None,
        source_frame=mechanical.source_frame if mechanical else None,
        target_frame=mechanical.target_frame if mechanical else None,
        collision_findings=collision_findings,
        payload_findings=payload_findings,
        modeled_only=connection.kind is ConnectionKind.SAFETY,
        executable=connection.kind in {ConnectionKind.SOFTWARE, ConnectionKind.INDUSTRIAL_IO},
    )


def _safety_findings(cell: CellProject, source_root: Path) -> tuple[ValidationItem, ...]:
    """Reject metadata that attempts to make a non-safety edge safety-like or executable."""

    findings: list[ValidationItem] = []
    source = source_root / "cell.yaml"
    for index, connection in enumerate(cell.connections):
        modeled = connection.modeled_only
        config_modeled = connection.config.get("modeled_only")
        if connection.kind is ConnectionKind.SAFETY:
            if modeled is False or config_modeled is False:
                findings.append(
                    ValidationItem(
                        code="studio.safety-edge-not-modeled-only",
                        severity="error",
                        path=f"{source.resolve()}#/connections/{index}",
                        message="Safety-layer connections must remain modeled-only metadata.",
                    )
                )
        elif modeled is not None or config_modeled is True:
            findings.append(
                ValidationItem(
                    code="studio.connection-safety-kind-mismatch",
                    severity="error",
                    path=f"{source.resolve()}#/connections/{index}",
                    message="Only kind 'safety' may carry modeled-only connection metadata.",
                )
            )
    return tuple(findings)


def _capability_findings(
    kind: ConnectionKind,
    from_component: ComponentType,
    from_port: Port,
    to_component: ComponentType,
    to_port: Port,
    source: Path,
) -> tuple[ValidationItem, ...]:
    """Validate optional manifest capability bindings without duplicating resolver rules."""

    if kind is not ConnectionKind.SOFTWARE:
        return ()
    findings: list[ValidationItem] = []
    for side, component, port in (
        ("from", from_component, from_port),
        ("to", to_component, to_port),
    ):
        metadata = port.metadata
        requested = metadata.get("capability", metadata.get("capability_contract"))
        if not isinstance(requested, str) or not requested:
            continue
        if not any(item.contract == requested for item in component.capabilities):
            findings.append(
                ValidationItem(
                    code="studio.capability-unavailable",
                    severity="error",
                    path=f"{source.resolve()}#/connections/{side}/port",
                    message=(
                        f"Port '{port.id}' requests capability '{requested}', but component "
                        f"'{component.component.id}' does not declare that capability."
                    ),
                )
            )
    return tuple(findings)


def _connection_removal_warnings(connection: Connection) -> tuple[ValidationItem, ...]:
    if connection.kind is not ConnectionKind.SAFETY:
        return ()
    return (
        ValidationItem(
            code="studio.safety-edge-removal-review",
            severity="warning",
            path=f"#/connections/{connection.id}",
            message=(
                "A modeled safety dependency was removed from the engineering graph; independent "
                "rated safety review remains required and no hardware wiring was changed."
            ),
        ),
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
    if not _is_affine_matrix(source_transform) or not _is_affine_matrix(target_transform):
        return ValidationItem(
            code="studio.mechanical-snap-transform-invalid",
            severity="error",
            path=f"{source.resolve()}#/connections",
            message="Mechanical snap transforms must be finite affine 4x4 matrices.",
        )
    try:
        _matrix_inverse(source_transform)
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
    if candidate.from_port.frame and candidate.from_port.frame not in candidate.from_frames:
        return ValidationItem(
            code="studio.mechanical-frame-missing",
            severity="error",
            path=f"{source.resolve()}#/connections/from/port",
            message=f"Source frame '{candidate.from_port.frame}' is not declared by its component.",
        )
    if candidate.to_port.frame and candidate.to_port.frame not in candidate.to_frames:
        return ValidationItem(
            code="studio.mechanical-frame-missing",
            severity="error",
            path=f"{source.resolve()}#/connections/to/port",
            message=f"Target frame '{candidate.to_port.frame}' is not declared by its component.",
        )
    spans = _prim_spans(candidate.scene_usda)
    source_matches = [item for item in spans if item.path == source_instance.usd_prim.rstrip("/")]
    target_matches = [item for item in spans if item.path == target_instance.usd_prim.rstrip("/")]
    if len(source_matches) == 0 or len(target_matches) == 0:
        return ValidationItem(
            code="studio.mechanical-snap-failed",
            severity="error",
            path=f"{source.resolve()}#/connections",
            message=(
                "Mechanical snap source and target prim paths must be present in the editable "
                "scene."
            ),
        )
    if len(source_matches) != 1 or len(target_matches) != 1:
        return ValidationItem(
            code="studio.mechanical-snap-path-ambiguous",
            severity="error",
            path=f"{source.resolve()}#/connections",
            message="Mechanical snap source and target prim paths must each resolve exactly once.",
        )
    if snapped != target_instance.usd_prim.rstrip("/") and any(
        item.path == snapped for item in spans
    ):
        return ValidationItem(
            code="studio.mechanical-snap-path-ambiguous",
            severity="error",
            path=f"{source.resolve()}#/connections",
            message=f"The generated target prim path '{snapped}' is already occupied.",
        )
    collision_findings = _collision_findings(candidate, source)
    payload_findings = _payload_findings(candidate, source)
    blocking = tuple(
        item for item in (*collision_findings, *payload_findings) if item.severity == "error"
    )
    if blocking:
        return blocking[0]
    return MechanicalSnapPreview(
        connection_id=candidate.connection.id,
        source_prim=source_instance.usd_prim,
        current_target_prim=target_instance.usd_prim,
        snapped_target_prim=snapped,
        source_frame=candidate.from_port.frame or candidate.from_port.id,
        target_frame=candidate.to_port.frame or candidate.to_port.id,
        transform=relative,
        adapter_required=False,
        collision_findings=collision_findings,
        payload_findings=payload_findings,
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


def _is_affine_matrix(matrix: tuple[float, ...] | None) -> bool:
    if matrix is None:
        return False
    return matrix[12:15] == (0.0, 0.0, 0.0) and abs(matrix[15] - 1.0) < 1.0e-12


def _collision_findings(
    candidate: _ConnectionCandidate, source: Path
) -> tuple[ValidationItem, ...]:
    """Check declared collision assets without claiming a physics/collision simulation result."""

    findings: list[ValidationItem] = []
    for side, asset in (
        ("from", candidate.from_collision_asset),
        ("to", candidate.to_collision_asset),
    ):
        if asset is None or not asset.is_file():
            findings.append(
                ValidationItem(
                    code="studio.mechanical-collision-asset-missing",
                    severity="error",
                    path=f"{source.resolve()}#/connections/{side}/port",
                    message=(
                        "Every mechanically connected component must declare an existing "
                        "collision asset."
                    ),
                )
            )
    return tuple(findings)


def _payload_findings(candidate: _ConnectionCandidate, source: Path) -> tuple[ValidationItem, ...]:
    """Validate only explicit payload metadata; unknown payload is never silently authorized."""

    source_port_payload = candidate.from_port.metadata.get("payload_kg")
    target_limit = candidate.to_port.metadata.get("max_payload_kg")
    if isinstance(source_port_payload, (int, float)) and not isinstance(source_port_payload, bool):
        if isinstance(target_limit, (int, float)) and not isinstance(target_limit, bool):
            if float(source_port_payload) > float(target_limit):
                return (
                    ValidationItem(
                        code="studio.mechanical-payload-exceeded",
                        severity="error",
                        path=f"{source.resolve()}#/connections",
                        message=(
                            f"Declared payload {float(source_port_payload):g} kg exceeds the "
                            "target "
                            f"mount limit {float(target_limit):g} kg."
                        ),
                    ),
                )
    return ()


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


def _restore_mechanical_snap(
    text: str,
    cell: CellProject,
    connection: Connection,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Reverse a staged mechanical reparent using its immutable authored record."""

    source_instance = next(
        (item for item in cell.components if item.id == connection.from_.component), None
    )
    target_instance = next(
        (item for item in cell.components if item.id == connection.to.component), None
    )
    if source_instance is None or target_instance is None:
        raise ValueError(
            "Both mechanical endpoint instances must remain present to remove the edge."
        )
    current_target = target_instance.usd_prim.rstrip("/")
    spatial = connection.config.get("_cellforge_spatial")
    if not isinstance(spatial, Mapping):
        raise ValueError("The mechanical edge has no recorded authored spatial edit.")
    source_prim = spatial.get("source_prim")
    previous_target = spatial.get("previous_target_prim")
    snapped_target = spatial.get("snapped_target_prim")
    authored_properties = spatial.get("authored_properties")
    if (
        not isinstance(source_prim, str)
        or not source_prim
        or not isinstance(previous_target, str)
        or not previous_target
        or not isinstance(snapped_target, str)
        or not snapped_target
    ):
        raise ValueError("The mechanical edge has an incomplete authored spatial record.")
    if not isinstance(authored_properties, Sequence) or isinstance(
        authored_properties, (str, bytes)
    ):
        raise ValueError("The mechanical edge has no exact authored transform property record.")
    authored_property_values: list[str] = []
    for value in authored_properties:
        if not isinstance(value, str) or not value:
            raise ValueError("The mechanical edge has no exact authored transform property record.")
        authored_property_values.append(value)
    if source_instance.usd_prim.rstrip("/") != source_prim.rstrip("/"):
        raise ValueError("The mechanical source prim no longer matches its recorded snap source.")
    if current_target != snapped_target.rstrip("/"):
        raise ValueError("The mechanical target prim no longer matches its recorded snap target.")

    if current_target == previous_target.rstrip("/"):
        return (
            _strip_snap_metadata(
                text,
                current_target,
                connection.id,
                tuple(authored_property_values),
            ),
            (),
        )

    spans = _prim_spans(text)
    current_matches = [item for item in spans if item.path == current_target]
    if len(current_matches) != 1:
        raise ValueError(
            "The current mechanically attached target prim is not editable exactly once."
        )
    if any(item.path == previous_target.rstrip("/") for item in spans):
        raise ValueError(f"The original target prim path '{previous_target}' is already occupied.")
    current = current_matches[0]
    block_end = _line_end_after(text, current.close_brace + 1)
    block = _strip_snap_block(
        text[current.start : block_end],
        connection.id,
        tuple(authored_property_values),
    )
    without_target = f"{text[: current.start]}{text[block_end:]}"
    parents = [
        item
        for item in _prim_spans(without_target)
        if item.path == previous_target.rsplit("/", 1)[0]
    ]
    if not parents:
        raise ValueError("The original parent prim for mechanical removal is not editable.")
    if len(parents) != 1:
        raise ValueError("The original parent prim for mechanical removal is ambiguous.")
    parent_span = parents[0]
    line_start = without_target.rfind("\n", 0, parent_span.start) + 1
    parent_indent = without_target[line_start : parent_span.start]
    child_block = _reindent(block, f"{parent_indent}    ")
    changed = (
        f"{without_target[: parent_span.close_brace]}"
        f"{child_block}{without_target[parent_span.close_brace :]}"
    )
    return changed, ((current_target, previous_target.rstrip("/")),)


def _strip_snap_metadata(
    text: str,
    path: str,
    connection_id: str,
    authored_properties: tuple[str, ...],
) -> str:
    spans = [item for item in _prim_spans(text) if item.path == path.rstrip("/")]
    if len(spans) != 1:
        raise ValueError("The mechanically attached target prim is not editable exactly once.")
    span = spans[0]
    end = _line_end_after(text, span.close_brace + 1)
    block = _strip_snap_block(text[span.start : end], connection_id, authored_properties)
    return f"{text[: span.start]}{block}{text[end:]}"


def _strip_snap_block(
    block: str,
    connection_id: str,
    authored_properties: tuple[str, ...],
) -> str:
    top_level = _top_level_prim_lines(block)
    marker = f'custom string cellforge:mechanicalConnection = "{connection_id}"'
    if top_level.count(marker) != 1:
        raise ValueError("The mechanical target prim does not carry the recorded snap marker.")
    if any(top_level.count(property_line) != 1 for property_line in authored_properties):
        raise ValueError("The recorded mechanical transform property block was changed.")
    generated_tokens = (
        "cellforge:mechanicalConnection",
        "xformOp:transform",
        "xformOpOrder",
    )
    if any(
        any(token in line for token in generated_tokens) and line not in authored_properties
        for line in top_level
    ):
        raise ValueError("The mechanical target prim contains an unrecorded snap property.")
    return "".join(
        line for line in block.splitlines(keepends=True) if line.strip() not in authored_properties
    )


def _snap_metadata_properties(connection_id: str, transform: tuple[float, ...]) -> tuple[str, ...]:
    rows = [transform[index : index + 4] for index in range(0, 16, 4)]
    matrix = ", ".join("(" + ", ".join(f"{value:.12g}" for value in row) + ")" for row in rows)
    return (
        f'custom string cellforge:mechanicalConnection = "{connection_id}"',
        f"matrix4d xformOp:transform = ({matrix})",
        'uniform token[] xformOpOrder = ["xformOp:transform"]',
    )


def _top_level_prim_lines(block: str) -> tuple[str, ...]:
    """Return direct prim-body lines without confusing nested component properties."""

    depth = 0
    lines: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped and depth == 1:
            lines.append(stripped)
        depth += line.count("{") - line.count("}")
    return tuple(lines)


def _author_snap_metadata(block: str, connection_id: str, transform: tuple[float, ...]) -> str:
    opening = block.find("{")
    if opening < 0:
        raise ValueError("The target component prim has no editable body.")
    line_start = block.rfind("\n", 0, opening) + 1
    opening_line = block[line_start:opening]
    base_indent = opening_line[: len(opening_line) - len(opening_line.lstrip())]
    indent = f"{base_indent}    "
    existing = _top_level_prim_lines(block)
    if any(
        "cellforge:mechanicalConnection" in line
        or "xformOp:transform" in line
        or "xformOpOrder" in line
        for line in existing
    ):
        raise ValueError(
            "The target component prim already declares transform or snap metadata; "
            "mechanical snap editing is not safe without an authored property block."
        )
    metadata = "".join(
        f"\n{indent}{line}" for line in _snap_metadata_properties(connection_id, transform)
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
