> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-024 — Canonical pen runtime

## Goal
Execute the canonical pen behavior tree through the production BehaviorTree.CPP supervisor.

## Deliverables
- `cellforge_pen_bt_nodes` BehaviorTree.CPP plugin package implementing every canonical pen leaf;
- typed ROS action/service calls with cancellation, timeouts, stable failures, and uncertainty;
- immutable bundle-declared plugin loading and machine-readable node/port manifests;
- compiler validation of node types, ports, blackboard mappings, and plugin packages;
- canonical `examples/pen_engraving/behavior_tree.xml` execution without a simulator-specific tree;
- the Python L0 executor retained only as a deterministic regression oracle.

## Acceptance
- nominal and all ten canonical fault scenarios run through the C++ supervisor;
- safety-unhealthy performs no process command;
- cancellation reaches active actions and uncertain process outcomes are not retried;
- unknown nodes, ports, mappings, and undeclared plugins fail compilation;
- the runtime and oracle normalized traces agree on required ordering and outcomes.
