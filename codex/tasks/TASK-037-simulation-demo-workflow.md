> Follow `AGENTS.md`. Create an ExecPlan when this task becomes eligible. Task 036 may proceed in parallel; do not implement Task 038 in this task.

# TASK-037 — Simulation demo workflow

## Goal

Make CellForge demonstrable from a clean supported checkout with one documented L0 command and a
supported Isaac Sim 6 L2 path, both producing observable artifacts that show what actually ran.

## Prerequisites

- Task 035 is merged;
- the existing reference pen project, L0 contracts, and simulation evidence formats are available;
- the supported Isaac Sim 6 path and its environment requirements are recorded without treating an
  unavailable GPU/runtime as a passing result.

## Deliverables

- one stable, documented command that runs the nominal reference simulation at L0 without requiring
  Isaac Sim, ROS discovery, physical hardware, or a cloud service;
- a supported Isaac Sim 6 headless L2 command/path with clear setup, fidelity checks, and honest
  unavailable/failure behavior;
- observable artifacts for each run, including a structured evidence report, trace/event output,
  seed, source/project/scene identities, backend and fidelity, logs, and machine-readable assertions;
- deterministic replay instructions and a troubleshooting/limitations section that distinguishes
  interface evidence, physics evidence, process-quality evidence, hardware evidence, and safety
  evidence.

## Acceptance

- A clean supported environment can run the L0 demo with one command and receive a non-zero result
  for a failed assertion; the command leaves the documented artifacts at a predictable location.
- Repeating the same L0 run with the same seed reproduces the normalized trace and evidence inputs.
- The Isaac Sim 6 path is executable on its supported runner, identifies actual PhysX execution, and
  fails or reports unavailable when its runtime/GPU prerequisites are absent.
- Artifacts expose the exact project, scene, scenario, source revision, seed, selected adapters,
  fidelity, assertion outcomes, and functional-safety disclaimer rather than merely printing a
  human-only success line.
- No demo path authorizes physical operation, claims real-hardware qualification, or implements a
  functional-safety function.

## Explicit non-goals

- replacing executable release qualification (Task 036);
- adding a second simulated robot-cell workflow (Task 038);
- physical process-quality or functional-safety validation.
