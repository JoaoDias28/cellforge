> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-011 — BehaviorTree.CPP supervisor

## Goal
Execute versioned behavior trees and call ROS capability providers.

## Deliverables

- centralized supervisor node;
- plugin registration for initial conditions/actions;
- asynchronous ROS action wrappers;
- timeout, retry, and cancellation behavior;
- top-level cell/job state transitions;
- XML and port validation before execution;
- event emission for node transitions.

## Acceptance

- a simple mock workflow succeeds;
- cancellation stops active action and returns a defined result;
- an unknown node or missing blackboard input fails before job execution;
- device calls do not block the tree tick thread.
