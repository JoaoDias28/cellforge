# Task 028 — Studio spatial configuration and calibration

## Goal
Allow an engineer to spatially configure a placed component, edit its schema-backed
configuration and variants, and create/import immutable calibrations without manually editing
`cell.yaml` or USDA. Every accepted edit must preserve the paired canonical artifacts.

## Scope
Included: pure paired-buffer commands for transforms, component configuration/variants, and
calibration creation/import/binding; validation of finite transforms, component configuration,
variants, mounts, payload/reach declarations, calibration integrity/expiry/binding, and the
existing YAML/USD instance identity pair; Studio controls/presentation for those commands; and
deterministic plus Kit lifecycle/probe coverage.

Excluded: arbitrary CAD editing, physics collision computation, safety enforcement or override,
recipe/task authoring (Task 029), deployment/evidence UI (Task 030), hardware calibration, and
claims that a non-Kit test is an Isaac Sim visual-interaction qualification.

## Current state
Tasks 015–017 already provide in-memory paired YAML/USD buffers, transactional Save, stable
component IDs, placement/removal, typed connections, mechanical snap preview/application, and
whole-pair undo/redo. Component manifests provide config-schema paths, variants, frames, ports,
and assets; `calibration.schema.json` describes immutable calibration files. Task 027 commits are
present, but its required Isaac Sim 6 acceptance and publication are unresolved. The current
Windows environment also has no usable Isaac Sim 6 runner.

The initial focused Studio baseline could not execute because pytest's default user temp directory
and pre-existing `.pytest_cache` are owned by another Windows identity; this is an environment
failure before Task 028 changes, not a test assertion failure.

## Design
`SpatialConfigurationService` will be a pure application service. It parses the candidate
`cell.yaml`, resolves the project-local component registry and configuration schema, and returns
either a complete changed `ProjectContents` pair or structured findings with no mutation. Transform
edits author a finite matrix on the component USD Xform and preserve its immutable instance
metadata. Configuration/variant edits update only the matching operational instance after
schema/manifest validation. Calibrations are copied/created under `calibration/`, validated against
the canonical schema, must bind to the selected immutable component ID, have an integrity digest of
their canonical payload, and may not be expired. The calibration path and reference are updated in
the same candidate graph.

The service reuses the existing scene/link validator as the final paired-source gate. Mount validity
comes from existing mechanical connection validation; payload/reach are declarative component
limits, so absent declarations do not invent values. A Kit view stays a thin command/presentation
layer; it never writes files directly. Application undo/redo retains complete buffer pairs, and
Task 015 remains the sole persistent transaction boundary. Modeled safety remains read-only
engineering metadata and no command implements a safety function.

## Work sequence
1. Add a documented plan and a pure spatial/configuration/calibration service; acceptance: valid
   candidates produce linked source buffers while invalid candidates return findings only.
2. Integrate commands and complete-pair undo/redo in the Studio application and Kit UI; acceptance:
   selection and edits are visible without direct filesystem writes.
3. Add deterministic service/application/probe tests for transforms, invalid configurations,
   variants, calibration integrity/expiry/binding, save/reopen, undo/redo, and failure paths.
4. Run focused and repository checks where the environment permits; run the documented Isaac Sim
   6 probe only if the supported runner is installed.
5. Inspect, commit, and attempt publication. Do not merge or claim qualification while the inherited
   Task 027 Isaac Sim 6 prerequisite remains unavailable.

## Validation
- `uv run --frozen pytest --basetemp <writable temporary root>` for focused Studio tests.
- `uv run --frozen ruff format --check .`, `ruff check .`, and strict mypy for changed Studio files.
- `make lint`, `make test`, and `make validate-examples` or their exact command bodies where `make`
  is unavailable.
- A deterministic Task 028 Studio probe and the documented Isaac Sim 6 headless probe when
  available.
- `git diff --check`, staged diff checks, post-commit status/log verification, and publication
  checks if the prerequisite branch can be published.

## Risks and rollback
USDA text editing is intentionally constrained to editable Xform prims and must fail closed for
missing/singular/non-finite transforms. Calibration copying changes the project filesystem only
after the in-memory candidate has validated; save remains transactional for canonical sources.
Schema validation must use the project-selected schema directory to preserve backwards-compatible
project schemas. Reverting the Task 028 commit removes the new editor without a schema migration.

## Progress
- [x] 2026-08-13 — Read task, system specification, Studio/architecture/ADR documentation,
  calibration schema, prerequisite plans/implementation, Git state, and Task 027 history.
- [x] 2026-08-13 — Created the Task 028 branch and recorded the pre-change test-environment
  permission failure.
- [x] 2026-08-13 — Implement pure transforms, configuration/variant edits, immutable calibration
  creation/import/binding, paired validation, and staged artifact persistence.
- [x] 2026-08-13 — Integrate undoable commands and thin Studio controls; add deterministic,
  application, lifecycle-contract, and OpenUSD probe coverage.
- [x] 2026-08-13 — Committed the scoped implementation as `bd6ae66` after staged diff checks.
- [ ] 2026-08-13 — Publication and merge blocked: the supported Isaac Sim 6 acceptance probe timed
  out without output, and prerequisite Task 027 remains unqualified/unpublished for the same
  platform reason. Do not open a PR or begin Task 029.

## Decisions
- 2026-08-13 — Use a pure application service and existing paired-source validator rather than
  making Kit widgets edit YAML/USD directly.
- 2026-08-13 — Treat calibration artifacts as immutable validated files bound to one component;
  expired or digest-mismatched artifacts fail closed.
- 2026-08-13 — Do not infer payload/reach/collision values from visuals; validate only explicit
  declared engineering limits and report the absence of unsupported runtime geometry checks.
- 2026-08-13 — Extend the existing paired save journal to include newly created immutable
  calibration files. A rollback removes newly created files while restoring replaced canonical
  sources; reopening loads declared calibration bytes into the working state.

## Results
Implemented viewport-neutral selection data, finite non-singular Xform authoring, schema-driven
component configuration, manifest-backed variant edits, immutable calibration creation/import with
schema/digest/expiry/binding checks, paired artifact staging, transactional persistence/recovery,
and complete-pair undo/redo through the Studio application. The Kit UI delegates these commands and
the deterministic Task 028 probe passes.

Focused Studio checks pass: strict mypy for changed files and 43 Studio regressions; the new
deterministic probe passes. Repository example validation passes. The full Python suite produced
362 passed and 1 skipped, with one pre-existing unrelated failure asserting the absent
`CurrentState` text in `cellforge_motion/src/mtc_task_builder.cpp`. The repository-wide lint/type
run also reports pre-existing Task 027 formatting/lint issues in ROS sources and a missing
`sensor_msgs.msg` type stub. Isaac Sim 6.0.1-rc.7 is installed, but its required Task 028 headless
Kit/OpenUSD command timed out after 184 seconds without output; its process was stopped. This is a
failed/unavailable real workflow acceptance, not a passing qualification.

The implementation is committed locally as `bd6ae66 task(028): add studio spatial configuration`.
It was not pushed and no PR was opened because neither the Task 028 real Kit acceptance nor Task
027 prerequisite qualification is complete.
