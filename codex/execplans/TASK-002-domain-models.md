# Task 002 domain models and schema loader

## Goal
Provide a pure-Python, typed domain boundary that can load CellForge YAML and JSON documents,
report source-aware validation errors, and serialize public models deterministically. This gives
Task 003 a stable model layer for schema and example validation without introducing runtime,
simulation, web, or vendor dependencies.

## Scope
Included: Pydantic models corresponding to the supplied component, cell, recipe, scenario, and
deployment-profile schemas; a content-addressed bundle-manifest model; stable identifier and
Semantic Version validation; structured validation findings; YAML/JSON loading; canonical JSON
serialization; public exports; package documentation; and focused unit tests.

Excluded: JSON Schema validation and example-validation wiring (Task 003), cross-document port or
capability resolution, USD validation, bundle construction/hashing, ROS interfaces, Isaac Sim,
FastAPI, vendor SDKs, production-control behavior, and functional-safety enforcement.

## Current state
Task 001 created the `cellforge_domain` package boundary, Draft 2020-12 schemas, reference YAML
documents, Python quality configuration, and commit `2d940e7`. The package currently exposes no
models and has no runtime dependency. Baseline direct checks pass: Ruff format, Ruff lint, mypy,
and 3 pytest tests. GNU Make is unavailable on this Windows host; the `validate-examples` Makefile
target is intentionally unwired and exits 2 pending Task 003.

The supplied examples use lowercase URL-safe IDs for component types, instances, connections,
recipes, scenarios, and profiles; cell identity is a UUID; component and schema versions use
Semantic Versioning. Existing schemas forbid unknown fields in the central component and cell
structures, so domain models will do the same consistently.

## Design
All public models derive from one Pydantic base configured to forbid unknown fields, validate
assignments, accept aliases, and strip surrounding string whitespace. Shared annotated scalar
types validate stable identifiers, strict Semantic Version 2.0 strings, and lowercase SHA-256
digests. Models use enums for closed schema vocabularies and typed JSON-value mappings for fields
whose detailed schemas belong to later tasks.

`CellProject` performs the Task 002 semantic check for duplicate component-instance IDs. Other
cross-document and graph-link checks remain outside this task. Connection input uses the YAML key
`from` through a Python-safe field alias.

Loading selects YAML or JSON from the source suffix, requires a mapping at the document root, and
validates directly into the requested Pydantic model. A `SourceLoadError` carries the source path,
a stable error code, and structured `ValidationFinding` entries. Its displayed message is
sanitized and suppresses parser/filesystem exception details and tracebacks; the original cause is
retained only as non-serialized diagnostic state.

Canonical serialization uses Pydantic JSON-mode dumping followed by sorted-key, compact JSON
encoding. This makes output independent of input mapping insertion order. Bundle manifests model
content digests and frozen references but do not calculate a bundle hash; that belongs to Task 006.

Pydantic 2 is the only new dependency distribution. It is MIT licensed, actively maintained, and
required explicitly by Task 002 for validation and serialization. The removal path is to replace
`BaseModel`, annotated validators, and model validators with an equivalent typed validation layer
while preserving this package's public data contracts. PyYAML was already a locked workspace
development dependency from Task 001 and is now also declared by the domain package because YAML
loading is required public behavior.

Modeled safety ports and connections are descriptive data only. The models do not implement,
authorize, or claim functional-safety behavior.

## Work sequence
1. Add and lock the documented Pydantic and PyYAML runtime dependencies; acceptance: the locked
   workspace sync succeeds.
2. Add shared scalar validation, model enums, document models, findings, loading errors, and
   canonical serialization; acceptance: mypy and Ruff pass for the package.
3. Export and document the public API and dependency boundary; acceptance: the package imports
   without ROS, Isaac Sim, FastAPI, or vendor modules.
4. Add tests for every supplied document family, valid YAML/JSON loading, invalid IDs and semantic
   versions, missing fields, duplicate instance IDs, source-aware parse/read/validation failures,
   safe user messages, and deterministic serialization; acceptance: focused pytest passes.
5. Run all Task 002 and repository checks, inspect and stage only the scoped diff, update this plan's
   results, and create the required task commit.

## Validation
Run, with a workspace-local UV cache where needed:

```text
make lint
make test
make validate-examples
uv sync --locked --all-packages
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy src/python/cellforge_domain/src src/python/cellforge_domain/tests tests
uv run --frozen pytest
git diff --check
```

Expected evidence: all direct formatting, lint, typing, and pytest checks pass. Make commands may be
reported unavailable if GNU Make remains absent. `validate-examples` remains intentionally unwired
until Task 003 and must not be reported as passing.

## Risks and rollback
Over-validating identifiers could reject committed reference examples; tests load all document
families to catch that. Under-typed extension mappings could hide later schema errors; Task 003
will apply Draft 2020-12 schemas, while Task 002 forbids unknown structural fields. Aliases can
change serialized field names; canonical serialization always requests schema aliases and tests
the `from` connection key. Rollback is the single Task 002 commit; no data migration or external
state change is introduced.

## Progress
- [x] 2026-08-06 - Verified clean `main`, exact Task 001 prerequisite commit, required documents,
  supplied schemas/examples, and baseline checks.
- [x] 2026-08-06 - Added model and loader implementation with locked Pydantic 2.13.4 and PyYAML
  6.0.3 dependencies.
- [x] 2026-08-06 - Added valid/invalid unit coverage and deterministic serialization checks; the
  focused suite passes 32 tests with Ruff and strict mypy clean.
- [x] 2026-08-06 - Completed acceptance checks and full review; this plan is included in the
  task-scoped commit.

## Decisions
- 2026-08-06 - Treat committed Task 001 schemas and examples as the compatibility baseline; defer
  Draft 2020-12 schema execution to Task 003.
- 2026-08-06 - Keep modeled safety data descriptive and outside any enforcement path.
- 2026-08-06 - Represent bundle content addresses as lowercase 64-character SHA-256 hex digests;
  defer hash computation and manifest assembly to Task 006.
- 2026-08-06 - Use aliases for schema keys that are Python-reserved or shadow framework attributes
  (`from` and `schema`) so serialized documents remain compatible and model code remains safe.

## Results
Implemented strict Pydantic models for every supplied document family and bundle manifests, shared
identifier/version/digest types, source-aware YAML/JSON loading, sanitized structured failures,
canonical JSON output, public exports, and dependency/boundary documentation. Tests cover all 11
committed reference documents plus JSON loading, invalid IDs and versions, missing fields,
duplicate instances, read/parse/root/format failures, deterministic nested mappings and aliases,
bundle digests, and forbidden imports.

Direct acceptance checks pass: locked workspace sync; Ruff format and lint; strict mypy; and 34
repository tests. The focused domain suite contains 32 passing tests. `make lint`, `make test`, and
`make validate-examples` are unavailable because GNU Make is not installed on this Windows host.
The Makefile's `validate-examples` recipe remains intentionally unwired and exits 2 pending Task
003; it is not reported as passing. ROS and Isaac Sim checks are not applicable because this task
adds pure domain code only.

No schemas, examples, runtime control, or safety enforcement were changed. Task 003 was not
started.
