> Follow `AGENTS.md`. Create the required ExecPlan before implementation. This is the final task in the low-code program; do not start a later numbered task.

# TASK-048 — Low-code simulation qualification

## Goal

Qualify the complete guided low-code simulation-engineering path from project launch through
readiness, schema forms, connections, visual task/recipe authoring, experiments, reusable robot
runtime, and imported/primitive-built robot simulation. Produce reproducible evidence that shows
what actually ran and keep the main branch releasable with honest hardware and safety boundaries.

## Prerequisites

- Tasks 039–047 are merged in order and their focused checks and documentation are available;
- Tasks 033, 036, 037, and 038 remain the existing release/demo/qualification baseline;
- a supported L0 environment is available for the full path, and any Isaac Sim 6 L1/L2 runner is
  identified separately. Missing GPU/Kit/importer dependencies must be reported unavailable.

## Concrete deliverables

- an end-to-end low-code qualification command and machine-readable report;
- clean-checkout scenarios that use the guided flow to preview and explicitly Save a canonical
  project, resolve readiness, author connections and task/recipe data, define an experiment, and
  run it through the reusable simulation runtime;
- qualification fixtures for one existing supported robot, one imported robot, and one primitive
  robot, with explicit simulation-only support and observed fidelity;
- nominal, invalid, ambiguous, fault/recovery, cancel, timeout, restart, unavailable-backend,
  source-integrity, and Save-transaction failure cases;
- deterministic replay/comparison, report integrity, CI/Make documentation, limitations, and a
  release checklist that distinguishes interface, kinematic/physics, process, hardware, and
  safety evidence.

## Public interface and schema decisions

- Add `make low-code-simulation-check` and a stable underlying runner that composes the existing
  application services, schema/domain validators, simulation bridge, demo, and qualification
  reports. It must not introduce a second runtime or tree interpreter.
- Add `schemas/low_code_qualification_report.schema.json` with source revisions/digests, task
  surface results, canonical artifact hashes, experiment seeds/faults, selected components and
  adapters, requested/achieved fidelity, observed backend, assertion outcomes, unavailable or
  failed gates, limitations, and `physical_operation_authorized: false`.
- The qualification input references the canonical `cell.yaml`, USD scene,
  BehaviorTree.CPP XML, `recipes/`, and `scenarios/`; generated projects, experiment manifests,
  reports, and logs are derived artifacts. The report must bind every result to exact source and
  command identities.
- Extend existing qualification additively. Preserve the nine scenario categories, existing pen
  and kitting evidence, schema versions, runtime interfaces, and external Task 027 L2 boundary.
  A low-code or robot-model label cannot upgrade actual fidelity.
- Qualification evidence is engineering evidence only. It cannot approve recipes, promote
  imported/built robots to hardware support, or replace independent safety review.

## Canonical artifacts and Save-after-preview

The qualification path must preserve `cell.yaml` as the operational graph, USD as the spatial
scene, BehaviorTree.CPP XML as the task, `recipes/` as recipe source, and `scenarios/` as
simulation source. It must prove that previews do not write and that explicit Save-after-preview
is the only authoring persistence boundary; reports and logs remain derived evidence.

## Acceptance tests

- From a clean supported checkout, an L0 run completes the guided preview → explicit Save →
  readiness → schema form/source → typed connections → canonical task/recipe → experiment →
  reusable robot simulation path and writes predictable evidence; a failure returns non-zero.
- Repeating identical inputs, source revisions, and seeds produces byte-identical normalized
  canonical/replay evidence. Changed IDs, paths, source, seeds, or faults are visible in the
  comparison and cannot be silently reused.
- Readiness blocks missing/invalid/ambiguous source and reports missing Isaac/adapter capability
  as unavailable; no synthetic success or hard-coded report can pass a gate.
- Form/source, connection, BehaviorTree XML, recipe, scenario, and experiment round-trips preserve
  canonical semantics. Preview never writes, explicit Save is transactional, and injected Save
  failure leaves all prior artifacts unchanged.
- Existing, imported, and primitive robots pass the reusable simulation contract at their declared
  fidelity. Imported/built robots are simulation-only; L0/L1/L2 labels reflect observed backend,
  and unsupported higher-fidelity requests fail or report unavailable.
- Nominal, invalid, ambiguity, fault/recovery, cancellation, timeout, restart, corrupt-source,
  unavailable-backend, and uncertain-process outcomes are bounded, traceable, and expected. No
  uncertain process outcome is automatically retried as success.
- Existing `make lint`, `make test`, `make validate-examples`, release qualification, demo,
  kitting, Studio, and relevant robot checks remain green; supported Isaac checks run only on the
  supported runner and are reported honestly elsewhere.

## Explicit non-goals

- physical robot control, commissioning, process-quality acceptance, production deployment,
  hardware support promotion, or independent functional-safety implementation/certification;
- replacing any existing compiler, runtime, simulation engine, Isaac importer, MoveIt planner,
  BehaviorTree.CPP executor, evidence store, or schema contract;
- making the entire platform cloud-dependent or requiring Studio for production runtime;
- starting a post-048 product roadmap task in this task.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6–21;
- `docs/architecture.md`, sections 1–14;
- `docs/cell-studio.md`, sections 1–13;
- `docs/simulation.md`, `docs/simulation-demo.md`, `docs/testing.md`, and `docs/safety-security.md`;
- `ROADMAP.md`, `CODEX_TASK_INDEX.md`, and the ExecPlans created by Tasks 039–047;
- `codex/tasks/TASK-033-software-release-qualification.md`, `TASK-036-executable-release-qualification.md`,
  `TASK-037-simulation-demo-workflow.md`, and `TASK-038-simulation-component-expansion.md`.

## Required checks

- Add and run `make low-code-simulation-check` plus its focused subchecks for generated project,
  readiness, schema authoring, connections, task/recipe, experiments, robot runtime/import/build,
  deterministic replay, and failure paths;
- run `make lint`, `make test`, `make validate-examples`, `make release-qualification-check`,
  `make simulation-demo-check`, and `make kitting-simulation-check`;
- run the supported Isaac Sim 6/OpenUSD/PhysX integration and imported/built robot probes when
  available; missing prerequisites must produce explicit unavailable evidence, not a pass;
- run `git diff --check`, staged checks, clean status/log verification, and review the complete
  report for source identity, actual fidelity, limitations, and safety disclaimer.

## Safety and fidelity limits

This qualification proves a simulation-first engineering workflow only. It does not implement or
verify emergency stop, guards, safe robot stop, laser safety, interlocks, conformity, process
quality, hardware accuracy, or production acceptance. Rated safety remains independent. The report
must distinguish L0 contract evidence, L1 kinematic evidence, L2 physical simulation evidence,
process evidence, hardware evidence, and safety evidence; unavailable evidence stays unavailable.

Imported and primitive-built robots remain simulation-only, and functional safety remains
independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-048-low-code-simulation-qualification.md` using
`PLANS.md`. Record the end-to-end matrix, additive qualification/report schema, canonical source
and Save-after-preview invariants, robot fixture boundaries, deterministic replay, failure and
unavailable behavior, safety/fidelity limits, and rollback. Update it through final hosted checks
and stop after this task; do not start a later task.
