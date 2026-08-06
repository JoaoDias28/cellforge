# Task 003 schemas and example validation

## Goal
Wire the repository JSON Schemas into the pure `cellforge_domain` loader so that YAML and JSON
documents receive Draft 2020-12 validation, and provide a deterministic command that validates the
complete pen-engraving example including recipe and deployment references.

## Scope
Included: a versioned schema registry, Draft 2020-12 schema and instance validation, structured
source-aware findings, recipe/deployment cross-file checks, intentional invalid fixtures, tests,
documentation, dependency metadata, and `make validate-examples`.

Excluded: the Task 004 `cellforge` CLI, component registry/capability resolution from Task 005,
USD spatial validation, ROS/Isaac Sim integration, deployment compilation, production authorization,
and any implementation of functional-safety logic.

## Current state
Task 002 is present as commit `dede63e8ce768809f230e672cc1beece974e0ccc` and supplies strict
Pydantic models plus source-aware YAML/JSON loading. The five schemas identify Draft 2020-12 and
version `0.1.0`, but no runtime currently loads them. `make validate-examples` is an intentional
Task 003 failure. The clean checkout was branched to `task/003-schemas-validation`.

Baseline evidence on 2026-08-06: Ruff format, Ruff lint, mypy, and 34 pytest tests pass when run
directly from `.venv`. GNU Make is unavailable on this Windows host, so all Make targets are also
verified through their direct underlying commands.

## Design
`SchemaRegistry` loads schemas from an explicit directory, verifies each with
`Draft202012Validator.check_schema`, and keys entries by document kind plus the declared
`schema_version` constant. Explicit roots keep the domain package independent of repository layout
and make schema selection deterministic.

`load_document` gains an optional registry and document-kind argument. When supplied it parses YAML
or JSON to JSON-compatible data, selects the schema using the document's version, emits all sorted
schema failures as `ValidationFinding` values, and only then constructs the Pydantic model. Existing
callers remain backward compatible.

The example-validation module discovers the supported YAML documents, validates them through the
domain loader, then checks each cell recipe binding and deployment-profile path. Recipe bindings
must resolve to the registered recipe schema and the referenced recipe must declare compatibility
with the cell UUID. Each deployment profile must resolve and validate. Findings include source file,
JSON Pointer data path, schema keyword/rule in the stable code, and a human-readable message.

The `jsonschema` 4.x dependency is used for standards-conformant Draft 2020-12 behavior. Its MIT
license, maintenance status, reason, and removal path are documented in the package README.
Modeled safety fields remain data for review/refusal decisions only and do not enforce safety.

## Work sequence
1. Add and document the Draft 2020-12 validation dependency; regenerate the lock file.
2. Implement the schema registry, schema-aware loader path, finding formatter, and example command.
3. Align schemas/examples only where validation exposes a documented inconsistency.
4. Add valid-example, invalid-fixture, registry, error-contract, and cross-file tests.
5. Run acceptance and regression checks, inspect/stage only Task 003, commit, and verify clean state.

## Validation
- `make lint` or the exact Ruff/mypy commands from the Makefile when Make is unavailable.
- `make test` or `.venv/Scripts/pytest.exe` when Make is unavailable.
- `make validate-examples` or its exact `uv run --frozen` command when Make is unavailable.
- Direct module tests that all `schemas/*.json` pass Draft 2020-12 meta-schema validation.
- Intentional fixtures must fail with file, JSON Pointer, schema rule, and message.
- `git diff --check`, `git diff --cached --check`, final clean `git status --short`, and verified log.

## Risks and rollback
Schema/Pydantic drift could accept different documents; contract tests validate every example through
both layers. Cross-file paths could accidentally be interpreted relative to the process; all paths
resolve relative to the referencing file. New validation is opt-in for existing `load_document`
callers, preserving Task 002 behavior. Reverting the single Task 003 commit removes the dependency,
registry, command, fixtures, and Make target together.

## Progress
- [x] 2026-08-06 — repository gate, prerequisite verification, document review, branch, and baseline.
- [ ] 2026-08-06 — dependency and validation implementation.
- [ ] 2026-08-06 — tests and valid example pass.
- [ ] 2026-08-06 — final checks, Task 003 commit, and clean-tree verification.

## Decisions
- 2026-08-06 — Keep schema paths explicit instead of embedding repository-relative assumptions in
  `cellforge_domain`.
- 2026-08-06 — Key schemas by `(document kind, schema version)` because all document families share
  version `0.1.0`; a version-only map would collide.
- 2026-08-06 — Do not add production/safety authorization checks; schema validation cannot substitute
  for approved recipes, deterministic runtime policy, or independent rated safety hardware.

## Results
Implemented a five-schema Draft 2020-12 registry keyed by document kind and schema version,
schema-aware YAML/JSON domain loading, deterministic findings, and a repository example-validation
command. Cross-file checks cover recipe schema/document references, recipe-to-cell compatibility,
and deployment profiles. Six component configuration schemas are also meta-schema checked.

The direct equivalents of `make lint`, `make test`, and `make validate-examples` pass: 72 files are
formatted, Ruff reports no issues, mypy reports no issues in 13 files, all 40 pytest tests pass, and
the validator accepts 5 canonical schemas, 6 config schemas, and 11 YAML documents. GNU Make itself
is unavailable on this Windows host. No ROS, Isaac Sim, production control, or functional-safety
logic changed.
