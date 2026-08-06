> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-006 — Cell compiler and bundle manifest

## Goal
Compile a valid cell project into a deterministic deployment plan without installing it.

## Deliverables

- compiler pipeline matching `docs/architecture.md`;
- target-profile resolution;
- selected component/adapter/package list;
- frozen recipes and task references;
- deterministic manifest JSON;
- SHA-256 bundle ID calculation;
- evidence-policy placeholder that fails closed when production evidence is required.

## Acceptance

- repeated builds of unchanged input produce the same manifest and bundle ID;
- changing a recipe changes the bundle ID;
- production mode rejects simulated-only components;
- no binary/container build is required yet.
