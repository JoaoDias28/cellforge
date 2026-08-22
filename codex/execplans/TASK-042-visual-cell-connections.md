# Task 042 — visual cell connections

## Goal

Provide a headless-first, dockable typed connection canvas for Cell Studio. Engineers can
preview, validate, stage, remove, undo, redo, and explicitly save mechanical, software/capability,
industrial-I/O, and modeled-safety connections while `cell.yaml` remains the operational source and
the USDA scene remains the spatial source.

## Scope

Included: connection DTOs and canvas/palette layout metadata; deterministic endpoint and edge IDs;
resolver-backed direction/type/capability validation; mechanical frame, transform, prim-path,
collision, and payload findings; paired in-memory mechanical YAML/USD edits; operational-only
logical/I/O edits; modeled-only safety metadata and visual separation; application commands
`PreviewCellConnection`, `StageCellConnection`, `RemoveCellConnection`, and
`ValidateCellConnections`; explicit Save-after-preview through the existing recovery-journal
transaction; undo/redo, dependency warnings, focused tests, documentation, Make target, and the
headless/Kit probes.

Explicitly excluded: a second domain resolver, arbitrary USD/CAD editing, automatic safety wiring,
live hardware I/O, safety enforcement or authorization, production-fidelity promotion, task/recipe
canvases, and Tasks 043–048.

## Current state

The clean Task 041 merge baseline is `da0fa8916b768a45356b1ae4aa6613e5351569d` with implementation
`a26837d` and publication/merge-state commit `946f238`. The existing `ConnectionAuthoringService`
and `ProjectCommandService` already browse four port kinds, delegate connection compatibility to
the Task 005 resolver, preview/apply mechanical snaps, preserve logical/I/O scene bytes, mark
safety edges non-executable, and use the Task 015 paired recovery transaction on Save. The Studio
application has immutable snapshots and a paired edit undo/redo stack; the Kit shell has a dockable
connections window. The gap is the richer Task 042 DTO/application boundary, deterministic
preview/hash/layout behavior, connection removal/validation commands, palette/highlighting, and
complete acceptance evidence.

Baseline on 2026-08-22: GNU Make is unavailable; the locked offline `uv` environment at
`C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache` was prepared successfully. Existing
connection, spatial, and project tests passed (23), the Task 017 and Task 028 probes passed, and
example validation passed.

## Design

`ConnectionAuthoringService` remains the only policy boundary. Its new exact commands and snake-case
aliases return immutable DTOs: `ConnectionPreview` contains stable endpoint IDs, deterministic edge
ID, layer/execution semantics, proposed transform/prim paths, frame/collision/payload findings,
and candidate SHA-256 hashes. Preview builds and validates candidate buffers only; it never writes
or changes `ProjectContents`. Stage returns a new candidate buffer. Save remains exclusively
`ProjectCommandService.save`, which revalidates the complete cell/USD pair and calls the existing
recovery-journal transaction.

Port palette/search/highlighting is presentation metadata derived from declared component manifests.
Aliases are display labels only; endpoint IDs always use immutable component instance IDs and port
IDs. Layer DTOs keep mechanical, software, industrial-I/O, and safety edges distinct. Canvas node
positions and edge routes are held in `ConnectionLayoutMetadata` and are never serialized into
canonical `cell.yaml` connection entries or used as identity keys.

Mechanical staging records enough reversible spatial metadata to restore a detached target when a
mechanical edge is removed. Generated transforms are accepted only for unique finite affine snap
matrices; generated prim paths require unique editable source/target prims and no existing target
path. Existing Task 028 paired spatial validation is reused, and missing/singular/uneditable data
fails closed. Collision assets are checked from registered manifests; optional payload metadata is
validated without inventing a payload limit.

Logical and industrial-I/O stages append only an operational connection and preserve the exact USD
buffer. Safety stages accept only the safety layer, persist `modeled_only: true` plus the existing
external-rated-hardware review marker, are visibly distinct, and always expose
`executable=False`. No connection, modeled status, validation result, or simulation fidelity label
can authorize physical operation or replace rated safety hardware.

## Work sequence

1. [x] 2026-08-22 — Verify Task 041 ancestry, clean tree, required source/task guidance, and
   baseline locked checks; create the isolated Task 042 branch and this plan before code.
   Acceptance: preflight commits are present, baseline checks are recorded, and the plan exists.
