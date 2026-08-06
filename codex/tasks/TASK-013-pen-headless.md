> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-013 — Headless pen workflow and scenarios

## Goal
Run the reference behavior tree entirely against mocks.

## Deliverables

- implemented initial behavior-tree nodes;
- pen tree port mappings;
- scenario runner without Isaac Sim;
- nominal and ten required scenarios from `docs/testing.md`;
- JUnit and JSON reports;
- golden normalized traces.

## Acceptance

- all scenarios pass deterministically;
- replaying a failing seed reproduces the same event sequence;
- safety-unhealthy scenario performs no process command;
- uncertain process outcome does not automatically retry.
