> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Tasks 046–048 in this task.

# TASK-045 — Reusable robot simulation runtime contract

## Goal

Define and implement one reusable robot-model and simulation-adapter contract that can serve the
reference and future cells. The contract must make robot joints, frames, limits, controllers,
collision assets, capabilities, and actual simulation fidelity explicit while keeping MoveIt,
ROS, Isaac Sim, and BehaviorTree.CPP at their existing boundaries.

## Prerequisites

- Task 044 is merged and the experiment workbench can identify actual backend/fidelity and
  replay evidence;
- Tasks 007, 018, 019, 020, 024, 027, 033, 036, and 038 are merged with ROS contracts, motion
  planning, simulation adapters, canonical runtime, and qualification boundaries;
- the existing supported robot component and L0 mock remain backward-compatible.

## Concrete deliverables

- a versioned reusable robot model contract and validator for component packages;
- a simulation adapter interface covering model load, reset, joint/state observation, command
  execution, readiness, cancellation, timeout, deterministic faults, and trace identity;
- adapters for the existing supported robot at the fidelity levels it actually provides, with
  L0 deterministic fallback and a supported Isaac Sim path where available;
- mapping from model frames/joints/limits to MoveIt and typed ROS motion contracts without placing
  sequencing in the adapter;
- deterministic model/scene identity checks, contract tests, failure reporting, and documentation
  that imported or built robots remain simulation-only.

## Public interface and schema decisions

- Add `schemas/robot_simulation_model.schema.json` as a Draft 2020-12 contract referenced by a
  robot `component.yaml`. Required data includes immutable model ID/version, root/base frame,
  ordered joints and limits, link/frame roles, visual/collision asset refs, tool frames,
  controller mapping, supported capabilities, adapter entrypoints, and declared fidelity.
- Add a typed `RobotSimulationAdapter` contract with `load_model`, `reset`, `read_state`,
  `execute_trajectory`, `stop_and_cancel`, `inject_fault`, and `close`; every operation returns
  readiness, timeout/cancellation, stable fault, and evidence metadata. The existing planner/
  behavior-tree ROS interfaces remain the external contract.
- Model identity is content-addressed from canonical model metadata and referenced assets. Joint
  order, frame IDs, limits, and tool frames are immutable within a model version; aliases are
  display-only. No generated value may hide an ambiguous joint/frame mapping.
- Use Isaac Sim `Articulation`/controller/physics APIs and existing OpenUSD composition for Isaac
  backends; use existing MoveIt and ROS interfaces for planning. Do not duplicate a physics,
  kinematics, controller, or USD importer implementation.
- Component `support.level` for this task is `simulated` and `support.simulation_level` is the
  actual tested L0/L1/L2 value. No hardware adapter or production-qualified claim is added.

## Canonical artifacts and Save-after-preview

Robot model metadata must integrate without displacing `cell.yaml` as the operational graph, USD
as the spatial scene, BehaviorTree.CPP XML as the task, `recipes/` as recipe source, or
`scenarios/` as simulation source. Model/configuration changes are staged and previewed first;
explicit Save-after-preview is required before any canonical project or model package write.

## Acceptance tests

- A valid model validates with stable joint/frame/asset identity; missing roots, duplicate joints,
  invalid limits, disconnected links, unknown tool frames, controller mismatch, or bad asset refs
  fail with deterministic findings.
- The same robot model is selectable by the existing motion service and canonical behavior tree
  in L0 and supported Isaac execution without simulator-specific tree/recipe branches.
- L0 commands cover readiness, trajectory success, invalid command, busy, timeout, cancellation,
  communication loss, restart reconciliation, and stable fault mapping. Cancel/timeout evidence is
  bounded and never silently reports success.
- Isaac runs report actual version/backend/PhysX execution and fail or report unavailable when
  prerequisites are absent; CPU/mock output cannot be relabeled as L1/L2.
- Same model/scene/source inputs produce identical normalized identity and replay evidence. A
  model load or adapter failure cannot authorize a run or write a replacement canonical scene.
- Add contract, invalid-model, timeout/cancel, fault, restart, fidelity, and cross-workflow tests;
  keep existing pen/kitting qualification paths green.

## Explicit non-goals

- importing URDF/Xacro/MJCF/USD (Task 046), constructing primitives (Task 047), or adding real
  robot drivers/commissioning;
- replacing MoveIt, Isaac Sim, OpenUSD, ROS action contracts, BehaviorTree.CPP, or safety logic;
- claiming robot accuracy, payload, reach, process quality, hardware support, or safety validation
  from a simulated model.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 6–11, 15, 18–21;
- `docs/architecture.md`, sections 2–8, 9, 12–14;
- `docs/cell-studio.md`, sections 5–6, 11–13;
- `docs/simulation.md`, sections 1–3, 6, 8–14;
- `docs/component-sdk.md`, `docs/testing.md`, and `schemas/component.schema.json`;
- `codex/tasks/TASK-019-motion-service.md`, `TASK-020-pen-physical-sim.md`, and
  `TASK-027-isaac-l2-runtime-integration.md`.

## Required checks

- Add and run `make reusable-robot-simulation-check` (or the documented underlying locked `uv`
  command) for model validation, adapter contract cases, deterministic replay, and fidelity;
- run `make lint`, `make test`, `make validate-examples`, `make motion-service-check`,
  `make pen-physical-sim-check`, and `make kitting-simulation-check`;
- run supported Isaac Sim/PhysX integration checks when available and report external GPU/Kit
  gates unavailable rather than substituting CPU evidence;
- run `git diff --check` and inspect model/scene identity and support-level changes.

## Safety and fidelity limits

This runtime is an engineering simulation adapter. It must not emit safety-rated signals, control
physical robot joints, override interlocks, or claim production qualification. Safety status is
read-only. The achieved fidelity is the actual backend and weakest component; metadata, model
quality, or a UI selection cannot upgrade it.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-045-reusable-robot-simulation-runtime.md` using
`PLANS.md`. Record the contract/schema, existing adapter compatibility, Isaac/MoveIt reuse,
failure/cancellation semantics, fidelity evidence, tests, simulation-only boundary, and rollback.
Update it after each milestone and do not start Task 046.
