# ADR 0004: Use BehaviorTree.CPP for task orchestration

## Status
Accepted.

## Decision
Use a centralized BehaviorTree.CPP ROS 2 coordinator for cell process logic. Capability providers remain service-oriented nodes.

## Rationale
Tasks require modular composition, asynchronous actions, retries, recovery branches, monitoring, and editor-friendly XML.

## Consequences
Business sequence logic does not belong in device adapters. Behavior-tree plugins require stable contracts and tests.
