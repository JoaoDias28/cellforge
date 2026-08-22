> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Task 048 in this task.

# TASK-047 — Primitive robot builder

## Goal

Let an engineer build a small articulated robot model from validated primitive links and joints,
then generate the same reusable simulation-only robot contract used by imported robots. The
builder must be deterministic and useful for early simulation experiments without pretending to
be a CAD, robot-design, or physical-validation system.

## Prerequisites

- Task 046 is merged and the import/output package contract is proven;
- Task 045 is merged with the reusable robot model and adapter runtime;
- Tasks 039–044 provide guided project, schema, connection, task/recipe, and experiment flows;
- Isaac Sim/OpenUSD articulation and physics authoring APIs are available for the supported
  simulation path.

## Concrete deliverables

- a schema-driven primitive robot definition and guided builder/canvas for links, joints, frames,
  primitive visual/collision geometry, inertial values, limits, and tool mounts;
- deterministic validation of a single rooted acyclic link tree, joint parent/child references,
  axis/origin/limit data, collision geometry, and declared capabilities;
- generation of an articulated USD/model package through Isaac Sim/OpenUSD physics APIs and the
  Task 045 robot model contract;
- preview of the generated hierarchy, frames, limits, collisions, and simulation readiness,
  followed by explicit Save of the source definition and derived package;
- L0 and supported Isaac simulation tests, invalid graph/geometry tests, deterministic output
  tests, and documentation of model limitations.

## Public interface and schema decisions

- Add `schemas/primitive_robot.schema.json` as a Draft 2020-12 source contract. It contains
  `robot_id`, `version`, ordered `links`, `joints`, `frames`, `visual`, `collision`, inertial
  values, limits, tool mounts, and declared capabilities; allowed geometry primitives are
  explicitly enumerated (box, cylinder, sphere, capsule, and approved mesh reference).
- Add pure `PreviewPrimitiveRobot`, `ValidatePrimitiveRobot`, and `SavePrimitiveRobot` commands.
  The preview returns normalized definition, generated IDs/paths, model digest, warnings, and
  fidelity; it never writes files.
- The primitive definition is the reproducible authoring source. Generated `component.yaml`,
  articulated USD, collision/visual assets, and Task 045 model manifest are derived outputs with
  exact source/tool digests. `cell.yaml`, project USD, BehaviorTree.CPP XML, recipes, and
  scenarios remain their existing canonical artifacts.
- Link/joint/frame IDs derive from explicit names only when unique and stable. Multiple roots,
  parent choices, tool-frame roles, or missing geometry require an explicit user choice; defaults
  cannot hide ambiguity. Layout metadata is non-canonical.
- Use Isaac Sim/OpenUSD `UsdGeom`, `UsdPhysics`, and PhysX authoring/runtime facilities rather
  than a custom articulation or physics implementation. The generated component is
  `support.level: simulated` with no hardware adapter.

## Canonical artifacts and Save-after-preview

The builder preserves `cell.yaml` as the operational graph, USD as the spatial scene,
BehaviorTree.CPP XML as the task, `recipes/` as recipe source, and `scenarios/` as simulation
source. Primitive definitions and generated package changes are preview-only until explicit
Save-after-preview validates and writes them.

## Acceptance tests

- A valid two- or three-link primitive definition produces deterministic normalized source,
  component manifest, articulated USD hierarchy, joint limits, tool frame, and collision refs;
  same inputs produce identical digests.
- Multiple roots/cycles, missing links, duplicate IDs, invalid axes/origins, non-positive mass or
  inertia, invalid limits, unsupported primitive, missing mesh, path escape, and ambiguous tool
  frame fail validation and block Save.
- Preview does not modify the source directory or project canonical files. Explicit Save writes
  reproducible source/derived outputs; injected failure leaves no partial package and preserves
  previous outputs.
- The generated robot passes Task 045 validation and runs in L0. Supported Isaac runs report
  actual articulated/PhysX execution; missing GPU/Kit/importer prerequisites are unavailable,
  not successful CPU substitutes.
- The builder output can be placed through the existing component/connection flow and referenced
  by a canonical task/recipe/scenario without simulator-specific branches.
- Add success, invalid graph/geometry, ambiguity, deterministic replay, no-write, Save-failure,
  L0, and supported Isaac integration tests.

## Explicit non-goals

- CAD, mesh sculpting, automatic robot synthesis/optimization, calibration, payload/reach proof,
  collision certification, or physical robot control;
- replacing Isaac Sim/OpenUSD physics, MoveIt, BehaviorTree.CPP, importers, or the reusable robot
  contract;
- hardware adapters, commissioning, production qualification, safety logic, or silently inventing
  geometry/limits from a display name.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6–11, 15, 18–21;
- `docs/architecture.md`, sections 3–8, 9, 12–14;
- `docs/cell-studio.md`, sections 4–6, 11–13;
- `docs/simulation.md`, sections 1–3, 6, 8, 10–14;
- `docs/component-sdk.md`, `docs/testing.md`, and `schemas/component.schema.json`;
- `codex/tasks/TASK-045-reusable-robot-simulation-runtime.md` and `TASK-046-robot-import-wizard.md`.

## Required checks

- Add and run `make primitive-robot-builder-check` (or the documented underlying locked `uv`
  command) for valid/invalid definitions, deterministic generation, no-write preview, Save
  failure, L0, and fidelity-unavailable cases;
- run `make lint`, `make test`, and `make validate-examples`;
- run reusable robot, Studio schema, connection, simulation, and supported Isaac/OpenUSD checks;
  report Isaac/PhysX unavailability honestly;
- run `git diff --check` and inspect generated USD/model identity and support metadata.

## Safety and fidelity limits

Primitive robots are simulation-only engineering models. Their simplified geometry, inertial data,
joint limits, and controller mapping are placeholders unless separately validated; they cannot
authorize physical motion, implement safety, prove reach/payload/accuracy, or qualify a process.
Safety status is read-only and actual simulation fidelity is never inferred from the builder form.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-047-primitive-robot-builder.md` using `PLANS.md`.
Record the primitive schema, deterministic source/derived-output contract, Isaac/OpenUSD reuse,
validation/failure behavior, Save-after-preview, tests, simulation-only limits, and rollback.
Update it at each milestone and stop before Task 048.
