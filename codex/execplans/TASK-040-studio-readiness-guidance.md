# Task 040 — Studio readiness guidance

## Goal

Provide a deterministic, pure Cell Studio readiness service and a thin Kit panel that turns the
canonical project, component, task, recipe, scenario, simulation, calibration, and evidence
preconditions into source-linked engineering guidance. The report must distinguish `pass`,
`blocked`, `advisory`, and `unavailable`, preserve requested versus observed fidelity, and never
claim functional-safety validation or authorize physical operation.

## Scope

Included: `EvaluateStudioReadiness` and immutable report DTOs; the Draft 2020-12 diagnostic report
schema; deterministic checks over existing project/scene, schema, registry/resolver, task, recipe,
scenario, calibration, fidelity, and evidence services; source-linked remediation descriptors;
candidate remediation previews with no filesystem writes; explicit Save-after-preview through the
Task 015/039 transactional paired-artifact boundary; the readiness application/presentation state;
focused tests and a `studio-readiness-check`; documentation of the new panel and limitations.

Explicitly excluded: schema-driven authoring, visual connection/task/recipe canvases, experiment
management, automatic source repair, runtime readiness authority, production authorization,
hardware commissioning, functional-safety enforcement/certification, and Tasks 041–048.

## Current state

The checkout is the clean merged Task 039 baseline at merge `236bbee6458f19cb91536fbb7f7928504a60a073`
with prerequisite commit `e621837` (`task(039): add guided Studio project launcher`) in history.
Task 039 already supplies `ProjectContents`, `ProjectCommandService.inspect/save`, the paired
YAML/USD identity validator, recovery journal transaction, and explicit preview/Save application
commands. `FilesystemComponentRegistry` and `resolve_cell` provide exact component, adapter, port,
capability, and execution-mode resolution. `TaskAuthoringService`, `RecipeAuthoringService`,
`ScenarioEvidenceService`, `SpatialConfigurationService`, and `DeploymentService` expose pure
headless checks used by the existing project service. `scene.py` provides the deterministic USDA /
instance-ID cross-reference validator. `SimulationApplication` already reports backend failures and
fidelity rather than hiding them.

The project currently has no readiness report, readiness schema, remediation candidate service, or
readiness panel. The canonical source artifacts remain `cell.yaml`, the referenced USDA/USD scene,
BehaviorTree.CPP XML, recipe files, calibration files, scenarios, deployment profiles, and evidence;
the readiness report is diagnostic data only.

## Design

`StudioReadinessService` will expose the exact command `EvaluateStudioReadiness` plus snake-case
aliases. It accepts a selected project path or an in-memory `ProjectContents` candidate, requested
fidelity, and an explicit backend capability/fidelity probe. It parses/loads through the existing
schema registry and project service, delegates component/port/capability checks to `resolve_cell`,
delegates task/recipe/scenario/calibration/deployment checks to their existing services, and uses
the existing scene cross-reference validator. Kit code will only pass inputs and render DTOs.

The immutable `StudioReadinessReport` contains a stable project identity, sorted checks, summary,
requested fidelity, observed fidelity, and no wall-clock timestamp. Each `StudioReadinessCheck`
contains a stable `check_id`, category, status, severity, source reference, message, remediation
ID, evidence references, and optional validator link. Finding IDs are derived from stable check
category/rule/source inputs, while report normalization sorts all mappings and sequences. A
malformed or unavailable prerequisite is never downgraded to `pass`; a requested L2/L3 backend that
cannot prove its actual execution is `unavailable`, and L0 is explicitly observed as L0.

The check inventory is deterministic and covers: canonical cell/scene pairing and schema versions;
component manifest/asset/frame and exact registry resolution; typed ports/capabilities; task XML and
plugin resolution; recipe schema/reference/compatibility; scenario availability and requested
fidelity; adapter/backend readiness and actual fidelity; calibration freshness; evidence/source hash
and replay prerequisites; deployment target prerequisites; and a separately labeled modeled-safety
review category. Safety findings explain the independent rated-hardware boundary and are never used
as a software safety claim.

