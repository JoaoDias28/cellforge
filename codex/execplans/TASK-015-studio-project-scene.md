# Task 015 Studio project and scene round trip

## Goal
Cell Studio can explicitly create, open, validate, edit in memory, and save CellForge projects while preserving `cell.yaml` as the operational source of truth and the USD stage as the spatial source of truth. Both artifacts share immutable component instance IDs, validate together, and survive a failed two-file save without losing the last valid on-disk project.

## Scope
Included: pure application-service project commands, USDA stage initialization and inspection, YAML/USD instance cross-reference validation, dirty-state tracking, transactional `cell.yaml` plus scene save with a recovery journal, thin Kit callbacks, documentation, deterministic headless tests, and the Task 015 acceptance probe.

Excluded: component browsing or placement (Task 016), connection authoring (Task 017), simulation control (Task 018), binary USD authoring without an available OpenUSD runtime, runtime safety enforcement, and any production dependency on Cell Studio or Isaac Sim.

## Current state
Task 003 schema/model validation (`ff6fe84`) and Task 014's extension shell (`2ac6621`, completion `5324dcf`) are merged ancestors of `main`. Task 014 exposes read-only project inspection through a pure `StudioApplication` and a CLI-backed adapter; Kit callbacks contain no validation rules. Task 004 already creates projects transactionally as directory trees, but its starter USD prim does not yet carry the component instance ID. The pen project has matching YAML prim paths but no USD-authored instance metadata. The existing compiler checks only USDA root presence and duplicate YAML prim assignments.

Pre-edit checks pass through the exact Makefile command bodies: Ruff format/check, both mypy scopes, 221 pytest tests, canonical example validation, 9 Studio tests, and extension manifest verification. GNU Make itself is unavailable on this Windows host.

## Design
`ProjectCommandService` is the filesystem/application boundary used by the backend. `open` delegates schema and domain validation to the existing CLI/domain services, reads the canonical files without writing, and adds spatial cross-reference findings from a scene reader. The headless reader supports text USDA deterministically; when `pxr.Usd` is available in Isaac Sim it can inspect supported USD stages through OpenUSD APIs.

Each component prim carries a namespaced `cellforge:instanceId` attribute equal to the immutable YAML component ID. Validation reports missing prims, absent or mismatched prim IDs, duplicate scene IDs, duplicate operational IDs, extra tagged scene instances, and invalid/unreadable stages. UI callbacks only invoke `StudioApplication` commands and render returned findings.

The application stores opened YAML and scene text in memory. Editing commands replace those buffers and derive dirty state by exact comparison with the last successfully opened/saved contents. Open never writes. Save is the only command that writes an existing project's canonical files; it validates the proposed pair before writing.

Save writes and fsyncs a recovery journal containing the previous bytes, writes and fsyncs temporary candidates, then atomically replaces `cell.yaml` and the referenced scene. Any replacement failure restores both previous files from the journal before returning an error. A retained journal is an explicit recovery artifact only if rollback itself cannot complete; no UI callback silently treats a partial save as success.

The CLI starter and pen USDA scene gain the shared instance-ID metadata required by the new invariant. No schema changes or production dependencies are introduced.

## Work sequence
1. Add the ExecPlan and record prerequisite/baseline evidence.
2. Implement the pure scene reader, cross-reference validator, project command service, and transactional save/recovery behavior; add focused service tests.
3. Extend immutable application state and thin Kit callbacks for create/open/save and dirty state; update contract tests.
4. Add shared IDs to starter and pen USDA stages, documentation, and a deterministic Task 015 headless acceptance probe.
5. Run focused and full validation, inspect the complete diff, update results, commit, publish a ready PR, wait for required checks, merge only when green, and synchronize local `main`.

## Validation
- `make lint` (or its exact `uv` command body when GNU Make is unavailable)
- `make test` (or exact command body)
- `make validate-examples` (or exact command body)
- `make kit-extension-check` and `make studio-project-scene-check` (or exact command bodies)
- `isaac-sim.bat --no-window --ext-folder <repo>/src/kit --enable cellforge.studio --exec <repo>/scripts/verify_kit_project_scene.py`
- Focused tests cover valid pen open/save round trip, no writes on open/in-memory edits, invalid inputs, missing prim and duplicate ID findings, clean/dirty transitions, validation-blocked save, and rollback after an injected second-file replacement failure.
- `git status --short`, `git diff`, `git diff --check`, staged checks, and post-commit verification.

## Risks and rollback
USDA syntax is broader than the deterministic fallback parser; prefer `pxr.Usd` whenever installed and report unsupported binary stages when it is absent. Two separate filesystem files cannot be replaced with one OS primitive, so the recovery journal and rollback make the last valid pair recoverable. Rollback is a normal `git revert` of the Task 015 commit; no persistent data migration is introduced.

## Progress
- [x] 2026-08-10 — Read required specifications, architecture/ADR/task documents, prerequisite implementations, and Git history.
- [x] 2026-08-10 — Confirm Tasks 003 and 014 are merged ancestors of clean local and remote `main`; create task branch after a green baseline.
- [x] 2026-08-10 — Implement and test pure project/scene commands and cross-reference validation.
- [x] 2026-08-10 — Wire thin Kit callbacks, documentation, and headless acceptance probes.
- [ ] 2026-08-10 — Complete regression checks, commit, ready PR, CI, merge, and local-main synchronization.

## Decisions
- 2026-08-10 — Author `cellforge:instanceId` on each component prim; namespaced USD metadata keeps the spatial-to-operational link explicit without moving operational configuration into USD.
- 2026-08-10 — Retain exact source text in the editor buffer so an unmodified open/save round trip does not normalize user-authored YAML or USD formatting.
- 2026-08-10 — Keep scene parsing and transactional filesystem work outside `application.py`; the Kit-free state machine remains presentation-neutral and callbacks remain thin.
- 2026-08-10 — Treat Studio safety information as modeled/read-only engineering data; this task adds no safety logic or authorization path.
- 2026-08-10 — Re-run the existing whole-project validator against a temporary candidate tree before save so raw in-memory edits cannot bypass recipe, deployment, or other cross-file validation. Temporary validation artifacts never replace project sources.
- 2026-08-10 — Prefer `pxr.Sdf`/`pxr.Usd` composition when the Isaac Sim runtime is present; retain a deterministic text-USDA fallback for CPU-only CI and report binary USD as requiring OpenUSD rather than pretending to validate it.

## Results
Implemented explicit create/open/save commands, exact-text dirty buffers, shared `cellforge:instanceId` metadata, structured YAML/USD cross-reference findings, candidate whole-project validation, two-file recovery-journal transactions, explicit interrupted-save recovery, thin Kit callbacks, and headless probes. The final local run passed Ruff formatting/checking, mypy (57-source core scope and 7-source Studio scope), 232 pytest tests, validation of 5 canonical schemas/6 component config schemas/19 example YAML files, 20 Studio tests, 10 Task 015 service tests, extension manifest verification, and the non-Kit Task 015 probe.

GNU Make is unavailable on the Windows host, so the exact Makefile command bodies were executed directly with `uv`. Isaac Sim 6 is unavailable: neither `isaac-sim.bat` nor `isaacsim` is installed or on `PATH`; the local Omniverse package directory contains Hub and Kit only. The documented `scripts/verify_kit_project_scene.py` integration probe therefore remains unexecuted here. No ROS packages changed, so ROS build/test checks are not applicable. Commit, GitHub publication, CI, merge, and synchronization results remain pending.
