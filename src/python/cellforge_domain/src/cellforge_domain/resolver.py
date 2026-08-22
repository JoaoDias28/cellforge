"""Pure component, port, capability, and execution-mode resolution."""

from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field

from cellforge_domain.base import DomainModel
from cellforge_domain.findings import FindingSeverity, ValidationFinding
from cellforge_domain.identifiers import (
    ComponentTypeIdentifier,
    SemanticVersion,
    StableIdentifier,
)
from cellforge_domain.models import (
    AdapterMode,
    CapabilityImplementation,
    CellProject,
    ComponentInstance,
    ComponentType,
    Connection,
    ConnectionEndpoint,
    ConnectionKind,
    ExecutionMode,
    Port,
    PortDirection,
    SupportLevel,
)
from cellforge_domain.registry import FilesystemComponentRegistry, RegisteredComponentPackage


class DependencyNodeKind(StrEnum):
    COMPONENT = "component"
    TASK = "task"


class DependencyEdgeKind(StrEnum):
    CONNECTION = "connection"
    CAPABILITY = "capability"


class ResolvedComponent(DomainModel):
    instance_id: StableIdentifier
    component: ComponentTypeIdentifier
    version: SemanticVersion
    package_path: str


class ResolvedConnection(DomainModel):
    id: StableIdentifier
    kind: ConnectionKind
    from_: ConnectionEndpoint = Field(alias="from")
    to: ConnectionEndpoint
    port_type: StableIdentifier


class ResolvedCapability(DomainModel):
    task_id: StableIdentifier
    contract: StableIdentifier
    version: SemanticVersion
    provider_instance: StableIdentifier
    endpoint: StableIdentifier


class DependencyNode(DomainModel):
    id: StableIdentifier
    kind: DependencyNodeKind
    component: ComponentTypeIdentifier | None = None
    version: SemanticVersion | None = None


class DependencyEdge(DomainModel):
    id: StableIdentifier
    kind: DependencyEdgeKind
    source: StableIdentifier
    target: StableIdentifier
    contract: StableIdentifier | None = None
    version: SemanticVersion | None = None


class DependencyGraph(DomainModel):
    nodes: tuple[DependencyNode, ...]
    edges: tuple[DependencyEdge, ...]


class ResolutionReport(DomainModel):
    """Deterministic resolver output suitable for CLI, Studio, and compiler consumers."""

    mode: ExecutionMode
    valid: bool
    components: tuple[ResolvedComponent, ...]
    connections: tuple[ResolvedConnection, ...]
    capabilities: tuple[ResolvedCapability, ...]
    graph: DependencyGraph
    findings: tuple[ValidationFinding, ...]


def resolve_cell(
    cell: CellProject,
    registry: FilesystemComponentRegistry,
    mode: ExecutionMode,
    *,
    source_name: str = "cell.yaml",
) -> ResolutionReport:
    """Resolve one validated cell graph without importing runtime or adapter implementations."""

    findings = list(registry.findings)
    packages_by_instance: dict[str, RegisteredComponentPackage] = {}
    compatible_instances: set[str] = set()
    resolved_components: list[ResolvedComponent] = []

    indexed_instances = sorted(enumerate(cell.components), key=lambda item: item[1].id)
    for original_index, instance in indexed_instances:
        package = registry.get(instance.component, instance.version)
        component_path = f"{source_name}#/components/{original_index}"
        if package is None:
            available_versions = registry.versions(instance.component)
            if available_versions:
                findings.append(
                    _finding(
                        "resolver.component-version-conflict",
                        f"{component_path}/version",
                        (
                            f"Component '{instance.component}' version '{instance.version}' is not "
                            f"registered; available versions: {', '.join(available_versions)}."
                        ),
                    )
                )
            else:
                findings.append(
                    _finding(
                        "resolver.component-missing",
                        f"{component_path}/component",
                        f"Component '{instance.component}' is not registered.",
                    )
                )
            continue

        packages_by_instance[instance.id] = package
        resolved_components.append(
            ResolvedComponent(
                instance_id=instance.id,
                component=instance.component,
                version=instance.version,
                package_path=package.package_path,
            )
        )
        mode_findings = component_mode_findings(instance, package.manifest, mode, component_path)
        findings.extend(mode_findings)
        if not mode_findings:
            compatible_instances.add(instance.id)

    resolved_connections, connection_edges, connection_findings = _resolve_connections(
        cell,
        packages_by_instance,
        source_name,
    )
    findings.extend(connection_findings)

    resolved_capabilities, capability_edges, capability_findings = _resolve_capabilities(
        cell,
        packages_by_instance,
        compatible_instances,
        mode,
        source_name,
    )
    findings.extend(capability_findings)

    nodes = [
        DependencyNode(
            id=f"component.{component.instance_id}",
            kind=DependencyNodeKind.COMPONENT,
            component=component.component,
            version=component.version,
        )
        for component in resolved_components
    ]
    nodes.extend(
        DependencyNode(id=f"task.{task.id}", kind=DependencyNodeKind.TASK)
        for task in sorted(cell.tasks, key=lambda item: item.id)
    )

    sorted_findings = tuple(sorted(findings, key=_finding_sort_key))
    return ResolutionReport(
        mode=mode,
        valid=not any(finding.severity == FindingSeverity.ERROR for finding in sorted_findings),
        components=tuple(sorted(resolved_components, key=lambda item: item.instance_id)),
        connections=tuple(sorted(resolved_connections, key=lambda item: item.id)),
        capabilities=tuple(
            sorted(
                resolved_capabilities,
                key=lambda item: (item.task_id, item.contract, item.provider_instance),
            )
        ),
        graph=DependencyGraph(
            nodes=tuple(sorted(nodes, key=lambda item: item.id)),
            edges=tuple(sorted((*connection_edges, *capability_edges), key=lambda item: item.id)),
        ),
        findings=sorted_findings,
    )


