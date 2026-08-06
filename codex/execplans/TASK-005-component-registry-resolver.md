# Task 005 component registry and capability resolver

## Goal
Provide a pure-Python filesystem registry and deterministic resolver that loads versioned component
packages, links a cell's declared ports, resolves task capability providers, applies execution-mode
compatibility policy, and reports the resulting dependency graph with stable validation findings.

## Scope
Included: recursive `component.yaml` discovery; optional Draft 2020-12 manifest validation through
the existing schema registry; duplicate component-version and requested-version conflict detection;
cell instance lookup; declared connection endpoint, direction, and type validation; exact mechanical
port compatibility; versioned capability provider resolution; support-level, adapter, and execution-
mode checks; deterministic report models; public documentation; and unit/contract tests.

Excluded: Task 006 compilation, target deployment-profile selection, bundle manifests or hashing,
USD/frame validation, adapter implementation, ROS/Isaac Sim integration, remote registry services,
recipe approval, production authorization, and functional-safety enforcement.

## Current state
Tasks 002 and 003 are present as commits `dede63e` and `ff6fe84`. Task 004 is also present as
`04912dc`, and the clean checkout has been branched to `task/005-component-registry-resolver`.
`cellforge_domain` already supplies strict component/cell models, source-aware loading, structured
findings, schema validation, and canonical JSON serialization. The reference cell contains six
component packages, ten uniquely provided required capabilities, one mechanical link, and two
modeled-safety status links.

Baseline direct checks pass: locked UV sync, Ruff formatting and lint, strict mypy, 49 pytest tests,
and validation of 5 canonical schemas, 6 component configuration schemas, and 11 example YAML
documents. GNU Make is unavailable on this Windows host, so its exact underlying commands are used.

## Design
`FilesystemComponentRegistry` scans a caller-supplied root in sorted relative-path order. Valid
packages are indexed by exact `(component type ID, semantic version)` keys. Multiple versions of a
type are allowed; duplicate exact keys produce `registry.duplicate-component-version`. A cell
request for an absent type produces `resolver.component-missing`, while a type found only at other
versions produces `resolver.component-version-conflict`. Invalid manifests remain findings and are
not inserted into the usable index.

The resolver accepts an already validated `CellProject`, registry, and `ExecutionMode`. It gathers
all errors where possible. Each connection endpoint must name an instantiated component and a port
declared in the collection matching the connection kind. Source ports must be output/bidirectional,
targets input/bidirectional, and port types must match. Mechanical mismatches have their own stable
code because any future adapter-plate contract must be explicit rather than inferred from free-form
configuration.

Each task capability requirement resolves by contract ID to an implementation exposed by an
execution-compatible component. The selected implementation records its exact semantic version,
instance, and endpoint. No implicit provider choice is made when providers are ambiguous; differing
versions report a version conflict and equal-version duplicates report provider ambiguity. Empty or
mode-incompatible provider sets fail closed with stable codes.

Simulation requires a non-metadata, non-deprecated component with a simulation adapter and a cell
adapter mode other than `hardware`. Commissioning requires bench-tested or production-qualified
support plus a hardware adapter and non-simulation instance selection. Production requires
production-qualified support plus a hardware adapter and non-simulation selection. These checks
only determine engineering/runtime compatibility; they do not approve a recipe, command hardware,
or implement a safety function.

The report contains sorted resolved instances, port links, capability bindings, findings, and a
dependency graph. Graph nodes represent component instances and tasks; connection and capability
edges identify their source, target, contract/version where applicable. Sorting by stable IDs makes
output independent of filesystem enumeration and input sequence order.

No schema migration or new production dependency is required.

## Work sequence
1. Add public registry/resolution report models and filesystem discovery; acceptance: reference
   manifests load in deterministic order and duplicate/invalid packages return stable findings.
2. Implement instance, port, capability, support, adapter, and mode resolution; acceptance: the pen
   cell resolves in simulation and focused negative cases return the documented codes.
3. Add deterministic dependency-graph reporting, public exports, and package documentation;
   acceptance: reordered equivalent input produces identical canonical report JSON.
4. Add success, invalid-input, conflict, missing dependency, incompatible mechanical port,
   unsupported mode/support, ambiguity, and filesystem failure tests.
5. Run Task 005 acceptance and repository regression checks, review/stage only scoped changes,
   update this plan's results, commit, and verify a clean working tree.

## Validation
Run:

```text
make lint
make test
make validate-examples
uv sync --locked --all-packages
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy src/python/cellforge_domain/src src/python/cellforge_domain/tests src/python/cellforge_cli/src src/python/cellforge_cli/tests tests
uv run --frozen pytest
uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving
git diff --check
```

Expected evidence: the reference pen cell resolves in simulation with no findings; all stable-code
negative tests pass; repeated/reordered resolution serializes identically; the full existing suite
and example validation remain green. Make commands will be reported unavailable if GNU Make remains
absent. ROS and Isaac Sim checks are not applicable to this pure-domain task.

## Risks and rollback
Overly strict port policy could reject existing manifests, so exact checks apply only to explicitly
declared cell connections and are tested against the reference cell. Automatic capability provider
selection could bind the wrong physical device, so ambiguity fails closed. Execution-level policy
could be mistaken for safety or production approval; documentation and naming keep it explicitly to
compatibility resolution. Reverting the single Task 005 commit removes the registry/resolver and
tests without migrating schemas or data.

## Progress
- [x] 2026-08-06 - Verified clean repository, dedicated branch, Task 002/003 prerequisite history,
  required documentation, reference manifests, and passing direct baseline checks.
- [x] 2026-08-06 - Implemented registry discovery and conflict reporting.
- [x] 2026-08-06 - Implemented deterministic connection, capability, and mode resolution.
- [x] 2026-08-06 - Completed focused tests, documentation, and regression checks.

## Decisions
- 2026-08-06 - Allow multiple versions of one component type in the registry; only duplicate exact
  ID/version keys conflict, while cell references continue to require an exact version.
- 2026-08-06 - Fail on ambiguous capability providers instead of silently choosing equipment.
- 2026-08-06 - Treat modeled-safety ports exactly as descriptive graph dependencies; do not turn
  them into executable or safety-rated enforcement.
- 2026-08-06 - Keep Task 005 in `cellforge_domain` because discovery and resolution are pure,
  caller-rooted filesystem/domain operations with no platform service or adapter dependencies.

## Results
Implemented deterministic recursive component discovery with optional schema validation, exact
component ID/version indexing, distinct-version support, invalid-manifest findings, duplicate exact
version detection, and a sorted serializable registry inventory.

Resolution now links declared connection endpoints, checks direction and type compatibility,
resolves exact versioned capability providers, applies support/adapter/execution-mode policy, and
reports sorted component/task dependency nodes and connection/capability edges. Modeled-safety
connections remain descriptive data and do not implement or claim safety enforcement.

Focused coverage passes 12 success and failure-path tests, including deterministic reordered input,
registry invalid/duplicate input, missing/version-conflicting components, port failures, unsupported
modes, missing capabilities, provider ambiguity, and capability-version conflicts. The full suite
passes 61 tests; Ruff formatting/lint and strict mypy pass; all 5 canonical schemas, 6 component
configuration schemas, and 11 example YAML documents validate. GNU Make is unavailable, while the
exact direct Makefile commands pass. ROS, Isaac Sim, hardware, production authorization, and
functional-safety integration checks are not applicable to this pure-domain task.
