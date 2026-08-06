> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-009 — Contract mock adapters

## Goal
Implement L0 mocks for robot motion, gripper, fixture, vision locator, process machine, and inspection.

## Deliverables

- configurable timing and result behavior;
- ROS actions/services matching canonical interfaces;
- fault injection services or test hooks;
- deterministic state transitions;
- launch file for the complete mock cell.

## Acceptance

- every mock passes the generic adapter contract suite;
- faults can be selected by scenario configuration;
- no mock reports success without publishing coherent state transitions.
