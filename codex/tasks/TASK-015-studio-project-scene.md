> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-015 — Studio project and scene round trip

## Goal
Open, create, save, and validate cell projects with synchronized USD and YAML instance IDs.

## Deliverables

- project create/open/save commands;
- USD stage initialization;
- cross-reference validator;
- transactional save with recovery file;
- dirty-state tracking;
- round-trip tests.

## Acceptance

- open/save of the pen project preserves semantic content;
- interrupted save does not destroy the last valid project;
- missing USD prim or duplicate instance ID appears in validation panel.
