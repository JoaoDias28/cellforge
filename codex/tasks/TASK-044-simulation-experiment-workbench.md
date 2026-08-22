> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Tasks 045–048 in this task.

# TASK-044 — Simulation experiment workbench

## Goal

Give engineers a reproducible workbench for defining simulation experiments, selecting seeds and
scenarios, scheduling faults, replaying runs, comparing evidence, and understanding fidelity.
The workbench must orchestrate the existing simulation bridge and demo/qualification surfaces
without duplicating a runtime or physics engine.

## Prerequisites

- Task 043 is merged and visual tasks/recipes produce canonical, headless-valid source;
- Tasks 018, 020, 027, 030, 036, 037, and 038 are merged with simulation control, physical-model
  boundaries, demo artifacts, qualification evidence, and kitting scenarios;
- `scenarios/` remains the canonical scenario source and generated run artifacts remain derived.

## Concrete deliverables

- an experiment definition/editor with scenario selection, seed, backend/fidelity request,
  parameter overrides, fault schedule, repetitions, and assertion set;
- run controls for configure/reset/start/pause/step/cancel/finalize, using the existing typed
  simulation services and application service boundary;
- a run inventory with command/source/bundle/component/recipe/tree/scene identities, actual
  adapter/fidelity, logs, traces, assertions, limitations, and unavailable/failure status;
- deterministic replay and normalized comparison for traces/evidence, including diff views for
  assertions, events, outcomes, and observed fidelity;
- explicit Save-after-preview for experiment source and focused tests for successful, invalid,
  cancelled, timed-out, unavailable, and failed runs.

## Public interface and schema decisions

- Add pure `CreateExperiment`, `PreviewExperiment`, `RunExperiment`, `CancelExperiment`,
  `CompareExperimentRuns`, and `FinalizeExperimentEvidence` service contracts. UI callbacks may
  submit commands but cannot manipulate Kit timelines, USD, adapters, or ROS directly.
- Store an experiment manifest under a versioned `experiments/` directory only when explicitly
  saved. It references canonical `cell.yaml`, `behavior_tree.xml`, recipe, and `scenarios/`
  paths/digests rather than copying or replacing them. Add
  `schemas/simulation_experiment.schema.json` for this manifest.
- The manifest includes seed, repetition policy, requested fidelity/backend, fault schedule,
  assertion definitions, source identities, and an explicit `physical_operation_authorized:
  false` boundary. Timestamps and host-specific paths are excluded from normalized replay data.
- Run outputs are derived under the existing `.artifacts` conventions and use the existing
  evidence/report formats where possible. A report must record actual backend/fidelity and mark
  unavailable or failed runs non-passing.
- Reuse `simulation-bridge`, `run_simulation_demo.py`, existing adapter contracts, and
  qualification evidence. Do not add a second scenario interpreter or a simulator-specific tree
  branch.

## Canonical artifacts and Save-after-preview

Experiments reference, but do not replace, `cell.yaml` as the operational graph, USD as the
spatial scene, BehaviorTree.CPP XML as the task, `recipes/` as recipe source, and `scenarios/` as
simulation source. Experiment edits are preview-only until explicit Save-after-preview; run
evidence is derived and never becomes a canonical source artifact.

## Acceptance tests

- Same canonical project, experiment manifest, backend, and seed produce byte-identical
  normalized trace/evidence inputs; a different seed or fault schedule is visible in the diff.
- Nominal, scheduled-fault/recovery, assertion-failure, invalid input, cancellation, timeout,
  restart, and backend-unavailable runs report the correct status and non-zero result where
  required; no missing backend becomes a pass.
- Previewing or editing an experiment does not alter `cell.yaml`, USD, BehaviorTree XML, recipes,
  or scenarios. Explicit Save validates references and writes only the experiment manifest.
- Run evidence includes project/scene/recipe/tree/scenario hashes, selected adapters, requested
  and achieved fidelity, seed, faults, assertion outcomes, logs, limitations, and safety
  disclaimer. Comparison ignores nondeterministic timestamps but preserves event order/results.
- Pause/step/cancel and timeout behavior remains bounded and uses existing service cancellation;
  failed or uncertain process results are not silently retried or relabeled.
- Add focused workbench tests plus existing demo, kitting, simulation, qualification, lint, and
  example checks. Isaac Sim integration is required only on its supported runner.

## Explicit non-goals

- a new physics engine, scenario interpreter, behavior-tree executor, planner, evidence store, or
  production operator UI;
- changing canonical task/recipe/scenario semantics, adding hardware drivers, process-quality
  qualification, or functional-safety enforcement;
- treating experiment success as hardware, production, or safety qualification.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6–7, 10–12, 18–21;
- `docs/architecture.md`, sections 1–8, 12–14;
- `docs/cell-studio.md`, sections 2–5, 11–13;
- `docs/simulation.md`, sections 1–8 and 10–14;
- `docs/simulation-demo.md` and `docs/testing.md`, sections 2, 4, and 10;
- `codex/tasks/TASK-030-studio-deployment-evidence.md`, `TASK-036-executable-release-qualification.md`,
  `TASK-037-simulation-demo-workflow.md`, and `TASK-038-simulation-component-expansion.md`.

## Required checks

- Add and run `make studio-experiment-workbench-check` (or the documented underlying locked
  `uv` command) for deterministic replay, failure/cancel/timeout, unavailable fidelity, and
  comparison;
- run `make lint`, `make test`, `make validate-examples`, `make simulation-demo-check`, and
  `make kitting-simulation-check`;
- run `make studio-simulation-check` and the supported Isaac Sim probe where available; report
  unavailable GPU/Kit execution explicitly;
- run `git diff --check` and verify experiment preview is no-write.

## Safety and fidelity limits

The workbench is for engineering simulation and evidence only. It must not command physical
equipment, bypass safety hardware, authorize jobs, or claim process quality or functional-safety
verification. Requested fidelity is a constraint, not a claim; achieved fidelity comes only from
the observed backend and weakest required adapter.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-044-simulation-experiment-workbench.md` using
`PLANS.md`. Record the manifest/evidence contract, orchestration boundaries, deterministic replay
and comparison rules, cancellation/failure behavior, Save-after-preview, tests, safety/fidelity
limits, and rollback. Update it at each milestone and stop before Task 045.
