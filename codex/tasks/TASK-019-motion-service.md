> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-019 — MoveIt and MTC motion service

## Goal
Expose collision-aware robot motion and staged manipulation behind stable CellForge actions.

## Deliverables

- supported reference robot MoveIt configuration;
- plan-only and plan-and-execute modes;
- named safe poses;
- MTC pick/load/unload task builder;
- planning-scene synchronization contract;
- result/fault mapping;
- tests with fake controller.

## Acceptance

- unreachable and collision cases return stable failures;
- cancellation stops execution request;
- task logic does not directly depend on planner plugin names;
- plan-only works without physical hardware.
