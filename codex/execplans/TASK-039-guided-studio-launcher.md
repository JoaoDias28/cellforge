# Task 039 — Guided Studio launcher and deterministic project flow

## Goal

Provide a pure, deterministic Create/Open/Review/Save/Cancel application-service flow for
Cell Studio. Engineers can preview a blank or supported example project without filesystem
mutation, resolve only explicit choices, and persist a validated canonical project only after an
explicit confirmation.

## Scope

Included: template descriptors for the blank, pen, and kitting examples; deterministic request
allocation; preview DTOs and versioned diagnostics schema; structured ambiguity and validation
failures; application-service commands; explicit transactional Save using the Task 015 paired
YAML/USD recovery boundary; thin Studio wiring; documentation and focused tests.

Excluded: readiness guidance (Task 040), schema-driven forms, connections/task/recipe/experiment
authoring, robot import or generation, production deployment, hardware control, and safety logic.

## Current state

The checkout is the merged Task 038 baseline. The planning merge `19d8906238c95da10f5724b3264bcdd0cdb52761`
is in history, the worktree is clean, and Task 038 is represented by the merged simulation
component expansion commits. Task 015 provides `ProjectCommandService` with exact in-memory
`ProjectContents`, paired YAML/USD cross-reference validation, dirty-state-compatible buffers,
and a journaled two-file replacement with rollback. Task 016 provides linked component IDs and
aliases, while the existing `cellforge.studio` application and Kit extension are thin callers
around pure services. The supported canonical source examples are `examples/pen_engraving` and
`examples/kitting`; the repository currently has no guided launcher or preview schema.

## Design

`GuidedStudioService` will own immutable template descriptors and an in-memory draft registry.
The public request/response DTOs will use stable string codes and tuples so results are
deterministic and straightforward to serialize. `CreateProject` allocates a draft from a
`CreateProjectRequest`; `PreviewProject` recomputes the same candidate from the stored request
and returns `ProjectPreview`; `OpenProject` inspects an existing project through
`ProjectCommandService`; `ConfirmProjectSave` validates the preview and delegates the candidate
to the existing `save` transaction; `CancelProjectDraft` only removes the in-memory draft.

Templates are read-only source inventories. A blank template is generated from canonical
starter artifacts with explicit simulation/development mode; pen and kitting templates copy
their complete canonical source trees into the candidate. Paths are project-relative, contained
under the requested destination, and listed in the preview. IDs are allocated from a stable
seed and template/request namespace, never from display names; the display name is an alias only.
If an existing destination, duplicate requested ID, invalid schema, missing template/source, or
ambiguous choice is detected, the preview contains structured findings/required choices and
`can_save` is false. No default is selected when a choice is not unambiguous.

The preview is derived DTO data, not a canonical artifact. Candidate bytes are held in memory,
hashed with SHA-256, and never written by Create/Preview/Open/Cancel. Save requires an explicit
confirmation token tied to the current preview hash and destination, revalidates the candidate
with the domain/project service, stages all canonical files, and uses the existing paired
transaction/recovery journal. Reopening uses the normal project service and must reproduce the
allocated IDs and hashes. Safety fields remain modeled/read-only; projects start in simulation or
development mode and the launcher never authorizes physical operation.

## Work sequence

1. [x] Record prerequisite baseline and create this ExecPlan; acceptance: required files/history
   are read, clean preflight is recorded, and no implementation is changed before this plan.
2. [x] Add the preview schema, DTOs, template inventory, deterministic allocator, and pure
   candidate validation; acceptance: blank/pen/kitting previews are deterministic and invalid,
   ambiguous, escaping, and collision inputs return structured non-saveable findings.
3. [x] Add application-service command integration and explicit Save/Cancel/reopen behavior;
   acceptance: preview has no writes, explicit Save creates a valid project through the paired
   transaction, and injected replacement failure restores the original pair with a journal.
4. [x] Add thin Kit/application presentation wiring, focused acceptance probe, docs, and Make
   target; acceptance: callbacks only delegate, preview diagnostics are version-validated, and
   the guided result opens in the existing validator/simulation path.
