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

## Public API

Use `load_document(path, ModelType)` to load YAML or JSON into `ComponentType`, `CellProject`,
`Recipe`, `Scenario`, or `DeploymentProfile`. Loading failures raise `SourceLoadError`, whose
`findings` contain stable `ValidationFinding` codes and source-addressable paths. Bundle inventories
use `BundleManifest` and lowercase SHA-256 digests.

Use `to_canonical_json(model)` whenever serialized bytes participate in comparison or hashing. It
emits schema aliases and recursively sorts object keys.

No dependency in this package may import or require a production ROS graph, simulation runtime,
web service, external network connection, or vendor SDK.
