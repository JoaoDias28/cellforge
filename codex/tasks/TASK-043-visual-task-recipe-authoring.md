> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Tasks 044–048 in this task.

# TASK-043 — Visual task and recipe authoring

## Goal

Make task and process authoring accessible through visual canvases while preserving canonical
BehaviorTree.CPP XML and versioned recipe YAML. The editor must use declared capabilities and
schemas, expose advanced source when needed, and prevent a Studio-only task from reaching runtime.

## Prerequisites

- Task 042 is merged and the project can author validated component/port connections;
- Tasks 011, 012, 013, 024, 028, 029, 041, and 042 are merged, including BehaviorTree.CPP
  registration/port validation, recipe lifecycle, schema forms, and capability resolution;
- the existing canonical task XML, `recipes/`, and `scenarios/` remain source-controlled artifacts
  used by headless runtime and simulation paths.

## Concrete deliverables

- a node/port canvas driven by installed BehaviorTree.CPP node manifests and capability contracts;
- typed port mapping, blackboard bindings, retry/timeout/cancel decorators, branch validation,
  node documentation, and an XML/source view;
- canonical BehaviorTree.CPP XML generation plus non-runtime editor layout metadata;
- schema-driven recipe draft/version authoring with units, ranges, compatibility findings,
  evidence links, diffs, and immutable released-version handling;
- scenario references and seed/fidelity fields remain explicit, with Save-after-preview tests
  for task XML, recipe YAML, and any coupled project references;
- documentation and end-to-end tests that load the generated tree through the existing validator
  and runtime/simulation contract.

## Public interface and schema decisions

- Reuse/extend `UpdateTaskDefinition`, `CreateRecipeVersion`, and `RunValidation` behind a pure
  `TaskCanvasDocument` and `RecipeDraft` model; do not create a second tree executor or recipe
  interpreter.
- Node manifests are the public source for node type, version, ports, blackboard types, required
  capabilities, and allowed decorators. Canvas IDs are stable within a draft but canonical XML
  identity is the node registration/type and explicit port data, not screen coordinates.
- `behavior_tree.xml` is the only executable task source. Optional `behavior_tree.layout.json`
  is derived editor metadata and must never affect execution. Recipe YAML under `recipes/` is the
  canonical recipe source; a layout sidecar is likewise non-authoritative.
- Recipe drafts may be created from schemas and compatibility metadata. Released recipe versions
  are immutable, approval remains a separate two-role workflow, and a task/recipe preview must
  include exact source diffs and referenced cell/component/schema hashes.
- The visual editor must not add simulator-specific nodes, recipe fields, or branches. Scenario
  YAML under `scenarios/` remains the explicit simulation input and is not silently embedded in
  the tree or recipe.
- Preview never writes. Explicit Save validates XML, recipe/schema/compatibility, project refs,
  and any paired `cell.yaml`/USD change before replacing canonical files.

## Canonical artifacts and Save-after-preview

The editor preserves `cell.yaml` as the operational graph, USD as the spatial scene,
BehaviorTree.CPP XML as the canonical task, `recipes/` as canonical recipe source, and
`scenarios/` as canonical simulation source. Canvas/layout edits are previews until an explicit
Save-after-preview validates and persists the canonical files.

## Acceptance tests

- A canvas built from the installed node manifest creates valid canonical XML with typed ports,
  capability references, decorators, and stable round-trip output; malformed or unknown nodes,
  ports, blackboard types, capabilities, cycles, and missing registrations block Save.
- The saved XML passes the existing compiler/supervisor preflight and runs through the same
  BehaviorTree.CPP runtime in L0; the editor never invokes a Python oracle as production runtime.
- A new recipe draft validates units, limits, product/process compatibility, component versions,
  and evidence requirements; a released recipe cannot be mutated and a new version has a diff.
- Same inputs generate deterministic XML/YAML and stable IDs/layout-independent hashes. A preview
  changes no source; explicit Save is transactional and an injected failure preserves all prior
  artifacts.
- The task and recipe reference the same canonical scenario inventory without simulator identity
  branches. Invalid/cancel/timeout/failure paths are represented by declared contracts and tested
  through the existing simulation/qualification surfaces.
- Add success, invalid-port, missing-capability, invalid-recipe, immutable-version,
  Save-failure, and headless runtime/simulation tests.

## Explicit non-goals

- replacing BehaviorTree.CPP, the compiler, recipe approval, MoveIt, or the simulation bridge;
- arbitrary code nodes, embedded Python, simulator-specific production logic, or auto-approval;
- experiment comparison, robot import/build, physical commissioning, or safety enforcement;
- writing directly to canonical files from a canvas callback or autosaving released recipes.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6–14, 18, and 19;
- `docs/architecture.md`, sections 3–8, 12–14;
- `docs/cell-studio.md`, sections 2–5, 10–13;
- `docs/testing.md`, sections 1–4, 6, 8, and 10;
- `codex/tasks/TASK-024-canonical-pen-runtime.md`, `TASK-029-studio-task-recipe-authoring.md`,
  and `TASK-030-studio-deployment-evidence.md`.

## Required checks

- Add and run `make studio-visual-task-recipe-check` (or its documented underlying locked `uv`
  command) for canvas/XML/recipe round trips and failure cases;
- run `make lint`, `make test`, and `make validate-examples`;
- run `make studio-task-recipe-authoring-check`, `make studio-simulation-check`, and the
  canonical runtime/qualification checks relevant to the changed contracts;
- run the supported Kit probe, `git diff --check`, and a clean-save/reopen hash comparison.

## Safety and fidelity limits

Visual task/recipe authoring is engineering configuration. It cannot authorize an unapproved
recipe, unknown material, failed interlock, laser emission, physical motion, or any safety-rated
function. Simulation evidence must state actual L0/L1/L2 backend and limitations; a visual tree or
recipe field cannot promote fidelity or production support.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-043-visual-task-recipe-authoring.md` using `PLANS.md`.
Record the node/port and recipe contracts, canonical XML/YAML versus layout metadata, lifecycle
and approval boundary, Save-after-preview transaction, runtime tests, safety/fidelity limits, and
rollback. Update it after each milestone and do not start Task 044.
