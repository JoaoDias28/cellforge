> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-029 — Studio task and recipe authoring

## Goal
Author valid BehaviorTree.CPP tasks and immutable recipe versions without editing source files.

## Deliverables
- graph editor driven by installed plugin node/port manifests;
- canonical BehaviorTree.CPP XML plus non-runtime layout metadata;
- typed port mapping, decorators, capability resolution, and compiler-equivalent validation;
- schema-driven recipe forms, units/ranges, diffs, lifecycle, versioning, and compatibility;
- immutable released versions and no Studio-only production approval path.

## Acceptance
- Studio creates, edits, round-trips, validates, and simulates the canonical pen task;
- a new recipe version is created without mutating its predecessor;
- invalid ports, capabilities, parameters, and lifecycle changes are refused;
- saved XML compiles and executes through the Task 024 supervisor.
