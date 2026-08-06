> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-016 — Component browser and placement

## Goal
Browse registry components and place instances into the USD scene and cell graph.

## Deliverables

- filters by kind, capability, support, and simulation level;
- component detail/compatibility view;
- add/remove instance;
- generated immutable instance ID and editable alias;
- selected variant persistence;
- undo/redo integration where practical.

## Acceptance

- placing a component creates linked USD and YAML records;
- removing an instance with connections requires explicit resolution;
- unsupported production component displays a clear warning.
