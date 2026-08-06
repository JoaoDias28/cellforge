> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-012 — Job gateway and recipe freeze

## Goal
Accept jobs, resolve immutable runtime inputs, and submit them to the supervisor.

## Deliverables

- `RunJob` action server or gateway node design consistent with interfaces;
- idempotency handling;
- recipe/tree/bundle compatibility checks;
- execution-mode rules;
- frozen job record;
- duplicate and restart behavior tests.

## Acceptance

- same idempotency key cannot run twice with conflicting payload;
- unapproved recipe is rejected in production mode;
- simulation mode accepts the tested reference recipe;
- result persists before completion is returned.
