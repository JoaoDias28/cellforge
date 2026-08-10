# Task 017 connection authoring and validation UI

## Goal
Cell Studio can browse declared ports and author validated mechanical, software, industrial-I/O,
and modeled-safety connections while preserving `cell.yaml` as the operational graph and USD as
the spatial scene. Mechanical edits update both sources as one undoable operation, and modeled
safety dependencies remain visibly descriptive and never become executable wiring.

## Scope
Included: pure connection browsing and preview/application services; typed logical edge creation;
mechanical snap transform authoring; domain-resolver validation; safety-specific presentation and
disclaimer; paired in-memory undo/redo; source persistence through the existing transactional save;
thin Kit callbacks; deterministic tests; documentation; and Task 017 headless probes.

Excluded: simulation controls (Task 018), general constraint solving, collision/payload analysis
beyond existing validators, adapter generation, ROS graph generation, hardware/safety enforcement,
and schema-breaking changes.

## Current state
Tasks 005 (`c86e18f`), 015 (`3bd9752`), and 016 (`a0426e8`) are merged ancestors of clean
`origin/main`. Task 005 resolves exact component versions and validates connection endpoint
existence, kind, direction, and type compatibility. Tasks 015/016 provide paired YAML/USD buffers,
cross-reference validation, transactional save, immutable shared instance IDs, placement/removal,
and whole-pair undo/redo. The pre-edit baseline passes Ruff, both mypy scopes, 240 tests, example
validation, 28 Studio tests, extension metadata, and Task 015/016 deterministic probes. GNU Make
and Isaac Sim 6 are unavailable on this Windows host.

## Design
A Kit-free connection service will load the project-local registry and canonical in-memory
`cell.yaml`, expose deterministic instance/port records grouped by connection kind, and create
candidate `Connection` data. It delegates validation to the existing domain resolver against the
candidate graph, filtering returned findings to the proposed connection so UI and service code do
not duplicate compatibility rules. Invalid or ambiguous endpoints fail closed and do not mutate
either source.

Logical software and industrial-I/O connections change only `cell.yaml`. Modeled-safety
connections use the same typed validation path but are marked modeled-only in service/UI records,
carry a persistent review note where supported by the existing schema, and never author executable
mapping or USD changes. Their UI layer has a distinct style label and an explicit independent-safety
disclaimer.

Mechanical preview computes the target snap from the two declared mount-frame transforms. Applying
it writes the typed graph edge and updates the source component USD transform as one candidate
paired edit, followed by joint operational/spatial validation. The service fails closed when
required transforms or editable USDA prims are unavailable. Application undo/redo stores the whole
pair, and the existing explicit Save command remains the only filesystem persistence boundary.

No production dependency or schema migration is planned. Any necessary public resolver helper will
remain backward compatible and live in the domain package.

## Work sequence
1. Add pure port graph records and connection candidate validation; verify compatible and
   incompatible software, I/O, and safety cases without Kit.
2. Add mechanical snap preview/application and paired validation; verify YAML/USD coherence,
   immutable IDs, invalid transforms, and mutation failure paths.
3. Integrate application commands, undo/redo, and thin Kit connection panel callbacks with distinct
   modeled-safety presentation.
4. Add documentation and deterministic Task 017 non-Kit/Kit probes, then run focused and full checks.
5. Inspect the complete diff, commit, publish a ready PR, wait for required checks, merge only when
   green/mergeable, and synchronize local `main`.

## Validation
- `make lint`, `make test`, and `make validate-examples`, or their exact Makefile command bodies.
- Existing Kit, Task 015, and Task 016 checks plus the new Task 017 deterministic headless target.
- Focused tests for port browsing, compatible edge creation, incompatible kind/direction/type,
  duplicate/unknown endpoints, modeled-safety metadata/presentation, mechanical snap coherence,
  invalid transform input, and injected edit/backend failure.
- Documented Isaac Sim 6 `--no-window` Task 017 command when the runtime is available.
- `git status --short`, `git diff`, `git diff --check`, staged checks, post-commit verification, PR
  checks, mergeability, and synchronized default-branch verification.

## Risks and rollback
Text USDA editing supports only the established deterministic subset and must fail closed on an
unlocatable prim or transform representation. The resolver may report unrelated graph findings, so
candidate acceptance must distinguish findings caused by the proposed edge without hiding existing
project problems. Mechanical transform math must be deterministic and documented. Reverting the
Task 017 commits removes the feature without migrating existing project data.

## Progress
- [x] 2026-08-10 - Read required specifications, task, architecture/ADR documents, prerequisite
  plans/implementations, and Git history; confirm prerequisite ancestry and a green baseline.
- [x] 2026-08-10 - Implement pure connection browsing, validation, and mechanical snap services.
- [x] 2026-08-10 - Integrate application/UI commands, safety presentation, and undo/redo.
- [x] 2026-08-10 - Complete probes, documentation, and local regression validation.
- [x] 2026-08-10 - Commit, publish a ready PR, wait for CI, merge, and synchronize local `main`.

## Decisions
- 2026-08-10 - Reuse Task 005 resolver validation as the authority for port compatibility; Studio
  services construct candidates and present findings but do not reproduce domain rules.
- 2026-08-10 - Keep safety dependencies on a distinct modeled-only view/persistence path and never
  generate ordinary executable wiring or claim safety enforcement.
- 2026-08-10 - Treat connection edits as in-memory paired-source operations; Task 015 transactional
  Save remains the filesystem commit boundary.
- 2026-08-10 - Require each mechanical port to declare a finite 4x4
  `metadata.snap_transform`; do not infer spatial alignment from display geometry or silently assume
  missing engineering data.
- 2026-08-10 - Reparent the target component prim beneath the source component prim and update every
  affected operational `usd_prim` prefix in the same edit, so component subtrees and immutable IDs
  remain coherent across both canonical artifacts.

## Results
Implemented a deterministic typed port browser and graph, resolver-backed edge authoring for all
four connection kinds, modeled-safety-only persistence/presentation, mechanical snap preview and
paired YAML/USD application, whole-edit undo/redo state, thin Kit callbacks, transactional-save
integration, documentation, and non-Kit/Kit acceptance probes.

The final local run passes Ruff formatting/lint, strict mypy (57 core sources and 11 Studio/test
sources), 249 repository tests, 7 focused Task 017 tests, validation of 5 canonical schemas, 6
component configuration schemas, and 19 example YAML documents, the deterministic Task 017 probe,
and extension manifest verification. Earlier in the same final cycle, all 36 Studio tests plus Task
015 and Task 016 focused regressions/probes also passed.

GNU Make is unavailable, so the exact Makefile command bodies were run with `uv`. Isaac Sim 6 is
unavailable because neither `isaac-sim.bat` nor `isaacsim` is installed or on `PATH`; the documented
`scripts/verify_kit_connections.py` OpenUSD integration probe was therefore not executed. No ROS
packages changed, so local ROS build/test checks are not applicable.

Implementation commit `c342177` was published in ready PR #12. GitHub Actions run 31398531259
completed successfully: `Python 3.12 validation` passed lint, typing, tests, and example validation;
`ROS 2 Jazzy build and test` passed repository setup, dependency resolution, workspace build, and
workspace tests. GitHub reported the PR clean and mergeable. Merge commit `c23bbdd` was synchronized
to local and remote `main`, both resolving to `c23bbdd13388ef0836d652995879aec4531cbcee`, with the
Task 017 implementation commit confirmed as an ancestor. Task 018 was not started.