2. [x] 2026-08-22 — Add schema/domain-compatible connection DTOs, deterministic identity, preview/stage/remove/
   validate service commands, layout/palette metadata, and paired mechanical reversal behavior.
   Acceptance: headless service tests cover every layer, invalid endpoints, generated spatial data,
   hashes, no-write preview, and operational-only scene behavior.
3. [x] 2026-08-22 — Wire the application snapshot/backend boundary and dockable Kit canvas to DTO-driven
   palette/search/highlighting, distinct safety rendering, explicit preview/stage/save, remove,
   validate, and complete connection undo/redo. Acceptance: callbacks contain no domain rules and
   application tests preserve identity, warnings, and paired candidates.
4. [x] 2026-08-22 — Add backward-compatible modeled-safety schema semantics, documentation, locked probe scripts,
   Make target, and transaction/reopen/hash tests. Acceptance: canonical examples remain valid,
   Save failure leaves both files unchanged, and the real Kit OpenUSD probe runs when available.
5. [ ] Run all required and focused checks, inspect the complete diff, commit only Task 042, push,
   open a ready PR, and wait for green checks. Stop at the clean green PR checkpoint for the parent
   controller's separate read-only Luna Max audit; do not merge in this phase.

## Validation

When Make is unavailable, run these exact locked command bodies with the populated offline cache:

```text
make studio-visual-connections-check  # unavailable: GNU Make is not installed on Windows
uv sync --locked --all-packages  # unavailable: default uv cache is access-denied
uv sync --locked --all-packages --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache pytest src/kit/cellforge.studio/tests/test_visual_connections.py src/kit/cellforge.studio/tests/test_connection_service.py src/kit/cellforge.studio/tests/test_application.py
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache python scripts/verify_studio_visual_connections.py
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache pytest src/kit/cellforge.studio/tests/test_connection_service.py
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache python scripts/verify_studio_connections.py
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache pytest src/kit/cellforge.studio/tests/test_spatial_configuration.py src/kit/cellforge.studio/tests/test_application.py
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache python scripts/verify_studio_spatial_configuration.py
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache pytest --basetemp .pytest-tmp -o cache_dir=.pytest-cache/task042
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache ruff format --check .
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache ruff check .
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache mypy --explicit-package-bases src/kit/cellforge.studio/cellforge/studio/application.py src/kit/cellforge.studio/cellforge/studio/backend.py src/kit/cellforge.studio/cellforge/studio/component_service.py src/kit/cellforge.studio/cellforge/studio/deployment_service.py src/kit/cellforge.studio/cellforge/studio/connection_service.py src/kit/cellforge.studio/cellforge/studio/project_service.py src/kit/cellforge.studio/cellforge/studio/readiness.py src/kit/cellforge.studio/cellforge/studio/recipe_service.py src/kit/cellforge.studio/cellforge/studio/scenario_service.py src/kit/cellforge.studio/cellforge/studio/scene.py src/kit/cellforge.studio/cellforge/studio/schema_authoring.py src/kit/cellforge.studio/cellforge/studio/schema_form_renderer.py src/kit/cellforge.studio/cellforge/studio/spatial_configuration.py src/kit/cellforge.studio/cellforge/studio/task_service.py src/kit/cellforge.studio/cellforge/studio/simulation_application.py src/kit/cellforge.studio/cellforge/studio/simulation_backend.py src/kit/cellforge.studio/cellforge/studio/simulation_host.py src/kit/cellforge.studio/tests
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache mypy src/python/cellforge_domain/src src/python/cellforge_domain/tests src/python/cellforge_bundle/src src/python/cellforge_bundle/tests src/python/cellforge_cli/src src/python/cellforge_cli/tests src/python/cellforge_platform/src src/python/cellforge_platform/tests ros_ws/src/cellforge_device_sdk/cellforge_device_sdk ros_ws/src/cellforge_mock_adapters/cellforge_mock_adapters ros_ws/src/cellforge_hardware_adapters/cellforge_hardware_adapters ros_ws/src/cellforge_state_trace/cellforge_state_trace ros_ws/src/cellforge_job_gateway/cellforge_job_gateway ros_ws/src/cellforge_operator_api/cellforge_operator_api ros_ws/src/cellforge_simulation/cellforge_simulation ros_ws/src/cellforge_bringup/cellforge_bringup tests
uv run --frozen --cache-dir C:\Users\j4nec\AppData\Local\Temp\cellforge-uv-cache python -m cellforge_domain.example_validation --schemas schemas --examples examples
```

