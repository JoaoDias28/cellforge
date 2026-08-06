> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-003 — Schemas and example validation

## Goal
Wire the JSON schemas to the domain loader and validate all example YAML.

## Deliverables

- schema registry keyed by schema version;
- JSON Schema Draft 2020-12 validation;
- YAML-to-JSON validation command;
- cross-file validation for recipe and deployment references;
- tests proving all valid examples pass and intentional fixtures fail;
- `make validate-examples` implementation.

## Acceptance

- every file in `schemas/` parses as valid JSON Schema;
- pen example files validate or failures are corrected consistently in schema and examples;
- error output contains file, data path, schema rule, and human message.