5. [ ] Run focused, regression, schema, Studio, and Isaac checks; inspect/stage only Task 039,
   commit, publish a ready PR, wait for green required checks, merge, and verify the remote
   default branch. Do not start Task 040.

## Validation

- Focused `make studio-guided-launcher-check` or exact locked `uv` command body.
- `make lint`, `make test`, and `make validate-examples` (or exact underlying commands when Make
  is unavailable), plus existing Studio/Task 015/016 checks.
- `make kit-extension-check` and the documented Isaac Sim 6 headless launcher probe when the
  installed environment supports them; report unavailable integration honestly.
- Preview tests compare bytes, IDs, paths, defaults, source hashes, dirty state, and filesystem
  snapshots before/after. Save tests cover nominal, invalid, ambiguity, cancellation,
  destination conflict, and injected transactional replacement failure.
- `git diff --check`, complete diff/source inspection, staged checks, post-commit state, PR CI,
  mergeability, and origin/default-branch ancestry.

## Risks and rollback

The primary risk is treating generated preview data as a new source of truth or silently choosing
an unsafe/ambiguous component, recipe, scenario, or physical target. Keep canonical artifacts as
the only persisted source and require explicit choices. The existing Task 015 recovery journal
remains the rollback authority for paired files; a failed replacement must not report success or
leave mismatched YAML/USD. The feature is additive and can be reverted as a single task commit;
the preview schema is diagnostic and introduces no runtime or persistent-data migration.

## Progress

- [x] 2026-08-22 — Read AGENTS.md, SYSTEM_SPEC.md, PLANS.md, Task 039, relevant Studio/domain
  documentation, Task 015/016 contracts and ExecPlans, Task 038 plan, and prerequisite history.
- [x] 2026-08-22 — Confirm clean isolated checkout, planning merge ancestry, and Task 038
  prerequisite history; create this plan before implementation.
- [x] 2026-08-22 — Implement deterministic guided preview and structured failure contracts,
  including the diagnostic Draft 2020-12 preview schema, blank/pen/kitting templates, stable
  seeded IDs, hashes, findings, required choices, and no-write previews.
- [x] 2026-08-22 — Integrate explicit application-service Save/Cancel/Open behavior and tests,
  including paired YAML/USD validation, recovery-journal persistence, failure injection, and
  preservation of an existing dirty Studio buffer during preview.
- [x] 2026-08-22 — Add presentation/probe/docs/Make integration and run validation matrix,
  including lazy Kit bootstrap imports and the kitting project's local schema fallback.
- [ ] 2026-08-22 — Commit, publish, pass CI, merge, and verify the default branch.

## Decisions

- 2026-08-22 — Extend the existing Studio application-service boundary rather than putting
  allocation or validation in Kit callbacks; this preserves headless testing and dependency
  direction.
- 2026-08-22 — Reuse Task 015's paired save/recovery implementation for final persistence and
  keep previews entirely in memory; no autosave or hidden normalization is allowed.
- 2026-08-22 — Treat example templates as immutable source inventories and use stable seeded
  allocation for IDs/paths; display names and aliases never become persistence keys.
- 2026-08-22 — Mark all created projects simulation/development-only and retain modeled safety
  dependencies as read-only information; no rated safety behavior is implemented.

## Results

Implementation validation is green on the final pre-commit tree: the repository suite passes
with 471 passed, 2 documented skips, and one Starlette/httpx deprecation warning; the focused
guided suite passes 8 tests; the deterministic guided probe, extension manifest probe, Task 015
scene probe, Task 016 placement probe, and six kitting simulation tests pass. Ruff format/check,
core mypy (144 files), Studio mypy (27 files), and example validation (10 canonical schemas, 13
component schemas, 36 YAML examples) pass. `make` is unavailable in the managed Windows shell;
the exact locked offline `uv --cache-dir C:\\Users\\j4nec\\AppData\\Local\\Temp\\cellforge-uv-cache`
sync and command bodies were run instead. The Isaac Sim 6.0.1-rc.7 headless lifecycle probe on
the RTX 4080 exits 0 and reports clean load/create/unload assertions; Kit emits a non-fatal
shutdown lingering-reference warning. Commit, PR, CI, merge, and remote-default-branch
verification remain the final milestone.
