# Task 014 — Isaac Sim / Kit extension shell

## Goal
Provide a loadable Cell Studio shell for Isaac Sim 6 with dockable project, validation, and log
panels while keeping project inspection and validation in a pure, headless-testable Python service.

## Scope
Included: extension metadata and lifecycle, three dockable panels, useful no-project and
backend-unavailable states, a read-only application/backend boundary, deterministic non-Kit tests,
and documented interactive and headless Isaac Sim commands. Excluded: project or USD editing,
scene round trips, component placement, simulation control, deployment, and every Task 015 feature.

## Current state
Task 004 commit `04912dc` is an ancestor of `main` and supplies the pure CLI project inspection and
validation services. `docs/cell-studio.md`, ADR 0001, ADR 0002, and `docs/architecture.md` require a
thin Kit UI over application services and preserve `cell.yaml`/USD as separate canonical artifacts.
The repository has no Kit extension yet. Isaac Sim 6 is not installed in the current Windows
environment. NVIDIA's Isaac Sim 6 documentation confirms `omni.ext.IExt` startup/shutdown,
`extension.toml` Python modules, `--enable` extension activation, and `omni.ui` dockable windows.

## Design
The extension lives at `src/kit/cellforge.studio`. Its top-level Kit module owns only lifecycle,
widgets, rendering, and docking. `application.py` contains immutable view models and command
coordination with no `omni`, USD, ROS, or filesystem-write imports. `backend.py` adapts the existing
Task 004 inspection/validation functions; imports are deferred so a missing installed backend
becomes an explicit empty state instead of preventing extension startup.

Opening the extension creates no project command and therefore performs no project I/O. Opening or
refreshing a project invokes one read-only backend query. The UI displays returned findings and
never reimplements schema or domain rules. Backend failures are reduced to stable public states and
safe log records. No safety authority or production operation is added.

## Work sequence
1. Add the ExecPlan and pure application/backend service; acceptance: focused non-Kit tests cover
   no project, missing backend, valid/invalid project, failure handling, and read-only behavior.
2. Add Isaac Sim 6 extension metadata, lifecycle, panels, and a headless lifecycle probe;
   acceptance: manifest/structure tests pass without importing Kit on the development host.
3. Wire root lint/test targets and document supported interactive/headless launch commands;
   acceptance: repository documentation and checks name the exact extension path and commands.
4. Run scoped and full validation, inspect the diff, commit Task 014, publish a ready PR, wait for
   required checks, merge only when green, and synchronize local `main`.

## Validation
Run:

```text
make lint
make test
make validate-examples
uv run --frozen pytest src/kit/cellforge.studio/tests
uv run --frozen python scripts/verify_kit_extension_manifest.py
./isaac-sim.sh --no-window --ext-folder <repo>/src/kit --enable cellforge.studio \
  --exec <repo>/scripts/verify_kit_extension.py
git diff --check
git diff --cached --check
```

Expected evidence: pure tests prove startup state is read-only and backend outcomes are rendered
without UI validation logic; manifest verification proves the extension layout is discoverable.
The Isaac Sim command must load and unload the extension on an installed Isaac Sim 6 host. If the
host lacks Isaac Sim, that integration command is unavailable and is not represented as passing.

## Risks and rollback
Kit APIs may differ from older releases; use only Isaac Sim 6 documented `IExt`, `omni.ui.Window`,
and docking APIs. Isaac's Python environment may not contain CellForge packages; deferred backend
loading makes this visible and recoverable. Project reads could accidentally write; the service
exposes no write command and tests compare the complete project tree before and after inspection.
Rollback is the single Task 014 commit; there are no schema, project, hardware, or safety changes.

## Progress
- [x] 2026-08-10 — read required specifications and relevant architecture/ADR documents; verified
  clean `main`, Task 004 ancestry, branch creation, and the pre-edit baseline.
- [x] 2026-08-10 — implemented and tested the pure application/backend boundary, including
  byte-for-byte read-only project inspection and Task 004 project-local schema selection.
- [x] 2026-08-10 — implemented and structurally verified the Kit extension lifecycle and panels.
- [x] 2026-08-10 — completed regression, Git, GitHub, merge, and final verification lifecycle.

## Decisions
- 2026-08-10 — Keep the pure service inside the extension source tree so Isaac Sim discovers a
  self-contained extension; defer optional Task 004 imports to preserve a useful missing-backend
  state.
- 2026-08-10 — Treat project selection as an explicit user command. Extension startup never reads
  or writes a project and does not restore a previous path automatically.
- 2026-08-10 — Reuse Task 004 validation and inspection without translating validation rules into
  widget callbacks.
- 2026-08-10 — Expose Task 004's existing project-local schema selection as a public application
  service shared by CLI and Studio, preserving byte-identity checks and avoiding divergent rules.

## Results
Implemented `cellforge.studio` extension discovery metadata, `IExt` lifecycle, and dockable project,
validation, and log panels. The pure application service owns immutable empty/ready/invalid/failure
states and delegates to Task 004 through a deferred backend adapter. Startup issues no project
command. A copied project with verified local schemas is inspected byte-for-byte read-only.

Ruff format/lint pass for 152 files, strict mypy passes for 61 source files, all 221 pytest tests
pass, the five canonical schemas and 19 example documents validate, and the non-Kit manifest check
passes. Focused CLI/Studio tests pass 18/18. GNU Make is unavailable on this Windows host, so the
three required Make targets were attempted and their exact locked `uv` equivalents pass.

Isaac Sim 6 is unavailable: PATH and the Python environment contain no Isaac Sim executable or
package, and the local source build at `C:\isaacsim` identifies itself as Isaac Sim 5.1.0. The
documented Isaac Sim 6 headless lifecycle command was therefore not run against an unsupported
version.

Implementation commit `2ac6621` was published in ready PR #6. Hosted Python 3.12 validation and
ROS 2 Jazzy build/test both passed, GitHub reported the PR clean and mergeable, and merge commit
`b44b778` was synchronized to local and remote `main` with a clean working tree. Task 015 was not
started.
