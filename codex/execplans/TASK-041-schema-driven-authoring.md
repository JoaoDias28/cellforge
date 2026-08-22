# Task 041 — schema-driven authoring with advanced source view

## Goal

Provide a pure, schema-driven authoring boundary for supported CellForge cell,
component-configuration, recipe, and scenario documents. The same validated candidate must be
usable by generated forms and advanced YAML/JSON source editing, with deterministic presentation
metadata, explicit ambiguity handling, exact preview diffs, and an explicit Save-after-preview
write boundary.

## Scope

Included: Draft 2020-12 schema form models and renderer; `x-cellforge` presentation annotations;
deterministic defaults, IDs, and project-relative paths; structured schema/source/semantic findings;
form/source candidate merge and exact diff; source format and comment/order preservation rules;
canonical candidate rendering; recipe immutability; scenario seed/fault/fidelity preservation;
paired project Save integration through the existing recovery-journal transaction; focused tests,
documentation, probe, and Make target.

Explicitly excluded: JSON Schema replacement, domain-model rewrites, visual connection or
behavior-tree editors, production approval or physical authorization, safety enforcement, recipe
mutation of released versions, Tasks 042–048, and any new ROS or Isaac runtime behavior.

## Current state

The clean merged Task 040 baseline is `f3e86dc` with prerequisite commits `940b8f1` and `e96f5ba`.
`ProjectContents` retains exact `cell.yaml`/USDA/artifact buffers; `ProjectCommandService.save`
validates candidates and uses the existing paired recovery-journal transaction. Existing component,
spatial, task, recipe, scenario, and readiness services are pure headless boundaries. The domain
`SchemaRegistry` validates registered Draft 2020-12 schemas but does not expose presentation form
metadata or source-preserving authoring candidates. Current canonical schemas contain no
`x-cellforge` UI annotations.

Baseline evidence before implementation: locked offline `uv` environment prepared successfully;
Ruff format/check passed; example validation passed; Studio tests passed (102); domain tests passed
(52). GNU Make is unavailable on this Windows runner, so the exact Make command bodies will be
used and recorded. The default uv cache is inaccessible; the populated
`C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache` is the offline cache used for checks.

## Design

`SchemaAuthoringService` will expose pure command methods and exact aliases
`BuildSchemaForm`, `UpdateSchemaForm`, `PreviewSourceEdit`, `MergeSourceEdit`, and
`SaveAuthoringCandidate`. Public frozen DTOs will include `SchemaFormModel`, field/group metadata,
`AuthoringCandidate`, structured findings, source identity, and a JSON-pointer keyed exact diff.
The renderer consumes the DTO only; it will not contain schema/domain rules.

The form builder recursively interprets Draft 2020-12 structural keywords (`type`, `properties`,
`required`, `items`, `enum`, `const`, defaults, numeric/string/array constraints, `description`,
and `$ref`/local definitions). `x-cellforge` is optional presentation-only metadata with exactly
`label`, `group`, `order`, `unit`, `help`, `advanced`, and `generated`; unknown annotations are
ignored. Unknown validation keywords are reported as structured errors when they are not a known
Draft 2020-12 keyword; no widget can silently accept them. Schema version is resolved exactly and
unsupported versions block authoring.

Defaults come only from a schema default, a single-valued enum/const, or a stable allocator for
an unambiguous ID/path. Allocators use an explicit seed and canonical source context, never a
display-name guess or cross-component inference. Multiple valid interpretations produce a sorted
required-choice record and no implicit value. Generated values are marked in the form model and
candidate provenance.

The candidate stores the source path, encoding, format, schema kind/version, original bytes/text,
form value, source value, canonical value, and SHA-256 hashes. YAML/JSON is parsed without writing;
source edits are merged into the same candidate and run through schema validation plus the existing
domain/semantic validator callback. Exact diffs are deterministic JSON-pointer entries with old/new
values and operation; comments and source order are retained in the unchanged source buffer and a
canonical formatter is preview-only. Save requires a current candidate token and explicit
confirmation, revalidates the complete candidate, refuses unresolved/unsupported/released data,
and delegates paired `cell.yaml`/USDA persistence to `ProjectCommandService.save`. A failed paired
transaction therefore restores prior bytes and hashes.

Supported project targets are cell documents, component config schemas referenced by placed
components, recipe files, and declared scenario files. For project-backed candidates, cell and USDA
buffers remain paired; recipe release status is checked before update; scenario fields including
seed, fault schedule, and requested fidelity are preserved. Canonical output is stable but is never
silently applied during Preview.

## Work sequence

1. [x] 2026-08-22 — Verify Task 040 ancestry, clean isolated worktree, read required guidance,
   create `codex/task-041-schema-driven-authoring`, capture baseline checks, and create this plan.
   Acceptance: plan exists before implementation and baseline evidence is recorded.
