> Follow `AGENTS.md`. Create the required ExecPlan before implementation. Do not implement Tasks 042–048 in this task.

# TASK-041 — Schema-driven authoring with advanced source view

## Goal

Let engineers author supported cell, component-configuration, recipe, and scenario data through
forms generated from machine-readable schemas while retaining an honest advanced YAML/JSON source
view. Forms must accelerate deterministic authoring without hiding or inventing canonical data.

## Prerequisites

- Task 040 is merged and readiness can report schema and source problems;
- Tasks 002, 003, 015, 016, 018, 028, and 029 are merged with the current Draft 2020-12 schemas,
  project services, recipe services, and canonical artifact validators;
- the existing canonical `cell.yaml`, USD scene, BehaviorTree.CPP XML, recipe YAML, and scenario
  YAML formats remain backward-compatible unless a separately reviewed schema migration is added.

## Concrete deliverables

- a reusable schema-form application service and renderer for existing CellForge schemas;
- field labels, groups, ordering, units, ranges, enum presentation, descriptions, and advanced
  visibility derived from non-semantic UI annotations;
- deterministic ID/path/default generation for unambiguous fields, with explicit required-choice
  controls for ambiguous values;
- an advanced source view that parses, validates, previews, and shows a structured diff against
  the form candidate without bypassing domain validation;
- form/source round-trip tests for cell components and connections, component config, recipes,
  and scenarios, including invalid and unsupported schema features;
- explicit Save-after-preview for every canonical write and documentation for schema authors.

## Public interface and schema decisions

- Add a pure `BuildSchemaForm`, `UpdateSchemaForm`, `PreviewSourceEdit`, `MergeSourceEdit`, and
  `SaveAuthoringCandidate` application-service contract. The service returns `SchemaFormModel`,
  `AuthoringCandidate`, and structured validation findings; widgets do not implement schema rules.
- Continue using JSON Schema Draft 2020-12. Optional `x-cellforge` annotations are presentation
  metadata only: `label`, `group`, `order`, `unit`, `help`, `advanced`, and `generated`.
  Unknown annotations are ignored; unknown validation keywords are reported rather than silently
  accepted.
- The source view edits the same candidate as the form. It must identify the source path,
  encoding, schema version, parse errors, semantic findings, and exact diff. It may offer a
  canonical formatter only as a preview; it must not rewrite comments or ordering invisibly.
- Defaults may come from `default`, a single-valued enum/const, or a stable allocator for an
  unambiguous ID/path. No display-name guessing, cross-component inference, or silent default
  may satisfy an ambiguous required value.
- Form layout metadata is derived/non-canonical. The operational graph stays in `cell.yaml`,
  spatial data in USD, task orchestration in BehaviorTree.CPP XML, recipes in `recipes/`, and
  simulation definitions in `scenarios/`. Released recipes remain immutable.

## Canonical artifacts and Save-after-preview

Forms and source view preserve `cell.yaml` as the operational graph, USD as the spatial scene,
BehaviorTree.CPP XML as the task source, `recipes/` as recipe source, and `scenarios/` as
simulation source. All form/source changes are candidates until explicit Save-after-preview.

## Acceptance tests

- Existing cell, component config, recipe, and scenario schemas render usable forms with the
  expected required/optional fields, units, ranges, enum values, and advanced sections.
- Valid form edits and valid source edits produce equivalent validated candidates and stable
  canonical output; same inputs generate byte-identical IDs, paths, and defaults.
- Invalid types, ranges, enums, references, schema versions, unknown required keywords, and
  malformed YAML/JSON return structured findings and block Save.
- A required field with multiple possible interpretations remains unresolved until the user
  chooses; a single valid default is generated and visibly identified as generated.
- Form-to-source and source-to-form edits are preview-only. Explicit Save updates the intended
  canonical file, and paired `cell.yaml`/USD changes use the existing transaction and recovery
  behavior; a failed Save leaves all prior artifacts intact.
- Released recipe versions cannot be edited in place; a new draft/version is required. Scenarios
  retain explicit seed/fault/fidelity fields and are not replaced by UI-only state.
- Add success, invalid-input, ambiguity, source-parse, Save-failure, and round-trip tests; keep
  the existing Studio, schema, and example checks green.

## Explicit non-goals

- replacing JSON Schema, Pydantic, the CLI validator, or source control;
- adding a visual connection or behavior-tree runtime, auto-approving recipes, or editing
  immutable released data;
- inferring safety requirements, component compatibility, or process limits from labels;
- arbitrary CAD editing, robot import/build, physical operation, or safety enforcement.

## Relevant documentation

- `SYSTEM_SPEC.md`, sections 3, 4, 6–12, 15, 17, and 19;
- `docs/architecture.md`, sections 3–8 and 14;
- `docs/cell-studio.md`, sections 2–5, 8–13;
- `docs/domain-model.md`, `schemas/cell.schema.json`, `schemas/component.schema.json`, and
  the recipe/scenario schemas;
- `docs/testing.md`, sections 1, 2, 6, and 10;
- `codex/tasks/TASK-028-studio-spatial-configuration.md` and `TASK-029-studio-task-recipe-authoring.md`.

## Required checks

- Add and run `make studio-schema-authoring-check` (or its documented underlying locked `uv`
  command) for form/source round trips, invalid data, ambiguity, and Save failure;
- run `make lint`, `make test`, and `make validate-examples`;
- run focused Studio project, spatial, task/recipe, simulation, and example checks; run the Kit
  interaction probe when available;
- run `git diff --check` and verify released recipe files and canonical source hashes are not
  changed by preview.

## Safety and fidelity limits

Forms and source views are engineering authoring tools. They may display safety fields and
simulation limits but cannot create a safety function, override an unhealthy interlock, authorize
physical execution, or promote a recipe/component to production. A schema value does not raise
the actual simulation fidelity of an adapter.

Any imported or primitive-built robot introduced by later tasks remains simulation-only, and
functional safety remains independent of CellForge software and simulation.

## Required ExecPlan

Before editing, create `codex/execplans/TASK-041-schema-driven-authoring.md` using `PLANS.md`.
Record the schema annotation contract, form/source candidate model, default allocator, migration
and compatibility policy, Save-after-preview transaction, tests, safety/fidelity limits, and
rollback. Update it at each milestone and do not start Task 042.
