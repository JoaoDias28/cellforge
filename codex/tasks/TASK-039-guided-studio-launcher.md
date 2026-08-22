> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Tasks 040–048 in this task.

# TASK-039 — Guided Studio launcher and deterministic project flow

## Goal

Give an engineer a guided entry point into Cell Studio that can create or open a cell project,
show a complete deterministic preview, and save only after explicit confirmation. The flow must
make the first useful project visible without hiding the canonical source or trapping domain
rules in Kit callbacks.

## Prerequisites

- Task 038 is merged and its pen and kitting examples, simulation contracts, and evidence limits
  are available;
- Tasks 004, 014, 015, and 016 are merged, including project validation, the Kit shell,
  paired project/scene buffers, and component placement;
- `cell.yaml`, the referenced USD scene, `behavior_tree.xml`, `recipes/`, and `scenarios/` remain
  the canonical project artifacts;
- functional safety remains an independent rated-hardware responsibility.

## Concrete deliverables

- a guided Create/Open/Review flow in the existing Studio application-service boundary;
- template and blank-project descriptors for the existing supported examples, with a clear
  simulation-only starting mode;
- a deterministic project skeleton preview showing generated paths, component instance IDs,
  schema versions, unresolved choices, validation findings, and the exact candidate hashes;
- deterministic allocation of project-relative paths, cell IDs, component IDs, aliases, and
  defaults only when the input is unambiguous;
- an explicit Save command that validates and transactionally persists the candidate, including
  the paired `cell.yaml`/USD identity check and recovery behavior from Task 015;
- cancel, reopen, dirty-state, failure, and no-partial-write tests plus user documentation.

## Public interface and schema decisions

- Add application-service commands named `CreateProject`, `OpenProject`, `PreviewProject`,
  `ConfirmProjectSave`, and `CancelProjectDraft`; keep Kit widgets as thin callers.
- `CreateProjectRequest` contains a template ID, destination directory, cell display name,
  requested schema version, and explicit choices. `ProjectPreview` contains candidate hashes,
  generated relative paths, immutable IDs, findings, required choices, and `can_save`.
- A preview is an in-memory DTO and is not a third source of truth. If it is exported for
  diagnostics, validate it with a versioned `schemas/studio_project_preview.schema.json`; the
  canonical project remains the source files, not the preview.
- Generated IDs and paths use a stable allocator seeded by the request and repository rules.
  Never derive persistence keys from display names when a collision or semantic ambiguity is
  possible; request a choice instead. Aliases remain display-only.
- The flow must create the existing canonical `cell.yaml`, USD scene, BehaviorTree.CPP XML,
  recipe references, and scenario references. Editor layout metadata is optional derived data.
- Preview never writes. Only explicit Save may replace files, and paired operational/spatial
  edits must use one logical transaction with the existing recovery journal. There is no
  autosave, hidden normalization, or background source mutation.

## Canonical artifacts and Save-after-preview

This task preserves `cell.yaml` as the operational graph, the USD scene as the spatial graph,
BehaviorTree.CPP XML as the canonical task, `recipes/` as canonical recipe source, and
`scenarios/` as canonical simulation source. Every generated project is preview-only until an
explicit Save-after-preview validates and transactionally persists the intended artifacts.

## Acceptance tests

- Same template, destination, choices, and seed produce byte-identical previews and identical
  generated IDs, paths, and defaults; a conflicting destination or ambiguous choice blocks Save.
- Preview of a blank and an existing supported template reports every generated canonical file
  and does not change the filesystem, dirty state, or source hashes.
- Invalid schema version, missing template, path escape, duplicate ID, missing scene reference,
  or unresolved required choice produces a structured failure and never claims success.
- Explicit Save validates `cell.yaml` and USD together, writes the canonical pair atomically,
  and leaves a recovery journal on injected replacement failure; reopening reproduces all IDs,
  paths, hashes, and references.
- Cancel and close-without-Save leave the original project unchanged. A failed Save cannot leave
  a new `cell.yaml` paired with an old scene or vice versa.
- The guided result can be opened by the existing headless validator and is usable by the
  existing simulation path without Studio-only branches.
- Add at least one success, invalid-input, ambiguity, and transactional-failure test; the
  supported Kit lifecycle probe must remain green where Isaac Sim is available.

## Explicit non-goals

- schema-driven field forms, readiness guidance, connection canvases, task/recipe canvases, or
  experiment management from Tasks 040–044;
- robot import, robot generation, hardware adapters, production deployment, or safety logic;
- replacing the existing project service, validator, component browser, or CLI;
- automatically choosing a component, recipe, scenario, safety dependency, or physical target
  when the request is ambiguous.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6, 7, 10, 11, 15, 19, and 21;
- `docs/architecture.md`, sections 3–8 and 14;
- `docs/cell-studio.md`, sections 1–8 and the paired Save contract from Task 015;
- `docs/testing.md`, sections 1, 2, and 6;
- `codex/tasks/TASK-015-studio-project-scene.md` and `TASK-016-component-browser-placement.md`.

## Required checks

- Add and run a focused `make studio-guided-launcher-check` (or its documented underlying
  locked `uv` command), covering preview determinism, invalid input, no-write preview, and
  transactional Save;
- run `make lint`, `make test`, and `make validate-examples`;
- run `make kit-extension-check` and the supported Isaac Sim headless launcher probe when the
  environment provides Isaac Sim; report it unavailable rather than passing it by substitution;
- run `git diff --check` and inspect canonical source hashes before and after each Save test.

## Safety and fidelity limits

The launcher is an engineering authoring surface. It may display modeled safety dependencies and
simulation readiness, but it does not implement, bypass, or certify emergency stop, guard
interlocks, safe robot stop, laser enable, or any other rated function. Projects created here are
simulation/development projects unless a later, separately governed process promotes them.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-039-guided-studio-launcher.md` using `PLANS.md`.
Record the current Task 038 baseline, source-of-truth and Save-after-preview design, allocator
and failure behavior, ordered implementation milestones, validation evidence, safety limits,
and rollback. Update it after each milestone and do not mark later tasks complete.
