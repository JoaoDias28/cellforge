# Task 016 component browser and placement

## Goal
Cell Studio can discover and filter project-registry components, inspect their declared contracts
and execution-mode compatibility, and add or remove component instances as one undoable edit to the
canonical `cell.yaml` operational graph and canonical USD spatial scene.

## Scope
Included: pure registry browser queries; kind, capability, support-level, and simulation-level
filters; component detail and compatibility warnings; immutable instance-ID generation; editable
aliases; selected-variant validation and persistence; referenced USD prim authoring; connection-aware
removal with explicit cascade resolution; in-memory undo/redo; thin Kit callbacks; documentation;
deterministic non-Kit tests; and Isaac Sim 6 probes.

Excluded: connection creation or editing (Task 017), mechanical attachment/snap behavior, component
configuration forms, remote registry services, simulation control (Task 018), production
authorization, and safety enforcement.

## Current state
Tasks 005 (`c86e18f`) and 015 (`3bd9752`, completion `0e439d5`) are ancestors of clean local
`main`; Task 015 is merged through PRs 8 and 9. Task 005 provides deterministic exact-version
filesystem discovery and resolver policy. Task 015 provides pure project commands, exact in-memory
buffers, YAML/USD cross-reference validation, transactional save, and thin Kit callbacks.

The pre-edit baseline passes Ruff format/check, strict mypy (57 core and 7 Studio sources), 232
pytest tests, canonical example validation, 20 Studio tests, 10 project/scene tests, and both
non-Kit probes. GNU Make and Isaac Sim 6 are not discoverable on this Windows host. Pytest requires
an explicit writable `--basetemp` because the host user Temp directory is inaccessible.

## Design
The domain resolver exposes its existing component/mode compatibility rule as a public pure
function so the browser does not copy production-support validation. A Kit-free component service
loads the project-local filesystem registry, maps manifests into deterministic browser/detail
records, and applies optional conjunctive filters.

Placement validates the exact component version, alias, variant-set names and selections, and
configuration before changing either buffer. It generates a UUID-derived stable instance ID,
authors one `ComponentInstance` in `cell.yaml`, and adds one USD Xform below the configured scene
root with the same `cellforge:instanceId` and a relative reference to the package visual asset.
The UUID generator is injectable for deterministic tests. The resulting pair is cross-reference
validated by the existing save service before filesystem replacement.

Removal rejects an unknown instance and refuses a connected instance unless the caller explicitly
selects connection removal. An accepted removal deletes the YAML component, optionally deletes its
incident connections, and removes the exact linked USD prim subtree. It never infers rewiring.

`StudioApplication` owns undo/redo stacks of complete in-memory source pairs. Successful placement
and removal push one logical edit; UI callbacks invoke commands and render returned state without
parsing YAML, authoring USD, or implementing compatibility rules. Save remains the only operation
that replaces project files.

No schema migration or new dependency is required. Modeled safety connections remain descriptive;
their presence only triggers the same explicit connection-removal requirement as every other edge.

## Work sequence
1. Publish the existing resolver compatibility rule and add deterministic browser/detail queries;
   acceptance: all four required filters and unsupported-production warnings have focused tests.
2. Implement paired YAML/USD placement and connection-aware removal; acceptance: linked IDs,
   selected variants, invalid inputs, missing packages, and explicit cascade behavior are tested.
3. Add application undo/redo and thin Kit browser callbacks/panel; acceptance: structural callback
   tests and headless state tests prove no UI-owned validation or direct file writes.
4. Add Task 016 probes and documentation; acceptance: deterministic non-Kit probe succeeds and the
   Isaac command is documented exactly.
5. Run all scoped and regression checks, inspect the diff, commit, publish a ready PR, wait for
   required checks, merge only when green/mergeable, and synchronize local `main`.

## Validation
- `make lint`, `make test`, and `make validate-examples`, or their exact Makefile command bodies if
  GNU Make remains unavailable.
- `make kit-extension-check`, `make studio-project-scene-check`, and the Task 016 headless target.
- Focused component-service tests for filtering, detail compatibility, success, invalid alias and
  variant, missing component, connection-blocked removal, explicit cascade, and USD mutation failure.
- Application tests for placement, removal, save boundary, undo, redo, and backend failure.
- `isaac-sim.bat --no-window --ext-folder <repo>\src\kit --enable cellforge.studio --exec
  <repo>\scripts\verify_kit_component_placement.py`.
- `git status --short`, `git diff`, `git diff --check`, staged checks, post-commit verification, PR
  checks, mergeability, and synchronized default-branch verification.

## Risks and rollback
The fallback USDA editor intentionally supports the Task 015 text-stage subset and fails closed on
an unlocatable scene root or malformed brace structure; Isaac Sim/OpenUSD performs the integration
check for composed references. Whole-buffer undo makes paired-artifact rollback deterministic.
Aliases never determine persistence identity. Removing a connected component can invalidate
intent, so cascading requires an explicit command parameter. Reverting the Task 016 commit removes
the feature without migrating project schemas or existing projects.

## Progress
- [x] 2026-08-10 — Read required specifications, architecture/ADR documents, prerequisite plans,
  implementations, and Git history; confirm clean prerequisite ancestry.
- [x] 2026-08-10 — Establish the green pre-edit deterministic baseline and create the task branch.
- [x] 2026-08-10 — Implement pure browser, detail, placement, and removal services with tests.
- [x] 2026-08-10 — Wire undo/redo and thin Kit callbacks, probes, and documentation.
- [ ] 2026-08-10 — Complete checks, commit, ready PR, CI, merge, and local-main synchronization.

## Decisions
- 2026-08-10 — Reuse the resolver's execution-mode rule through a public function so browser
  warnings and compiler resolution cannot drift.
- 2026-08-10 — Persist generated IDs independently of aliases and USD prim names; alias edits never
  change the operational or spatial linkage key.
- 2026-08-10 — Treat placement/removal as in-memory paired source transformations; Task 015's
  explicit transactional save remains the only filesystem commit boundary.
- 2026-08-10 — Require explicit cascade removal for every incident connection, including modeled
  safety dependencies; this models graph editing and does not implement a safety function.

## Results
Implemented deterministic project-registry browsing with all four required filters, detailed
manifest/variant/capability metadata, shared resolver compatibility policy, and explicit
production warnings. Placement creates a validated UUID-derived immutable instance ID, persists
the editable alias and exact selected variants in `cell.yaml`, and authors a referenced USD Xform
with the same ID. Removal refuses incident connections unless the engineer explicitly requests
their deletion. Complete in-memory YAML/USD pairs support undo/redo and continue to use Task 015's
validated journaled save boundary.

The final pre-commit run passes Ruff formatting/lint, strict mypy (57 core and 9 Studio sources),
240 repository tests, validation of 5 canonical schemas/6 component config schemas/19 example YAML
documents, 28 Studio tests, 10 Task 015 regression tests, 7 focused Task 016 tests, extension
manifest verification, and both deterministic Studio probes. The documented Isaac Sim 6 command
is unavailable because `isaac-sim.bat` is not installed/on PATH; no OpenUSD/Kit integration result
is claimed. GNU Make is unavailable, so the exact underlying Makefile commands were executed.
