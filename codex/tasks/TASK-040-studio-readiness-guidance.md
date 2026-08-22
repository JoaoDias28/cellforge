> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Tasks 041–048 in this task.

# TASK-040 — Studio readiness guidance

## Goal

Turn the current project, component, schema, asset, and simulation preconditions into an
actionable Studio readiness view. An engineer must see what is ready, blocked, unavailable, or
advisory before authoring or running a simulation, with every finding tied to a source and a
safe next action.

## Prerequisites

- Task 039 is merged, including the guided project preview and explicit Save boundary;
- Tasks 004, 005, 015, 016, 018, 027, 033, 036, 037, and 038 are available as the existing
  validators, registry, simulation, fidelity, and evidence contracts;
- readiness must not become a new runtime authority or a substitute for independent safety.

## Concrete deliverables

- a pure readiness application service and a Studio panel that evaluates a selected project;
- checks for canonical file pairing, schema versions, component/port resolution, assets and
  frames, task and recipe references, scenario availability, adapter readiness, target fidelity,
  and evidence prerequisites;
- deterministic finding IDs, severity/status, source locations, remediation IDs, and links back
  to the guided flow or existing validator;
- actionable remediation previews that can stage a candidate but cannot write without explicit
  Save-after-preview;
- machine-readable readiness reports and focused tests for pass, block, advisory, unavailable,
  stale, malformed, and recovery cases.

## Public interface and schema decisions

- Add a pure `EvaluateStudioReadiness` service returning `StudioReadinessReport`; the report has
  `project_identity`, `checks`, `summary`, `requested_fidelity`, `observed_fidelity`, and
  `generated_at` omitted or normalized so identical inputs remain deterministic.
- Each check has a stable `check_id`, category, status (`pass`, `blocked`, `advisory`, or
  `unavailable`), severity, source reference, message, remediation ID, and evidence references.
  `unavailable` is never coerced to `pass`.
- Add `schemas/studio_readiness_report.schema.json` as a Draft 2020-12 report contract. It is
  diagnostic/evidence data, not a canonical project source and must not be required by Cell
  Runtime.
- Reuse existing domain validators and registry resolution. The panel must not copy schema,
  capability, compatibility, or fidelity rules into callbacks.
- Readiness remediation returns a candidate preview. Canonical `cell.yaml`, USD,
  BehaviorTree.CPP XML, recipes, and scenarios change only through explicit Save and the existing
  transactional paired-artifact path.

## Canonical artifacts and Save-after-preview

Readiness never replaces the canonical `cell.yaml` operational graph, USD spatial scene,
BehaviorTree.CPP XML task, `recipes/` recipe source, or `scenarios/` simulation source. Any
remediation is a candidate only; explicit Save-after-preview is the sole authoring write boundary.

## Acceptance tests

- A valid pen and kitting project reports deterministic passing checks with stable check IDs and
  no timestamps in normalized output; the report identifies the requested and actually observed
  fidelity.
- Missing component manifest, missing USD prim/instance ID, bad port, invalid recipe/schema,
  absent scenario, unresolved adapter, stale calibration, or malformed behavior tree produces a
  blocking finding linked to the correct source.
- Missing Isaac Sim/GPU or an unsupported adapter produces `unavailable`, never a synthetic L2
  pass; L0 readiness remains explicitly L0.
- A modeled safety dependency or external safety status is shown in a separately labeled safety
  review category. The report never says that application readiness is functional-safety
  validation and cannot enable physical operation.
- Remediation preview changes no source file. Explicit Save validates the full candidate, and an
  injected failure leaves the original canonical pair and source hashes intact.
- Add tests for nominal, invalid input, stale/missing data, unavailable fidelity, remediation
  failure, and deterministic report replay. The panel displays backend failure explicitly.

## Explicit non-goals

- fixing arbitrary project data automatically, editing source in a background callback, or
  replacing the CLI/compiler validators;
- schema-driven authoring forms, visual connections, task/recipe canvases, or experiments;
- safety enforcement, safety certification, physical commissioning, or production authorization;
- turning warnings into approval or promoting component support levels.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6–12, 15, 18, and 19;
- `docs/architecture.md`, sections 1, 4–8, 10–14;
- `docs/cell-studio.md`, sections 3–5, 10–13;
- `docs/simulation.md`, sections 6, 8, 11–14;
- `docs/testing.md`, sections 1, 2, 6, and 10;
- `codex/tasks/TASK-035-simulation-readiness-bootstrap.md` and `TASK-036-executable-release-qualification.md`.

## Required checks

- Add and run `make studio-readiness-check` (or the documented underlying locked `uv` command)
  with nominal, blocked, advisory, unavailable, and deterministic-report cases;
- run `make lint`, `make test`, and `make validate-examples`;
- run the existing focused Studio, simulation, and qualification checks; run the Kit probe when
  available and report unavailable integration honestly;
- run `git diff --check` and verify no remediation path writes before explicit Save.

## Safety and fidelity limits

Readiness is engineering guidance and standard-control refusal only. It may prevent a simulation
or authoring operation when required inputs are missing, and it may display safety state, but it
does not implement rated safety functions, reset interlocks, authorize laser emission, or certify
hardware. Fidelity is bounded by the weakest selected adapter and actual backend execution.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-040-studio-readiness-guidance.md` using `PLANS.md`.
Document the check inventory, report schema, reuse of existing validators, remediation preview
and Save-after-preview behavior, unavailable/fidelity policy, tests, safety boundary, and
rollback. Update progress as checks are implemented and do not start Task 041.