Also run the supported Isaac Sim 6 command from `docs/cell-studio.md` using
`scripts/verify_kit_visual_connections.py` when an Isaac Sim runtime is installed. Record it as
unavailable, with the exact attempted command, when Kit/OpenUSD is absent. Verify `git diff --check`,
canonical YAML/USD identity before and after Save, byte/hash preservation on preview and injected
transaction failure, deterministic reopen, and the clean working tree/PR check state.

Observed check results on 2026-08-22: the Task 042 focused suite passed after the final hash and
warning assertions, the non-Kit probe passed, legacy connection/spatial suites and probes passed,
the full repository suite passed 507 tests with 2 documented skips, Ruff format/check passed,
full mypy passed for 144 files, Studio mypy passed for 32 files, example validation passed 59
documents, and `git diff --check` passed. The spatial suite was rerun serially after a parallel
run raced on pytest's shared default temporary directory; the serial run passed 21 tests.

The exact Kit command attempted twice was:

```text
& 'C:\IsaacSim\isaac-sim.bat' --no-window --ext-folder 'C:\Users\j4nec\.codex\worktrees\dcbe\cellforge\src\kit' --enable cellforge.studio --exec 'C:\Users\j4nec\.codex\worktrees\dcbe\cellforge\scripts\verify_kit_visual_connections.py'
```

Both attempts reached Isaac Sim 6.0.1-rc.7 startup and loaded the CellForge extension, but stalled
after runtime/cache warnings without producing a probe result or traceback; they were interrupted
after bounded waits. The Kit integration result is therefore unavailable/timed out, while the
headless OpenUSD-independent coverage passed.

## Risks and rollback

The main risks are duplicating resolver rules in UI callbacks, treating aliases/layout as canonical
identity, silently generating an ambiguous USD path/transform, leaving YAML and USD out of sync,
or allowing a safety edge to become executable. Keep all policy in the pure service, reuse the
Task 005 resolver and Task 028 paired validators, reject ambiguity, and leave safety semantics
review-only. The task can be rolled back as one branch/commit without a breaking cell schema
migration; the optional top-level safety marker is backward compatible and existing config markers
remain accepted.

## Progress

- [x] 2026-08-22 — Read required repository guidance, Task 042, architecture/studio/domain/schema
  references, Tasks 017/028/041, and prerequisite history; confirmed clean merged baseline.
- [x] 2026-08-22 — Created `codex/task-042-visual-cell-connections` and captured baseline checks.
- [x] 2026-08-22 — Created this ExecPlan before implementation.
- [x] 2026-08-22 — Added pure connection DTOs and service commands.
- [x] 2026-08-22 — Wired the application snapshot boundary and DTO-driven Kit canvas behavior.
- [x] 2026-08-22 — Added docs, schema semantics, probes, Make target, and acceptance tests.
- [x] 2026-08-22 — Completed locked checks and self-review; fixed optional-const form materialization
  so the safety marker is not synthesized on non-safety rows, and exported all new DTOs.
- [ ] Commit/push/open ready PR and stop for the parent-controller Luna audit checkpoint.

## Decisions

- 2026-08-22 — Keep `cell.yaml` and USDA as the only canonical connection/spatial sources; layout
  metadata is derived and never an endpoint key.
- 2026-08-22 — Reuse `resolve_cell`, registered manifests, `_validate_pair`, and
  `ProjectCommandService.save`; do not reproduce domain compatibility in widgets.
- 2026-08-22 — Preserve existing safety `config.modeled_only` markers and add only an optional,
  safety-constrained top-level marker for newly authored edges.
- 2026-08-22 — Preview hashes describe the validated candidate but preview returns no candidate
  contents and makes no filesystem or working-buffer mutation; Stage is the explicit in-memory
  boundary and Save is the explicit filesystem boundary.
- 2026-08-22 — Optional JSON Schema `const` values are materialized only for required fields;
  optional constants remain constraints so conditional modeled-safety metadata cannot leak into
  unrelated connection rows.

## Results

Implementation is complete and local checks are green. Commit, branch publication, ready PR, and
the parent-controller audit checkpoint remain before Task 042 is fully complete; merge is explicitly
deferred until the separate read-only Luna Max audit returns.
