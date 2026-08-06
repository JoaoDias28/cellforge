> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-018 — Isaac simulation bridge and scenario control

## Goal
Run CellForge scenarios against Isaac Sim adapters through ROS 2.

## Deliverables

- simulation start/reset/pause/step control;
- scenario state setup;
- adapter registration for simulated devices;
- fault injection bridge;
- trace capture and assertion evaluation;
- headless execution path for GPU CI.

## Acceptance

- nominal scenario starts from a clean deterministic reset;
- same seed is reproducible within documented tolerances;
- simulation reports unsupported fidelity honestly;
- scenario result is stored as evidence.
