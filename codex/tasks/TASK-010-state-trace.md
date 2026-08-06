> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-010 — State aggregator and trace recorder

## Goal
Create canonical cell state and durable structured event recording.

## Deliverables

- state aggregator node;
- stale-device detection;
- event sequence numbering;
- local durable event store interface with SQLite implementation for MVP;
- trace query utility;
- tests for ordering, restart, and device timeout.

## Acceptance

- cell readiness reflects required device and safety state;
- events survive process restart;
- every command can be correlated to job and trace IDs.
