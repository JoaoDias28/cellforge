> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-027 — Isaac Sim L2 runtime integration

## Goal
Run the complete canonical runtime against genuine Isaac Sim 6/OpenUSD/PhysX adapters.

## Deliverables
- ROS simulation adapters for robot, gripper, fixture, process handshake, vision/inspection, and modeled safety status;
- supervisor-to-MoveIt/MTC-to-Isaac integration using the same tree and recipe as L0;
- simulator-derived grasp, release, seating, collision, drop, readiness, timeout, and inspection;
- a submitted `RunJob` acceptance probe with no manually fabricated success events;
- supported Isaac Sim 6 GPU runner and replayable L2 evidence.

## Acceptance
- nominal and every required fault scenario completes end-to-end in Isaac Sim 6;
- 100 seeded L2 runs produce a replayable report within declared tolerances;
- event evidence originates from runtime/adapters, not the test harness;
- laser evidence explicitly excludes beam/material and mark-quality qualification;
- unavailable Isaac/GPU execution blocks completion instead of falling back to CPU claims.
