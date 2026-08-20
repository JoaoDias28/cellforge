> Follow `AGENTS.md`. Create an ExecPlan when this task becomes eligible. Do not implement Tasks 037–038 in this task.

# TASK-036 — Executable release qualification

## Goal

Replace the Task 033 synthetic or hard-coded release-qualification success path with actually
executed gates and honest, reproducible evidence for the software and simulation platform.

## Prerequisites

- Task 035 is merged;
- the Task 033 software-side workflow and the current L0/L2 contracts are understood;
- a supported environment is identified for each claimed gate, with unavailable platform gates
  reported as unavailable rather than converted into passes.

## Deliverables

- executable qualification commands that run the gates under test instead of replaying or accepting
  synthetic success events;
- L0 and supported Isaac Sim 6 L2 execution of the same canonical behavior tree and recipe without
  simulator-specific workflow branches;
- the required nominal, fault, cancel, timeout, restart, corrupt-bundle, offline-platform,
  stale-device, and uncertain-process scenarios;
- signed or otherwise integrity-protected qualification evidence containing the command, Git/source
  revision, bundle and component identities, seeds, actual backend/fidelity, logs/reports, gate
  outcomes, and explicit limitations;
- documentation of the supported runner, required dependencies, unavailable-gate behavior, and
  the independent functional-safety and physical-process boundaries.

## Acceptance

- A clean supported run executes every claimed gate and fails non-zero when a gate or evidence
  assertion fails; no hard-coded success result, fictional package, or synthetic event can make a
  release pass.
- Evidence is traceable to observed command output and artifacts, identifies actual L0 versus L2
  execution, records seeds and revisions, and cannot be relabeled across fidelity levels.
- The same tree and recipe are exercised in L0 and L2, or a documented supported-environment
  limitation blocks the L2 claim without producing a false pass.
- All nine scenario categories produce expected outcomes, including bounded cancellation/timeout,
  restart recovery, fail-closed bundle and device handling, offline operation, and explicit
  `OUTCOME_UNKNOWN` for an irreversible uncertain process.
- The qualification report states that simulation is engineering verification only; it does not
  qualify real hardware, process quality, or independent functional safety.
- Runtime, schema, ROS, bundle, and Studio public interfaces remain backward compatible unless a
  separately approved change is required and documented.

## Explicit non-goals

- real-device commissioning or production acceptance;
- functional-safety implementation or certification;
- the one-command demo path (Task 037);
- adding another simulated workflow or component family (Task 038).
