# Task 027 — Isaac Sim L2 runtime integration

## Goal
Run the canonical pen runtime and its immutable recipe/tree through genuine Isaac Sim 6 OpenUSD/PhysX adapters, then produce replayable L2 evidence from adapter/runtime events rather than a test-harness oracle.

## Scope
Included: L2 ROS adapters for the reference robot, gripper, fixture, laser process handshake, vision/inspection, and modeled safety status; their composition with the existing supervisor, gateway, and MoveIt/MTC services; runtime-submitted scenario execution; seeded replay reporting; and truthful L2 evidence/limitations.

Excluded: hardware drivers, functional-safety enforcement, laser beam/material/mark-quality qualification, Studio authoring work, Task 028+, and relabeling CPU/L0 output as L2.

## Current state
Task 026 is merged on `main` at `b4db142`; all direct prerequisite task commits are in history. Task 018 owns control/evidence services, Task 019 owns MoveIt/MTC services, Task 020 supplies a thin Isaac PhysX pen edge and CPU-only model, Task 024 supplies the canonical runtime tree, and Tasks 025–026 assemble the L0 runtime/bundle. The existing L2 request fails closed in bringup.

The workstation has an NVIDIA RTX 4080, but only unsupported Isaac Sim `5.1.0-rc.19` metadata is present and no Isaac Sim 6 executable is installed. `make` is not available in the current PowerShell environment. Neither limitation may be hidden or substituted by CPU evidence.

## Design
Adapters will be real ROS capability providers backed by Isaac Sim 6 state and sensor/PhysX observations. The canonical `RunJob` request, frozen recipe, and existing behavior tree remain unchanged. The adapter layer owns simulator I/O and emits canonical state/events; the scenario runner only configures, submits, injects declared faults, and evaluates captured evidence. MoveIt/MTC remains the planner/manipulator service, while simulator-derived collision, grasp, seating, drop, readiness, timeout, and inspection outcomes are mapped to stable contract failures.

L2 reports must identify the Isaac version, GPU, scene/cell/scenario identities, adapter evidence origin, exact seeds, final results, and the laser/process limitations. Any missing Isaac 6/GPU execution is a failing availability condition and blocks task completion/publication; deterministic non-Kit tests can validate boundary logic but are not L2 evidence.

## Work sequence
1. Inspect prerequisite runtime, simulation, motion, and bundle interfaces; acceptance: every existing contract and fault boundary needed by the L2 composition is identified.
2. Add the L2 adapter/runtime composition and scenario/evidence contract; acceptance: unit tests prove no fabricated runtime success, stable simulator-derived results, cancellation/timeout, and failure mappings.
3. Add the supported Isaac Sim 6 GPU runner and replayable 100-seed report path; acceptance: the runner refuses unsupported Isaac versions and CPU-only claims.
4. Run Python, ROS, and documented Isaac acceptance checks; acceptance: all available checks are green and Isaac 6 execution produces the required report.
5. Inspect the scoped diff, update this plan with results, commit, publish, review, and merge only after the required checks and Isaac acceptance are green.

## Validation
- `make lint`
- `make test`
- `make validate-examples`
- `make ros-build`
- `make ros-test`
- Task 027 deterministic adapter/runtime tests and 100-seed replay report
- Supported Isaac Sim 6 headless GPU runner executing nominal and every required fault scenario through `RunJob`

## Risks and rollback
Isaac Kit/ROS APIs vary by version; the runner must require Isaac Sim 6 and reject unsupported releases. Adapter state must never be invented by the test harness. Simulator readiness remains ordinary engineering status, not a safety function. The change will be additive and can be reverted as one task-scoped commit without schema migration.

## Progress
- [x] 2026-08-12 — Verified clean `main`, Task 026 merge, direct-prerequisite history, task branch, and workstation Isaac/GPU state.
- [x] 2026-08-12 — Established the Python baseline and inspected existing runtime boundaries.
- [x] 2026-08-13 — Implemented L2 runtime composition, canonical bundle selection, Kit-hosted ROS adapters, MoveIt/MTC handoff, RunJob acceptance coverage for nominal/drop/seating/collision, and GPU-only seeded evidence runner.
- [ ] 2026-08-13 — Execute supported Isaac Sim 6 GPU acceptance and replayable evidence (blocked: no Isaac Sim 6 runner; skipped at user request).
- [ ] 2026-08-13 — Created local commit `6417e11`; publication, review, and merge remain blocked pending the required Isaac Sim 6/GPU acceptance and the user's request not to run checks.

## Decisions
- 2026-08-12 — Treat Isaac Sim 6 execution as a non-negotiable acceptance requirement: neither the installed 5.1 release metadata nor the CPU physical model can qualify Task 027.
- 2026-08-12 — Preserve the existing canonical tree/recipe and public `RunJob` contract; L2 behavior is selected through adapters and runtime configuration, not a simulator-specific task tree.

## Results
Implemented the immutable L2 bundle profile, strict L2 adapter selection, Kit-hosted ROS adapters,
OpenUSD/PhysX-derived observation state, MoveIt/MTC adapter handoff, the public `RunJob` acceptance
client for the nominal/drop/seating/collision scenarios, and a GPU-only 100-seed replayable report
runner. The modeled laser evidence explicitly excludes beam/material interaction and mark-quality
qualification; modeled safety status remains read-only and non-safety-rated.

At the user's request, no checks or Isaac acceptance commands were run after this implementation.
The required L2 acceptance remains unavailable: this workstation exposes an RTX 4080, but
`C:\\isaacsim\\VERSION` is `5.1.0-rc.19` and there is no supported Isaac Sim 6 installation or
configured GPU runner. This blocks task qualification, publication, and merge; CPU/mock output is
not substituted for L2 evidence.

### Qualification update — 2026-08-13

The former availability statement is superseded. Qualification ran on Isaac Sim
`6.0.1-rc.7+release.42383.32955d8d.gl` with an NVIDIA GeForce RTX 4080. The GPU probe generated
`actual_physx_executed: true`, 100/100 successful seeded runs, zero failures, and all three PhysX
fault scenarios. The canonical `/cell/run_job` acceptance passed nominal, dropped-pen,
failed-seating, and collision scenarios through live Kit-hosted adapters and ROS runtime services.
Each scenario uses a fresh real runtime because declared fault scenarios correctly end in
`RECOVERABLE_FAULT`; event evidence is runtime/adapter-originated.

Ruff formatting/lint and strict mypy passed. The full Python suite passed 358 tests with one
Windows symlink-privilege skip; 18 focused L2 tests and canonical example validation passed. The
CPU 100-seed report passed but remains non-L2 contract evidence. The Windows ROS build passed for
11 packages; the final ROS suite passed 110 tests with zero errors, failures, or skips. `make` is
unavailable on this host, so its exact command bodies were run with `uv` and the documented Windows
ROS scripts. No L0/CPU evidence was relabeled as L2. Laser/process and safety limitations remain
unchanged: no beam/material or mark-quality claim, and modeled safety is read-only/non-rated.