def component_mode_findings(
    instance: ComponentInstance,
    component: ComponentType,
    mode: ExecutionMode,
    component_path: str,
) -> tuple[ValidationFinding, ...]:
    """Return canonical engineering compatibility findings for one execution mode.

    Browser badges and final cell resolution share this policy. These findings do not authorize
    operation and do not implement a safety function.
    """
    findings: list[ValidationFinding] = []
    level = component.support.level

    if level == SupportLevel.DEPRECATED:
        findings.append(
            _finding(
                "resolver.support-level-unsupported",
                f"{component_path}/component",
                (
                    f"Deprecated component '{component.component.id}' cannot be selected for new "
                    "cells."
                ),
            )
        )
    elif mode == ExecutionMode.SIMULATION and level == SupportLevel.METADATA_ONLY:
        findings.append(
            _finding(
                "resolver.support-level-unsupported",
                f"{component_path}/component",
                f"Component '{component.component.id}' has no executable simulation support.",
            )
        )
    elif mode == ExecutionMode.COMMISSIONING and level not in {
        SupportLevel.BENCH_TESTED,
        SupportLevel.PRODUCTION_QUALIFIED,
    }:
        findings.append(
            _finding(
                "resolver.support-level-unsupported",
                f"{component_path}/component",
                f"Component '{component.component.id}' is not supported for commissioning.",
            )
        )
    elif mode == ExecutionMode.PRODUCTION and level != SupportLevel.PRODUCTION_QUALIFIED:
        findings.append(
            _finding(
                "resolver.support-level-unsupported",
                f"{component_path}/component",
                f"Component '{component.component.id}' is not production-qualified.",
            )
        )

    required_adapter = (
        component.adapters.simulation
        if mode == ExecutionMode.SIMULATION
        else component.adapters.hardware
    )
    if required_adapter is None:
        findings.append(
            _finding(
                "resolver.adapter-missing",
                f"{component_path}/adapter_mode",
                f"Component '{component.component.id}' has no {mode.value} adapter.",
            )
        )

    incompatible_selection = (
        mode == ExecutionMode.SIMULATION and instance.adapter_mode == AdapterMode.HARDWARE
    ) or (mode != ExecutionMode.SIMULATION and instance.adapter_mode == AdapterMode.SIMULATION)
    if incompatible_selection:
        findings.append(
            _finding(
                "resolver.adapter-mode-incompatible",
                f"{component_path}/adapter_mode",
                (
                    f"Instance adapter mode '{instance.adapter_mode.value}' is incompatible with "
                    f"'{mode.value}' resolution."
                ),
            )
        )

    return tuple(findings)


