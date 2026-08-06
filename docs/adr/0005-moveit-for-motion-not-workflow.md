# ADR 0005: Use MoveIt/MTC for motion and manipulation, not full workflow

## Status
Accepted.

## Decision
MoveIt 2 plans collision-aware motion. MoveIt Task Constructor handles multi-stage manipulation. The behavior tree remains responsible for production sequencing.

## Rationale
This keeps planning concerns separate from machine workflow and fault recovery.

## Consequences
Motion services expose stable actions to the supervisor and hide planner-specific details.
