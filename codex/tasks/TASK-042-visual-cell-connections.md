> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Tasks 043–048 in this task.

# TASK-042 — Visual cell connections

## Goal

Provide a typed visual connection canvas for assembling a cell from declared component ports.
Mechanical mounts, capability/ROS links, industrial I/O, and modeled safety dependencies must be
easy to distinguish, validated by existing domain contracts, and persisted only to the canonical
operational graph and USD scene when explicitly saved.

## Prerequisites

- Task 041 is merged and schema-driven authoring can present port/configuration data;
- Tasks 005, 015, 016, 017, and 028 are merged with registry resolution, placement, connection
  validation, paired scene editing, and spatial configuration;
- `cell.yaml` is the operational connection source and USD is the spatial source; aliases and
  canvas layout are not persistence keys.

## Concrete deliverables

- a dockable typed connection canvas with separate mechanical, software/capability,
  industrial-I/O, and modeled-safety layers;
- port palette/search, endpoint highlighting, direction/type/capability validation, mechanical
  snap preview, transform/frame/collision findings, and removal/dependency warnings;
- deterministic edge identity and generated path/transform defaults only when the endpoints and
  mount relationship are unambiguous;
- application-service commands for preview, stage, remove, undo/redo, and validation, reusing the
  Task 005/017 resolver rather than reproducing its rules in UI code;
- connection layout metadata and focused tests for valid, invalid, cross-layer, spatial, and
  Save-failure cases.

## Public interface and schema decisions

- Extend the existing application-service boundary with `PreviewCellConnection`,
  `StageCellConnection`, `RemoveCellConnection`, and `ValidateCellConnections`; return a typed
  `ConnectionPreview` containing endpoint IDs, proposed transforms/prim paths, findings, and
  candidate hashes.
- Existing `cell.yaml` connection entries remain the canonical serialization with stable
  component instance IDs and port IDs. Display aliases, graph coordinates, selection state, and
  routing are derived layout metadata, stored separately if needed.
- Preserve `kind` values `mechanical`, `software`, `industrial_io`, and `safety`. If the current
  schema needs it, add the backward-compatible optional boolean `modeled_only`, constrained to
  `kind: safety` and always true; do not reinterpret an ordinary software edge as safety.
- Mechanical application stages the USD reparent/snap transform and the `cell.yaml` edge as one
  paired in-memory candidate. Logical and I/O edges update only the operational candidate.
- Preview never writes. Explicit Save validates the complete `cell.yaml`/USD pair and uses the
  existing recovery/atomic replacement path. A safety edge is descriptive review metadata and
  never an executable safety or ROS connection.

## Canonical artifacts and Save-after-preview

The canvas preserves `cell.yaml` as the operational graph, USD as the spatial scene,
BehaviorTree.CPP XML as the task, `recipes/` as recipe source, and `scenarios/` as simulation
source. Graph layout is derived; only explicit Save-after-preview may persist a validated edge or
paired spatial change.

## Acceptance tests

- Compatible mechanical ports produce a deterministic preview with the expected transform,
  frame, prim path, payload/collision findings, and no file mutation until Save.
- Software/capability and industrial-I/O edges reject missing endpoints, wrong direction/type,
  unavailable capability, duplicate edge, and incompatible component instance IDs with stable
  findings; valid edges round-trip through the current schema.
- Safety-layer edges are visually distinct, persist as modeled-only metadata, are reported as
  non-executable, and cannot be used to authorize a physical process.
- Removing an instance with incident edges requires an explicit user choice and preserves the
  complete undo/redo candidate; aliases cannot change endpoint identity.
- Invalid/singular/uneditable snap data and injected USD or YAML replacement failures fail closed
  and leave both canonical artifacts unchanged.
- Reopening a saved project restores the same IDs, edges, transforms, and scene identity. Add
  success, invalid, cross-layer, spatial, undo/redo, and transactional-failure tests.

## Explicit non-goals

- a second connection resolver, arbitrary USD editing, automatic safety wiring, or live hardware
  I/O control;
- behavior-tree/recipe canvases, robot import/build, experiment management, or production
  deployment;
- treating a visual edge, safety status, or validation result as a rated safety function.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6–11, 15, and 19;
- `docs/architecture.md`, sections 3–8, 11–14;
- `docs/cell-studio.md`, sections 2–5, 8–10, and 12;
- `docs/domain-model.md`, `schemas/cell.schema.json`, and `schemas/component.schema.json`;
- `codex/tasks/TASK-017-connections-ui.md` and `TASK-028-studio-spatial-configuration.md`.

## Required checks

- Add and run `make studio-visual-connections-check` (or the documented underlying locked `uv`
  command) covering all graph layers, spatial preview, invalid inputs, undo/redo, and no-write
  preview;
- run `make lint`, `make test`, and `make validate-examples`;
- run `make studio-connections-check`, `make studio-spatial-configuration-check`, and the Kit
  OpenUSD connection probe where available;
- run `git diff --check` and validate canonical cell/USD identity before and after Save.

## Safety and fidelity limits

The canvas models safety dependencies for engineering review only. It must not implement guard
locking, emergency stop, safe robot stop, laser enable, interlock override, or any other rated
function. Simulation fidelity and adapter status are displayed from authoritative manifests and
cannot be raised by adding a graph edge.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-042-visual-cell-connections.md` using `PLANS.md`.
Document layer separation, endpoint/schema compatibility, mechanical paired-edit behavior,
modeled-only safety semantics, Save-after-preview, tests, safety boundary, and rollback. Update
it as implementation decisions are made and stop before Task 043.