`PreviewStudioReadinessRemediation` returns a `ReadinessCandidatePreview` containing candidate
buffers, source hashes, the linked remediation/check IDs, validation findings, and a save token. It
supports only explicit, bounded candidate transformations supplied by an existing authoring service
or a caller-provided candidate; it never writes a canonical or report file. `SaveStudioReadiness`
requires the current preview token and explicit confirmation, re-evaluates/validates the complete
candidate, and delegates to `ProjectCommandService.save` so the paired YAML/USD transaction and
recovery behavior remain the only write boundary. Any injected replacement failure preserves the
original canonical pair and source hashes.

The report schema is `schemas/studio_readiness_report.schema.json`, Draft 2020-12, and is diagnostic
only. It is not added to the Runtime schema registry or required by Cell Runtime. An explicit
`to_dict`/`to_json` normalization path validates exported reports against this schema.

## Work sequence

1. [x] Record Task 039 baseline, required source documents, scope, and safety/fidelity constraints;
   acceptance: this plan exists before implementation and the preflight state is documented.
2. [x] Add report DTOs, deterministic normalization, schema, and pure delegated check inventory;
   acceptance: nominal, blocked, advisory, malformed, stale, and unavailable inputs produce stable
   source-linked reports with no timestamp and no synthetic higher-fidelity pass.
3. [x] Add remediation preview and explicit Save integration over `ProjectCommandService`;
   acceptance: preview leaves canonical files and hashes unchanged, explicit Save validates the
   full candidate, and transactional failure restores the original pair.
4. [x] Add Studio application/panel wiring, backend-failure display, documentation, and the
   focused readiness probe/Make target;
   acceptance: callbacks delegate only, the panel renders all statuses and safety disclaimer, and
   the focused command covers nominal/blocked/advisory/unavailable/deterministic cases.
5. [ ] Run focused Studio/simulation/qualification/regression checks, inspect the complete diff,
   commit only Task 040, publish a ready PR, wait for required checks, merge, and verify remote
   default-branch ancestry. Do not start Task 041.

## Validation

- `make studio-readiness-check` or the exact locked `uv --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache`
  command body, covering nominal, blocked, advisory, unavailable, stale/malformed/recovery,
  deterministic replay, backend failure, remediation no-write, and transactional Save failure.
- `make lint`, `make test`, and `make validate-examples` or exact Makefile command bodies when GNU
  Make is unavailable; run focused prior Studio checks, simulation demo/kitting checks, and Task
  036 qualification checks applicable to changed interfaces.
- `make kit-extension-check` and the documented Isaac Sim 6 headless readiness/lifecycle probe if
  available; otherwise report the integration as unavailable without substitution.
- `make ros-build` and `make ros-test` if any ROS source changes; no ROS changes are expected.
- `git diff --check`; inspect source hashes before/after remediation preview and after injected Save
  failure; validate the report JSON against the new Draft 2020-12 schema.

## Risks and rollback

The primary risk is duplicating compiler/domain policy in a UI callback or turning diagnostic
availability into an authorization claim. Keep all domain decisions in the pure service and reuse
existing validators/resolvers. Keep the report and candidate DTOs non-canonical; only explicit Save
can reach `ProjectCommandService.save`. The existing recovery journal remains the rollback authority
for paired files. The feature is additive and can be reverted as one task-scoped commit; the report
schema introduces no Runtime migration.

## Progress

- [x] 2026-08-22 — Read AGENTS.md, SYSTEM_SPEC.md, PLANS.md, Task 040, architecture, Cell Studio,
  simulation, testing, Tasks 035/036, and Task 039 implementation/history.
- [x] 2026-08-22 — Confirmed clean isolated checkout, required merge/prerequisite ancestry, and
  created branch `task/040-studio-readiness-guidance`.
