> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-028 — Studio spatial configuration and calibration

## Goal
Let an engineer construct and spatially configure the reference cell without manual YAML or USDA.

## Deliverables
- viewport selection, transforms, mount snapping, and frame/collision visualization;
- schema-driven component configuration and variant editing;
- immutable calibration import/creation, validation, expiry, and component binding;
- payload, reach, mount, configuration, calibration, and paired-scene validation;
- paired transactional save plus undo/redo for all new commands;
- real Kit lifecycle and visual interaction tests.

## Acceptance
- the complete reference cell can be assembled and configured entirely in Studio;
- invalid transforms/configuration/calibration cannot corrupt either canonical artifact;
- reopening produces identical operational identities, transforms, and bindings;
- the actual Isaac Sim 6 UI workflow passes on the supported runner.