def _resolve_connections(
    cell: CellProject,
    packages_by_instance: dict[str, RegisteredComponentPackage],
    source_name: str,
) -> tuple[list[ResolvedConnection], list[DependencyEdge], list[ValidationFinding]]:
    resolved: list[ResolvedConnection] = []
    edges: list[DependencyEdge] = []
    findings: list[ValidationFinding] = []
    instance_ids = {instance.id for instance in cell.components}
    duplicate_ids = _duplicates(connection.id for connection in cell.connections)
    endpoint_tuples = [
        (
            connection.kind.value,
            connection.from_.component,
            connection.from_.port,
            connection.to.component,
            connection.to.port,
        )
        for connection in cell.connections
    ]
    duplicate_endpoint_tuples = _duplicates(endpoint_tuples)

    for original_index, connection in sorted(
        enumerate(cell.connections), key=lambda item: (item[1].id, item[0])
    ):
        connection_path = f"{source_name}#/connections/{original_index}"
        if connection.id in duplicate_ids:
            findings.append(
                _finding(
                    "resolver.duplicate-connection-id",
                    f"{connection_path}/id",
                    f"Connection ID '{connection.id}' is not unique within the cell.",
                )
            )
        endpoint_tuple = (
            connection.kind.value,
            connection.from_.component,
            connection.from_.port,
            connection.to.component,
            connection.to.port,
        )
        if endpoint_tuple in duplicate_endpoint_tuples:
            findings.append(
                _finding(
                    "resolver.duplicate-connection-endpoints",
                    f"{connection_path}/from",
                    (
                        "Connection endpoint tuple "
                        f"({connection.kind.value}, "
                        f"{connection.from_.component}:{connection.from_.port}, "
                        f"{connection.to.component}:{connection.to.port}) is not unique "
                        "within the cell."
                    ),
                )
            )

        from_port = _resolve_endpoint(
            connection,
            connection.from_,
            "from",
            packages_by_instance,
            instance_ids,
            connection_path,
            findings,
        )
        to_port = _resolve_endpoint(
            connection,
            connection.to,
            "to",
            packages_by_instance,
            instance_ids,
            connection_path,
            findings,
        )
        if from_port is None or to_port is None:
            continue

        if from_port.direction not in {PortDirection.OUTPUT, PortDirection.BIDIRECTIONAL}:
            findings.append(
                _finding(
                    "resolver.port-direction-incompatible",
                    f"{connection_path}/from/port",
                    f"Source port '{from_port.id}' does not provide an output direction.",
                )
            )
        if to_port.direction not in {PortDirection.INPUT, PortDirection.BIDIRECTIONAL}:
            findings.append(
                _finding(
                    "resolver.port-direction-incompatible",
                    f"{connection_path}/to/port",
                    f"Target port '{to_port.id}' does not accept an input direction.",
                )
            )

        if from_port.type != to_port.type:
            code = (
                "resolver.mechanical-port-incompatible"
                if connection.kind == ConnectionKind.MECHANICAL
                else "resolver.port-type-incompatible"
            )
            findings.append(
                _finding(
                    code,
                    connection_path,
                    (
                        f"Port types '{from_port.type}' and '{to_port.type}' are incompatible for "
                        f"connection '{connection.id}'."
                    ),
                )
            )
            continue

        resolved.append(
            ResolvedConnection(
                id=connection.id,
                kind=connection.kind,
                **{"from": connection.from_},
                to=connection.to,
                port_type=from_port.type,
            )
        )
        edges.append(
            DependencyEdge(
                id=f"connection.{connection.id}",
                kind=DependencyEdgeKind.CONNECTION,
                source=f"component.{connection.from_.component}",
                target=f"component.{connection.to.component}",
            )
        )

    return resolved, edges, findings


def _resolve_endpoint(
    connection: Connection,
    endpoint: ConnectionEndpoint,
    endpoint_name: str,
    packages_by_instance: dict[str, RegisteredComponentPackage],
    instance_ids: set[str],
    connection_path: str,
    findings: list[ValidationFinding],
) -> Port | None:
    endpoint_path = f"{connection_path}/{endpoint_name}"
    if endpoint.component not in instance_ids:
        findings.append(
            _finding(
                "resolver.connection-component-missing",
                f"{endpoint_path}/component",
                f"Connection references unknown instance '{endpoint.component}'.",
            )
        )
        return None

    package = packages_by_instance.get(endpoint.component)
    if package is None:
        return None

    ports = _ports_for_kind(package.manifest, connection.kind)
    port = next((candidate for candidate in ports if candidate.id == endpoint.port), None)
    if port is None:
        findings.append(
            _finding(
                "resolver.port-missing",
                f"{endpoint_path}/port",
                (
                    f"Component instance '{endpoint.component}' has no {connection.kind.value} "
                    f"port '{endpoint.port}'."
                ),
            )
        )
    return port