2. [x] 2026-08-22 — Add schema authoring DTOs, schema walker, annotation/default/ambiguity policy, validation,
   stable diff, and renderer. Acceptance: synthetic and canonical schemas produce deterministic
   fields/groups/defaults and structured unsupported-keyword findings.
3. [x] 2026-08-22 — Add form/source merge and project/recipe/scenario Save-after-preview integration. Acceptance:
   valid edits round-trip byte-stably, preview hashes do not change, invalid or released candidates
   cannot save, and injected paired-save failure leaves all prior artifacts intact.
4. [x] 2026-08-22 — Add canonical schema annotations, public exports, Studio application/backend wiring where
   needed, authoring documentation, focused tests, and the schema-authoring probe/Make target.
   Acceptance: cell/config/recipe/scenario contracts cover success, invalid input, ambiguity,
   generated values, semantic references, seed/fault/fidelity, backend/UI failure, and renderer
   delegation without domain rules.
5. [ ] Run required and focused locked checks, Kit probe if available, inspect complete diff, commit
   only Task 041, publish a ready PR, wait for every required check, merge when green/mergeable,
   fetch and verify `origin/main` ancestry, and leave this worktree clean. Do not start Task 042.

## Validation

- Exact locked command body for `studio-schema-authoring-check`: focused authoring tests and probe.
- `make lint`, `make test`, and `make validate-examples`, or exact locked `uv --cache-dir
  C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache --offline` command bodies when Make is
  unavailable; run Studio, domain, project, spatial, task/recipe, simulation, guided, readiness,
  and relevant example regressions.
- `git diff --check`; schema meta-validation; byte/hash assertions for preview, explicit Save,
  released recipe immutability, and paired transaction recovery; canonical output stability.
- Run the documented Kit interaction probe if Isaac Sim is available; otherwise report it
  unavailable. No ROS sources are in scope, so ROS checks are only run if implementation changes
  ROS files.

## Risks and rollback

The primary risks are duplicating domain validation in widgets, rewriting comments/order during a
preview, silently choosing ambiguous identifiers, or allowing source edits to bypass recipe,
component, scenario, or paired YAML/USD validation. Keep all policy in the pure authoring service,
reuse registered schemas and existing project/recipe/scenario services, and keep renderer output
presentation-only. The existing `ProjectCommandService` recovery journal remains the only paired
canonical write authority. The task can be rolled back as one branch/commit without a schema
version migration; annotations are ignored by existing validators and therefore backward
compatible.

## Progress

- [x] 2026-08-22 — Read required repository/task/architecture/domain/testing/schema guidance and
  Task 028/029 plus Task 040 implementation/history.
- [x] 2026-08-22 — Confirmed clean worktree at Task 040 merge and prerequisite history; created
  task branch and captured baseline.
- [x] 2026-08-22 — Created this ExecPlan before implementation.
- [x] 2026-08-22 — Implemented pure schema form/candidate/diff services and renderer.
- [x] 2026-08-22 — Integrated validation and explicit Save-after-preview across supported artifacts.
- [x] 2026-08-22 — Added annotations, docs, probe, Make target, and comprehensive tests.
- [x] 2026-08-22 — Completed locked local checks: 501 repository tests passed with two expected
  skips; 121 Studio tests passed; Ruff format/check and mypy (144 domain plus 31 Studio files)
  passed; focused project/spatial/task-recipe/simulation regressions and probes passed; example
  validation passed; and the Isaac Sim Kit interaction probe passed. GNU Make is unavailable, so
  the exact target command bodies were run with the populated offline uv cache.
- [ ] Complete commit, PR/CI/merge, and final ancestry verification.

## Decisions

- 2026-08-22 — Use a new pure Studio service module and existing `ProjectCommandService.save`, not
  widget callbacks or a second persistence path.
- 2026-08-22 — Treat `x-cellforge` as derived presentation metadata; unknown annotations are
  ignored, while unknown validation keywords are surfaced and block Save.
- 2026-08-22 — Allocate only from explicit schema defaults, singleton enum/const, or deterministic
  seed/context; unresolved multiple choices remain visible and unsaveable.
- 2026-08-22 — Preserve original source text/bytes and ordering/comments; canonical formatting is
  a preview artifact, never an implicit write.
- 2026-08-22 — Preserve the engineering/safety boundary: authoring can display safety and
  simulation values but never enforces safety or authorizes physical execution.
- 2026-08-22 — Preserve original bytes for no-op previews; meaningful regenerated output carries a
  warning so comment/order changes are explicit in the reviewed candidate.

## Results

Implementation is complete locally. Focused authoring tests pass (19), the full Studio suite passes
(121), the complete locked repository suite passes (501 with two expected skips), the headless
authoring probe passes, the focused prerequisite regressions pass, example validation passes, and
the Isaac Sim Kit interaction probe passes. GNU Make is unavailable on this Windows runner; the
documented locked uv command bodies were executed with the populated offline cache. CI/PR/merge
evidence, limitations, and the next-task prompt will be recorded here after publication.
