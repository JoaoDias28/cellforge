> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-022 — Local operator API and minimal UI

## Goal
Provide a safe local operational interface.

## Deliverables

- status, active job, faults, bundle/recipe identity, and trace-summary endpoints;
- submit/cancel job endpoints with role checks;
- approved recovery-action model;
- minimal local web UI;
- audit events.

## Acceptance

- API cannot call arbitrary ROS services;
- unauthorized maintenance/recovery is rejected;
- operation remains available when platform server is offline;
- all operator actions are auditable.
