> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-020 — Simulated pen manipulation

## Goal
Implement the L2 physical simulation of the pen cell.

## Deliverables

- robot, gripper, pen, input carrier, fixture, laser enclosure, and inspection camera scene assets or approved placeholders;
- product spawning and bounded pose randomization;
- grasp/attachment simulation;
- fixture seating signal;
- MoveIt/MTC integration;
- collision and cycle tests.

## Acceptance

- nominal pick/load/process-safe-pose/unload completes;
- dropped pen and failed seating faults are detected;
- 100 seeded runs produce a report with failures reproducible by seed;
- limitations of laser/process physics are documented.
