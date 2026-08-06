# Task 006 cell compiler and bundle manifest

## Goal
Compile a valid CellForge project into a deterministic, content-addressed deployment plan and
manifest without building binaries, containers, installing a bundle, or weakening production and
functional-safety boundaries.

## Scope
Included: project/schema preflight, exact component and capability resolution, basic USD instance
and behavior-tree reference checks, exact target-profile selection, recipe compatibility and
production approval checks, selected adapter/runtime package resolution, frozen recipe/task
references, source-file inventory, canonical manifest JSON, SHA-256 bundle ID calculation, a
production evidence-policy gate that fails closed, CLI access, documentation, and deterministic
tests.

Excluded: binary/container assembly, signing/publication, bundle installation or activation,
calibration signature verification, semantic BehaviorTree.CPP validation, Isaac Sim validation,
runtime/ROS interfaces, functional-safety implementation, and all Task 007 work.

## Current state
Tasks 004 and 005 are present at `04912dc` and `c86e18f`. The starting branch was
`task/005-component-registry-resolver`; the clean Task 006 branch is
`task/006-cell-compiler`. `cellforge_domain` already owns strict models, canonical JSON,
schema loading, filesystem component discovery, and exact component/port/capability/mode
resolution. `cellforge_cli` validates and inspects projects but intentionally stops before the
compiler stages. The pen example is simulation-only and its recipe status is `TESTED`.

The untouched baseline passed the Makefile-equivalent commands: Ruff format, Ruff lint, strict
mypy, 61 pytest tests, and example validation. GNU Make itself is unavailable on this Windows
host. The default uv cache was sandbox-inaccessible, so checks use a temporary workspace-local uv
cache.

## Design
Add `cellforge_bundle` as an application package that depends on, but is never imported by,
`cellforge_domain`. The compiler returns a structured report with deterministic stage findings and
an optional manifest. Expected input problems are data, not exceptions. Filesystem reads are
restricted to normalized project-relative paths; absolute paths and traversal outside the project
fail validation.

Compilation proceeds in architecture order: schema/domain validation; exact registry and
connection linking; textual USD prim/reference validation sufficient for current USDA sources;
exact capability resolution; behavior-tree XML well-formedness and referenced-tree checks; recipe
cell/capability compatibility and production approval; exact target profile/mode selection;
adapter and package selection; production evidence policy; then immutable manifest construction.
Stages that lack valid prerequisites report a stable blocked/error finding rather than silently
succeeding.

The manifest freezes canonical identifiers plus hashes for recipes, behavior trees, configuration,
component manifests/assets/config schemas, scene, calibrations, and selected target profile. Lists
are sorted by stable keys and runtime packages are deduplicated and sorted. The bundle ID is the
lowercase SHA-256 digest of canonical UTF-8 JSON for the complete manifest payload with
`bundle_id` omitted. `manifest.json` is serialization output and is not included in its own file
inventory.

Component adapters are chosen exactly by execution mode: simulation uses the simulation adapter;
commissioning and production use hardware. `target_selected` is resolved, never preserved as an
ambiguous runtime choice. Production requires `APPROVED` recipes and
`production_qualified` components through existing resolver rules. The evidence checker is an
explicit placeholder: when production evidence is required it emits an error and no manifest,
because no evidence verification service exists yet. Modeled safety connections remain read-only
metadata; the compiler neither creates nor claims safety enforcement.

Public model additions remain backward compatible by giving new manifest fields defaults where an
older caller could have constructed the Task 002-era model. No existing JSON schema is changed.

## Work sequence
1. Extend bundle-domain data contracts with adapter/task/target/evidence fields and canonical
   hash-input serialization; verify focused model tests.
2. Add the `cellforge_bundle` package and compilation pipeline with stable findings and safe path
   handling; verify focused compiler tests.
3. Add the CLI build command and documentation; verify focused CLI tests.
4. Add deterministic-build, changed-recipe, production-rejection, invalid-input, and failure-path
   tests, then run the full repository checks.
5. Inspect diffs, update this plan with results, stage only Task 006, commit, and verify a clean
   working tree and the exact commit in Git history.

## Validation
Run:

```text
make lint
make test
make validate-examples
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy src/python/cellforge_domain/src src/python/cellforge_domain/tests src/python/cellforge_bundle/src src/python/cellforge_bundle/tests src/python/cellforge_cli/src src/python/cellforge_cli/tests tests
uv run --frozen pytest
uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving
```

Expected evidence: unchanged builds have byte-identical canonical manifest JSON and bundle IDs;
recipe content changes alter the file hash and bundle ID; the simulation-only pen example is
rejected for production; malformed documents, escaping references, missing behavior trees, invalid
targets, and output failures return stable findings/nonzero CLI results without tracebacks.

ROS and Isaac checks are not applicable because Task 006 adds no ROS or Kit code.

## Risks and rollback
The main compatibility risk is expanding the public manifest contract. Defaults protect older
model construction, while compiler output always supplies the new frozen fields. Textual USDA
checking is deliberately conservative and documented; full OpenUSD composition belongs to a later
spatial integration task. The compiler can be rolled back as one task commit; it creates no runtime
state and installs nothing.

## Progress
- [x] 2026-08-06 19:03 +01:00 - repository state, required documents, Tasks 004/005 history, and
  untouched baseline verified.
- [x] 2026-08-06 19:25 +01:00 - bundle contracts and compiler implemented; nine focused tests pass.
- [x] 2026-08-06 19:25 +01:00 - CLI/documentation integrated and verified.
- [x] 2026-08-06 19:25 +01:00 - full direct Makefile-equivalent checks and acceptance scenarios pass.
- [ ] 2026-08-06 19:03 +01:00 - Task 006 committed and final repository state verified.

## Decisions
- 2026-08-06 19:03 +01:00 - Keep filesystem/compiler orchestration in `cellforge_bundle` so the
  domain layer remains independent of CLI, ROS, Isaac Sim, web services, and vendor software.
- 2026-08-06 19:03 +01:00 - Hash canonical manifest content without `bundle_id` to avoid a
  self-referential digest while retaining every frozen input hash in the content address.
- 2026-08-06 19:03 +01:00 - Fail every production compile at the evidence stage until a real
  evidence verifier exists; an unchecked caller assertion cannot authorize production.
- 2026-08-06 19:25 +01:00 - Freeze exact resolved capability provider/version/endpoint mappings in
  the manifest as well as exposing the complete resolution report.

## Results
Implemented `cellforge_bundle`, backward-compatible expanded bundle contracts, and `cellforge build`.
The compiler now returns deterministic stage results/findings, freezes exact components,
capabilities, adapters, runtime packages, recipes, behavior trees, schemas, component runtime files,
scene, target profile, and calibrations, and emits a canonical content-addressed manifest.

All 70 tests, Ruff formatting/lint, strict mypy over 29 source files, and validation of 5 canonical
schemas, 6 component config schemas, and 11 example YAML documents pass. The literal `make lint`,
`make test`, and `make validate-examples` commands are unavailable because GNU Make is not installed
on this Windows host; their exact recipes pass when invoked directly with uv. ROS and Isaac checks
are not applicable. Commit and final clean-tree verification remain.