- [x] 2026-08-22 — Created this ExecPlan before implementation.
- [x] 2026-08-22 — Implement readiness report/schema and delegated check inventory.
- [x] 2026-08-22 — Implement no-write remediation preview and transactional explicit Save.
- [x] 2026-08-22 — Add presentation/probe/docs and complete local validation/publication.
- [x] 2026-08-22 — Opened ready PR #38; Python 3.12 validation and ROS 2 Jazzy build/test passed.
- [ ] 2026-08-22 — Merge PR #38 and verify remote-main ancestry.

## Decisions

- 2026-08-22 — Use the existing Studio application/backend boundary and `ProjectCommandService`
  transaction rather than introducing a second persistence path.
- 2026-08-22 — Treat all reports and remediation previews as derived diagnostic DTOs; canonical
  project files remain the only source of truth.
- 2026-08-22 — Delegate component/port/capability policy to `FilesystemComponentRegistry` and
  `resolve_cell`, and delegate task/recipe/scenario/calibration/evidence policy to existing pure
  services rather than copying rules into Kit callbacks.
- 2026-08-22 — Represent missing Isaac/GPU/adapter capability as `unavailable`, never a synthetic
  pass; preserve explicit L0 labels and independent functional-safety wording.
- 2026-08-22 — Classify a declared component with no simulation adapter (`resolver.adapter-missing`)
  as a blocking project-configuration finding, while backend/GPU/fidelity availability remains
  `unavailable`.

## Results

Implementation: added `cellforge.studio.readiness.EvaluateStudioReadiness`, immutable report,
check, summary, remediation, preview, backend-probe, and Save DTOs; deterministic check IDs and
normalization; delegated schema/registry/resolver/task/recipe/scenario/calibration/evidence and
deployment checks; explicit L0/L2/L3 fidelity and safety disclaimer handling; no-write candidate
staging; and Save-after-preview through the existing paired YAML/USD transaction. Added the Draft
2020-12 diagnostic schema, Studio application state and panel, backend wiring, focused probe, and
documentation. The report schema is auxiliary and is not loaded as a Cell Runtime canonical
schema.

Validation completed on 2026-08-22:

- `make lint`, `make test`, `make validate-examples`, and `make studio-readiness-check` were
  unavailable because GNU Make is not installed in this Windows environment.
- Replaced those Make wrappers with the exact Makefile command bodies using the parent locked
  Python 3.12 runtime and worktree source paths: Ruff format/check passed; full mypy passed for
  144 source files plus Studio mypy passed for 28 files; full pytest passed (`482 passed,
  2 skipped`); and example validation passed (`10 canonical schemas, 13 component config
  schemas, 36 example YAML documents`). The attempted offline `uv --cache-dir
  C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache sync --locked --all-packages` could not
  complete because the populated cache lacks `hatchling>=1.27` and network access is blocked.
- `studio-readiness-check` body passed with 10 focused tests and the readiness probe covering
  nominal pen/kitting, blocked, advisory, unavailable, stale/malformed, deterministic replay,
  backend failure, no-write preview, explicit confirmation, and injected transaction recovery.
- Task 039 guided launcher regression passed (8 tests plus probe); simulation regression passed
  (18 tests plus probe); kitting simulation passed (6 tests); Task 036 qualification passed
  (10 tests, 1 external Task 027 evidence skip), with the qualification report honestly showing
  L2 unavailable and L0-only evidence.
- The pure Studio extension manifest check passed. Isaac Sim 6 base Kit lifecycle probe passed
  using `C:\IsaacSim\kit\kit.exe` and verified startup, all Cell Studio windows, and clean
  unload. The documented full `isaac-sim.bat` invocation reached extension startup but ended in
  an environment `LLVM ERROR: out of memory`; the lighter base Kit invocation passed. No ROS
  source files changed, so ROS build/test were not applicable.
- `git diff --check` passed after excluding the generated qualification report. The complete
  implementation diff is ready for task-scoped staging and publication.
- PR #38 (`https://github.com/JoaoDias28/cellforge/pull/38`) is ready for review and currently
  reports both required GitHub checks passing; merge and remote-main verification remain the only
  unfinished lifecycle steps.
