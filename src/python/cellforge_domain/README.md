# cellforge-domain

Pure Python Pydantic models and source-aware YAML/JSON loading for CellForge component types,
cells, recipes, scenarios, deployment profiles, validation findings, and bundle manifests.

This package remains independent of ROS, Isaac Sim, FastAPI, and vendor SDKs. Modeled safety ports
and connections describe dependencies for validation and review; they never implement functional
safety or authorize physical operation.

## Runtime dependencies

- `pydantic` 2.x (MIT): actively maintained validation and deterministic data-model foundation
  required by Task 002. Removal requires replacing the public model, annotated-validator, and
  model-validator contracts with an equivalent typed validation layer.
- `PyYAML` 6.x (MIT): maintained YAML parser used only for source document loading. Removal can use
  another safe YAML 1.1-compatible parser behind `load_document` without changing public models.
- `jsonschema` 4.x (MIT): actively maintained Python implementation used for standards-conformant
  JSON Schema Draft 2020-12 meta-schema and instance validation. Removal requires an equivalent
  Draft 2020-12 validator behind `SchemaRegistry`; schemas and public findings need not change.

## Public API

Use `load_document(path, ModelType)` to load YAML or JSON into `ComponentType`, `CellProject`,
`Recipe`, `Scenario`, or `DeploymentProfile`. Loading failures raise `SourceLoadError`, whose
`findings` contain stable `ValidationFinding` codes and source-addressable paths. Bundle inventories
use `BundleManifest` and lowercase SHA-256 digests.

Create `SchemaRegistry.from_directory(schema_path)` and pass it to `load_document` for Draft 2020-12
validation before Pydantic construction. The document kind is inferred from the model, or callers
may pass a `SchemaDocumentKind` explicitly. Run the repository
example contract with:

```console
python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving
```

Failure lines contain the source file plus JSON Pointer, the violated schema rule/code, and a human
message. Cross-file checks resolve recipe schemas, recipe documents, cell compatibility, and
deployment profiles relative to the referencing `cell.yaml`.

Use `to_canonical_json(model)` whenever serialized bytes participate in comparison or hashing. It
emits schema aliases and recursively sorts object keys.

Load a local component registry and resolve a validated cell with:

```python
registry = FilesystemComponentRegistry.from_directory(
    component_root,
    schema_registry=schema_registry,
)
report = resolve_cell(cell, registry, ExecutionMode.SIMULATION)
```

The registry accepts distinct semantic versions and rejects duplicate component ID/version keys.
Resolution requires exact component versions, links declared cell connection endpoints, validates
port direction and type compatibility, resolves each task capability to one exact versioned
provider, and checks support level plus adapter availability for the requested execution mode.
`ResolutionReport` is sorted for deterministic canonical serialization and includes a component/task
dependency graph and stable findings. Important resolver codes include
`resolver.component-missing`, `resolver.component-version-conflict`, `resolver.port-missing`,
`resolver.mechanical-port-incompatible`, `resolver.capability-missing`, and
`resolver.support-level-unsupported`.

Modeled safety connections are resolved only as descriptive dependencies. Neither registry loading
nor resolution approves recipes, authorizes physical operation, or implements a safety function.

No dependency in this package may import or require a production ROS graph, simulation runtime,
web service, external network connection, or vendor SDK.