def _ports_for_kind(component: ComponentType, kind: ConnectionKind) -> tuple[Port, ...]:
    if kind == ConnectionKind.MECHANICAL:
        return component.ports.mechanical
    if kind == ConnectionKind.SOFTWARE:
        return component.ports.software
    if kind == ConnectionKind.INDUSTRIAL_IO:
        return component.ports.industrial_io
    return component.ports.safety


def _resolve_capabilities(
    cell: CellProject,
    packages_by_instance: dict[str, RegisteredComponentPackage],
    compatible_instances: set[str],
    mode: ExecutionMode,
    source_name: str,
) -> tuple[list[ResolvedCapability], list[DependencyEdge], list[ValidationFinding]]:
    implementations: dict[str, list[tuple[str, CapabilityImplementation]]] = {}
    for instance_id, package in packages_by_instance.items():
        for implementation in package.manifest.capabilities:
            implementations.setdefault(implementation.contract, []).append(
                (instance_id, implementation)
            )

    resolved: list[ResolvedCapability] = []
    edges: list[DependencyEdge] = []
    findings: list[ValidationFinding] = []
    duplicate_task_ids = _duplicates(task.id for task in cell.tasks)
    for task_index, task in sorted(enumerate(cell.tasks), key=lambda item: (item[1].id, item[0])):
        task_path = f"{source_name}#/tasks/{task_index}"
        if task.id in duplicate_task_ids:
            findings.append(
                _finding(
                    "resolver.duplicate-task-id",
                    f"{task_path}/id",
                    f"Task ID '{task.id}' is not unique within the cell.",
                )
            )

        for capability in sorted(set(task.required_capabilities)):
            candidates = implementations.get(capability, [])
            if not candidates:
                findings.append(
                    _finding(
                        "resolver.capability-missing",
                        f"{task_path}/required_capabilities",
                        f"No component provides required capability '{capability}'.",
                    )
                )
                continue

            mode_candidates = [
                (instance_id, implementation)
                for instance_id, implementation in candidates
                if mode in implementation.modes and instance_id in compatible_instances
            ]
            if not mode_candidates:
                findings.append(
                    _finding(
                        "resolver.capability-mode-unsupported",
                        f"{task_path}/required_capabilities",
                        (
                            f"Capability '{capability}' has no provider compatible with "
                            f"'{mode.value}'."
                        ),
                    )
                )
                continue

            versions = sorted({implementation.version for _, implementation in mode_candidates})
            if len(versions) > 1:
                findings.append(
                    _finding(
                        "resolver.capability-version-conflict",
                        f"{task_path}/required_capabilities",
                        (
                            f"Capability '{capability}' is provided at conflicting versions: "
                            f"{', '.join(versions)}."
                        ),
                    )
                )
                continue

            if len(mode_candidates) > 1:
                providers = ", ".join(sorted(instance_id for instance_id, _ in mode_candidates))
                findings.append(
                    _finding(
                        "resolver.capability-provider-ambiguous",
                        f"{task_path}/required_capabilities",
                        f"Capability '{capability}' has multiple providers: {providers}.",
                    )
                )
                continue

            provider_instance, implementation = mode_candidates[0]
            resolved.append(
                ResolvedCapability(
                    task_id=task.id,
                    contract=capability,
                    version=implementation.version,
                    provider_instance=provider_instance,
                    endpoint=implementation.endpoint,
                )
            )
            edges.append(
                DependencyEdge(
                    id=f"capability.{task.id}.{capability}",
                    kind=DependencyEdgeKind.CAPABILITY,
                    source=f"task.{task.id}",
                    target=f"component.{provider_instance}",
                    contract=capability,
                    version=implementation.version,
                )
            )

    return resolved, edges, findings


def _duplicates[T](values: Iterable[T]) -> set[T]:
    seen: set[T] = set()
    duplicates: set[T] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _finding(code: str, path: str, message: str) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        severity=FindingSeverity.ERROR,
        path=path,
        message=message,
    )


def _finding_sort_key(finding: ValidationFinding) -> tuple[str, str, str]:
    return finding.path, finding.code, finding.message
