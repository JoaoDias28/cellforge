> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-002 — Domain models and schema loader

## Goal
Implement pure Python domain models for component types, instances, ports, connections, cells, recipes, scenarios, validation findings, and bundle manifests.

## Deliverables

- Pydantic models under `cellforge_domain`;
- YAML/JSON loading with source-path-aware errors;
- stable identifier and semantic-version validation;
- structured `ValidationFinding` with code, severity, path, and message;
- unit tests for valid and invalid objects.

## Constraints

- Domain code must not import ROS, Isaac Sim, FastAPI, or vendor SDKs.
- Preserve unknown-file error context without leaking stack traces as user messages.

## Acceptance

- all supplied schema concepts have corresponding models;
- invalid IDs, missing required fields, and duplicate instance IDs are tested;
- public models serialize deterministically.
