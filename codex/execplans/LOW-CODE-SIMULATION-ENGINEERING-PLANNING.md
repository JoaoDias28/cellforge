# Low-code simulation engineering planning program

## Goal

Define an incremental, implementation-ready Task 039–048 program for guided low-code cell
engineering. The program must make a new cell reproducible from canonical source artifacts,
extend the existing Cell Studio and simulation contracts, and leave the main branch releasable
after every task without claiming hardware, process, or functional-safety qualification.

## Scope

Included: ten decision-complete task specifications, their serial dependency chain, roadmap and
status corrections, and explicit invariants for deterministic generation, preview-before-save,
canonical `cell.yaml`/USD/BehaviorTree XML/recipes/scenarios, reusable robot simulation, and
honest simulation evidence.

Excluded: product code, schema files, UI changes, Isaac Sim assets, runtime changes, new
dependencies, hardware integration, safety logic, and starting Task 039.

## Current state

The repository is at merged Task 038. Tasks 035–038 established deterministic L0 qualification,
the documented L0/L2 demo boundary, and a reusable tray-kitting workflow. Cell Studio already has
application-service boundaries for project/scene, placement, connections, task/recipe, scenario,
and deployment/evidence workflows. `cell.yaml` is the operational source of truth; the USD stage
is the spatial source of truth; BehaviorTree.CPP XML, recipe YAML, and scenario YAML remain
canonical source artifacts. The current README status is stale because it still describes Tasks
036–038 as planned.

## Design

1. Deliver Tasks 039–048 serially: guided launcher → readiness guidance → schema authoring →
   connections → task/recipe authoring → experiment workbench → reusable robot runtime → import
   wizard → primitive builder → end-to-end qualification. Task 039 depends on Task 038 and each
   later task depends on its immediate predecessor.
2. Make deterministic generation the first implementation concern. Allocate IDs, paths, and
   defaults only when the input is unambiguous and stable; surface a required choice otherwise.
3. Treat every authoring operation as a previewed candidate. Preview does not write canonical
   files. An explicit Save validates and transactionally persists the candidate; paired
   `cell.yaml`/USD edits remain one logical save and failures cannot leave a half-updated pair.
4. Keep editor layouts and viewport state derived/non-canonical. Canonical operational, spatial,
   task, recipe, and scenario files must round-trip independently of the GUI.
5. Use existing Isaac Sim, OpenUSD, ROS 2, MoveIt, BehaviorTree.CPP, and simulation-bridge
   capabilities at their existing boundaries. The program adds orchestration and authoring
   contracts, not a second physics engine, planner, tree executor, importer, or safety system.
6. Imported and primitive-built robots are simulation-only until a separately approved hardware
   and safety program exists. Evidence reports actual backend/fidelity and never relabels L0 or
   CPU output as L1/L2.

## Work sequence

1. Add and review the ten task files with concrete interfaces, schemas, acceptance tests,
   non-goals, documentation, safety limits, and per-task ExecPlan requirements; acceptance:
   every task is implementable independently and names only merged prerequisites.
2. Update the task index with the exact serial dependency chain and update the roadmap/README;
   acceptance: status distinguishes merged simulation readiness, adapter prototypes, and planned
   low-code work.
3. Run documentation-oriented repository checks and inspect the complete diff; acceptance:
   schema/example validation and all available baseline checks remain green and no product code
   or Task 039 implementation is present.
4. Commit the planning change, publish a ready PR, wait for required checks, and merge only when
   GitHub reports the PR green and mergeable; acceptance: local and remote `main` include the
   planning commit and the worktree is clean.

## Validation

- `make lint`, `make test`, and `make validate-examples` where Make is available;
- the underlying locked `uv` Ruff, mypy, pytest, and example-validation commands when Make is
  unavailable;
- `git diff --check`, staged diff checks, status/log verification, hosted required checks, and
  final default-branch synchronization;
- manual review that the ten task files contain all required planning sections and that no
  implementation file, generated artifact, or Task 039 execution was added.

## Risks and rollback

The main risks are accidental scope expansion into product code, an implicit third source of
truth, non-deterministic generated IDs/defaults, and wording that implies safety or physical
qualification. The task specs explicitly constrain those risks. The planning change is additive
and can be reverted as one documentation commit without data or schema migration.

## Progress

- [x] 2026-08-22 — Verified the clean merged Task 038 baseline, required repository documents,
  architecture contracts, and prerequisite history.
- [x] 2026-08-22 — Ran available baseline lint, type, test, and example-validation commands.
- [x] 2026-08-22 — Add and review Task 039–048 specifications and program status updates.
- [ ] 2026-08-22 — Publish, pass hosted checks, merge, and verify default-branch state.

## Decisions

- 2026-08-22 — Use one serial chain so each low-code slice leaves the main branch releasable and
  no task depends on an unmerged future editor/runtime surface.
- 2026-08-22 — Guided flows and visual canvases sit above pure application services; they never
  become a second source of truth or a replacement for CLI/domain validation.
- 2026-08-22 — The import wizard supports URDF/Xacro, MJCF, and articulated USD through existing
  Isaac/ROS/OpenUSD importers; the primitive builder emits the same reusable robot contract.
- 2026-08-22 — Imported and built robots are simulation-only, and independent rated safety remains
  outside CellForge software and simulation.

## Results

The ten decision-complete task specifications, serial index chain, Phase 6/8 roadmap update, and
README status correction are complete. Publication and merge remain pending. This ExecPlan
intentionally records planning work only; Task 039 and all later implementation tasks remain
unstarted.
