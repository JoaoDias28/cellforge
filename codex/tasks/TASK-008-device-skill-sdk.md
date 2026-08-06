> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-008 — Device and skill SDK

## Goal
Provide reusable ROS 2 base classes and contract-test helpers for device adapters and skills.

## Deliverables

- canonical state publisher helper;
- command/trace ID utilities;
- timeout/cancellation helpers;
- stable result/fault object;
- lifecycle/readiness pattern documentation;
- generic adapter contract test suite.

## Acceptance

- a sample fake adapter can pass the contract suite;
- tests cover not-ready rejection, cancellation, timeout, fault mapping, and restart state;
- SDK does not hide communication uncertainty.
