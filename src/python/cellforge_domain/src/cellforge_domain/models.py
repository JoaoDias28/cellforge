"""Pure Pydantic domain models for canonical CellForge documents."""

from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, JsonValue, field_validator, model_validator

from cellforge_domain.base import DomainModel
from cellforge_domain.identifiers import (
    ComponentTypeIdentifier,
    SemanticVersion,
    Sha256Digest,
    StableIdentifier,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveSeconds = Annotated[float, Field(gt=0)]
NonNegativeSize = Annotated[int, Field(ge=0)]
RecipeVersion = Annotated[int, Field(ge=1)]
GitRevision = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
JsonObject = dict[str, JsonValue]


def _require_unique(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} entries must be unique")
    return values


class ComponentKind(StrEnum):
    ROBOT = "robot"
    END_EFFECTOR = "end_effector"
    SENSOR = "sensor"
    PROCESS_MACHINE = "process_machine"
    FIXTURE = "fixture"
    CONVEYOR = "conveyor"
    EXTERNAL_AXIS = "external_axis"
    IO_MODULE = "io_module"
    PRODUCT_CARRIER = "product_carrier"
    PASSIVE_GEOMETRY = "passive_geometry"
    SAFETY_DEVICE = "safety_device"


class FrameRole(StrEnum):
    ROOT = "root"
    MOUNT = "mount"
    TOOL = "tool"
    SENSOR = "sensor"
    PROCESS = "process"
    CALIBRATION = "calibration"
    PRODUCT = "product"


class PortDirection(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"


class ConnectionKind(StrEnum):
    MECHANICAL = "mechanical"
    SOFTWARE = "software"
    INDUSTRIAL_IO = "industrial_io"
    SAFETY = "safety"


class ExecutionMode(StrEnum):
    SIMULATION = "simulation"
    COMMISSIONING = "commissioning"
    PRODUCTION = "production"


class AdapterMode(StrEnum):
    SIMULATION = "simulation"
    HARDWARE = "hardware"
    TARGET_SELECTED = "target_selected"


class SupportLevel(StrEnum):
    METADATA_ONLY = "metadata_only"
    SIMULATED = "simulated"
    BENCH_TESTED = "bench_tested"
    PRODUCTION_QUALIFIED = "production_qualified"
    DEPRECATED = "deprecated"


class SimulationLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class RecipeStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    TESTED = "TESTED"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class CpuArchitecture(StrEnum):
    AMD64 = "amd64"
    ARM64 = "arm64"


class ComponentIdentity(DomainModel):
    id: ComponentTypeIdentifier
    version: SemanticVersion
    kind: ComponentKind
    name: NonEmptyString
    manufacturer: str | None = None
    model: str | None = None
    description: str | None = None
    license: str | None = None


class ComponentAssets(DomainModel):
    visual_usd: NonEmptyString
    collision_usd: NonEmptyString
    urdf: NonEmptyString | None = None
    srdf: NonEmptyString | None = None
    thumbnail: NonEmptyString | None = None


class ComponentFrame(DomainModel):
    id: StableIdentifier
    role: FrameRole
    usd_prim: NonEmptyString | None = None


class Port(DomainModel):
    """A declared mechanical, software, industrial-I/O, or modeled-safety port."""

    id: StableIdentifier
    direction: PortDirection
    type: StableIdentifier
    frame: StableIdentifier | None = None
    required: bool = False
    metadata: JsonObject = Field(default_factory=dict)


class ComponentPorts(DomainModel):
    mechanical: tuple[Port, ...]
    software: tuple[Port, ...]
    industrial_io: tuple[Port, ...]
    safety: tuple[Port, ...]


class CapabilityImplementation(DomainModel):
    contract: StableIdentifier
    version: SemanticVersion
    endpoint: StableIdentifier
    modes: tuple[ExecutionMode, ...] = ()
    limits: JsonObject = Field(default_factory=dict)

    @field_validator("modes")
    @classmethod
    def modes_are_unique(cls, values: tuple[ExecutionMode, ...]) -> tuple[ExecutionMode, ...]:
        _require_unique(tuple(values), "modes")
        return values


class Adapter(DomainModel):
    package: StableIdentifier
    entrypoint: NonEmptyString
    minimum_version: SemanticVersion | None = None
    fidelity: SimulationLevel | None = None


class ComponentAdapters(DomainModel):
    simulation: Adapter | None
    hardware: Adapter | None


class ComponentSupport(DomainModel):
    level: SupportLevel
    simulation_level: SimulationLevel
    owner: StableIdentifier | None = None


class ComponentType(DomainModel):
    """A reusable supported component product and its declared contracts."""

    schema_version: SemanticVersion
    component: ComponentIdentity
    assets: ComponentAssets
    variants: dict[StableIdentifier, tuple[str, ...]] = Field(default_factory=dict)
    frames: tuple[ComponentFrame, ...] = Field(min_length=1)
    ports: ComponentPorts
    config_schema: NonEmptyString | None = None
    capabilities: tuple[CapabilityImplementation, ...]
    adapters: ComponentAdapters
    fault_catalog: NonEmptyString | None = None
    support: ComponentSupport


class CellIdentity(DomainModel):
    id: UUID
    name: NonEmptyString
    description: str | None = None


class SceneReference(DomainModel):
    usd: NonEmptyString
    root_prim: NonEmptyString = "/World"


class ComponentInstance(DomainModel):
    """One configured component occurrence in a cell operational graph."""

    id: StableIdentifier
    alias: StableIdentifier
    component: ComponentTypeIdentifier
    version: SemanticVersion
    usd_prim: NonEmptyString
    variants: dict[StableIdentifier, str] = Field(default_factory=dict)
    adapter_mode: AdapterMode
    config: JsonObject
    calibration_refs: tuple[NonEmptyString, ...] = ()


class ConnectionEndpoint(DomainModel):
    component: StableIdentifier
    port: StableIdentifier


class Connection(DomainModel):
    """A typed link between two declared component ports."""

    id: StableIdentifier
    kind: ConnectionKind
    from_: ConnectionEndpoint = Field(alias="from")
    to: ConnectionEndpoint
    config: JsonObject = Field(default_factory=dict)


class TaskDefinition(DomainModel):
    id: StableIdentifier
    behavior_tree: NonEmptyString
    required_capabilities: tuple[StableIdentifier, ...] = ()


class RecipeBinding(DomainModel):
    schema_: NonEmptyString = Field(alias="schema")
    path: NonEmptyString


class CellProject(DomainModel):
    """Canonical operational graph paired with a referenced USD scene."""

    schema_version: SemanticVersion
    cell: CellIdentity
    scene: SceneReference
    components: tuple[ComponentInstance, ...] = Field(min_length=1)
    connections: tuple[Connection, ...]
    tasks: tuple[TaskDefinition, ...]
    recipes: tuple[RecipeBinding, ...]
    calibrations: tuple[NonEmptyString, ...] = ()
    scenarios: tuple[NonEmptyString, ...] = ()
    deployment_profiles: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def component_instance_ids_are_unique(self) -> Self:
        instance_ids = [component.id for component in self.components]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("component instance IDs must be unique within a cell")
        return self


class RecipeIdentity(DomainModel):
    id: StableIdentifier
    version: RecipeVersion
    name: NonEmptyString
    status: RecipeStatus


class RecipeCompatibility(DomainModel):
    cell_ids: tuple[UUID, ...]
    required_capabilities: tuple[StableIdentifier, ...]
    component_constraints: JsonObject = Field(default_factory=dict)


class TraceabilityPolicy(DomainModel):
    record_fields: tuple[StableIdentifier, ...]
    capture_before_image: bool = False
    capture_after_image: bool = False

    @field_validator("record_fields")
    @classmethod
    def record_fields_are_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique(values, "record_fields")


class Recipe(DomainModel):
    """An immutable-versioned process recipe document."""

    schema_version: SemanticVersion
    recipe: RecipeIdentity
    compatibility: RecipeCompatibility
    product: JsonObject = Field(default_factory=dict)
    parameters: JsonObject
    limits: JsonObject = Field(default_factory=dict)
    timeouts: dict[StableIdentifier, PositiveSeconds]
    retry_policy: JsonObject = Field(default_factory=dict)
    inspection: JsonObject = Field(default_factory=dict)
    traceability: TraceabilityPolicy
    approval: JsonObject = Field(default_factory=dict)


class ScenarioIdentity(DomainModel):
    id: StableIdentifier
    name: NonEmptyString
    seed: int
    timeout_seconds: PositiveSeconds | None = None


class InjectedFault(DomainModel):
    at: NonEmptyString
    target: StableIdentifier
    fault: StableIdentifier
    parameters: JsonObject = Field(default_factory=dict)


class ScenarioAssertions(DomainModel):
    final_status: NonEmptyString
    required_events: tuple[StableIdentifier, ...] = ()
    forbidden_events: tuple[StableIdentifier, ...] = ()
    max_cycle_seconds: PositiveSeconds | None = None


class Scenario(DomainModel):
    """A deterministic simulation scenario with optional fault injection."""

    schema_version: SemanticVersion
    scenario: ScenarioIdentity
    job: JsonObject
    initial_state: JsonObject
    randomization: JsonObject = Field(default_factory=dict)
    faults: tuple[InjectedFault, ...] = ()
    assertions: ScenarioAssertions


class DeploymentProfileIdentity(DomainModel):
    id: StableIdentifier
    name: NonEmptyString


class DeploymentPlatform(DomainModel):
    arch: CpuArchitecture
    os: NonEmptyString
    ros_distribution: StableIdentifier
    gpu: JsonObject = Field(default_factory=dict)


class DeploymentRuntime(DomainModel):
    native_packages: tuple[StableIdentifier, ...] = ()
    containers: tuple[NonEmptyString, ...] = ()


class DeploymentProfile(DomainModel):
    """A target platform and permitted-mode description for bundle resolution."""

    schema_version: SemanticVersion
    profile: DeploymentProfileIdentity
    platform: DeploymentPlatform
    runtime: DeploymentRuntime
    network: JsonObject
    modes: tuple[ExecutionMode, ...]
    external_prerequisites: tuple[NonEmptyString, ...] = ()

    @field_validator("modes")
    @classmethod
    def modes_are_unique(cls, values: tuple[ExecutionMode, ...]) -> tuple[ExecutionMode, ...]:
        _require_unique(tuple(values), "modes")
        return values


class BundleComponentReference(DomainModel):
    instance_id: StableIdentifier
    component: ComponentTypeIdentifier
    version: SemanticVersion


class BundleRecipeReference(DomainModel):
    id: StableIdentifier
    version: RecipeVersion


class BundleFile(DomainModel):
    path: NonEmptyString
    sha256: Sha256Digest
    size: NonNegativeSize


class BundleManifest(DomainModel):
    """Frozen references and content inventory for an immutable deployment bundle."""

    schema_version: SemanticVersion
    bundle_id: Sha256Digest
    source_revision: GitRevision
    cell_id: UUID
    target_profile: StableIdentifier
    components: tuple[BundleComponentReference, ...]
    recipes: tuple[BundleRecipeReference, ...]
    calibrations: tuple[NonEmptyString, ...] = ()
    files: tuple[BundleFile, ...]
