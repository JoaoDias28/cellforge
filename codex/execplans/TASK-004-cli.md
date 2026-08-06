# Task 004 CellForge CLI

## Goal
Provide a typed, headless `cellforge` command-line package for scaffolding, copying, validating,
and inspecting cell projects and for listing the canonical schemas. The commands must expose stable
machine-readable results without adding ROS, Isaac Sim, web, vendor, production-control, or
functional-safety dependencies.

## Scope
Included: `cellforge project init <path>`, `cellforge validate <project>`,
`cellforge inspect <project>`, `cellforge schema list`, and
`cellforge example copy pen-engraving <path>`; human and JSON output; documented exit codes;
canonical resource discovery and wheel inclusion; a valid simulation-only starter project; tests
using temporary directories; developer documentation; workspace quality-gate wiring.

Excluded: component/capability resolution (Task 005), compilation and deployment bundles (Task
006), ROS/Isaac Sim integration, spatial USD validation, behavior-tree semantics, physical process
authorization, recipe approval policy, hardware control, and functional-safety enforcement.

## Current state
The clean repository is on `task/004-cli`. Task 002 is commit `dede63e` and supplies pure Pydantic
models and source-aware errors. Task 003 is exact commit
`ff6fe84d0e542394e27dc234eea72f0f232e32e7`, subject
`task(003): add schema and example validation`; it supplies `SchemaRegistry` and
`validate_example_tree`. The CLI package does not yet exist.

Pre-edit direct checks pass: Ruff format (72 files), Ruff lint, strict mypy (13 source files), 40
pytest tests, and validation of 5 canonical schemas, 6 component configuration schemas, and 11
example YAML documents. GNU Make is unavailable on this Windows host. A locked `uv sync` attempt
was also blocked by managed cache permissions, so the existing locked `.venv` was used for direct
baseline commands.

## Design
Create a separate `cellforge-cli` workspace package depending only on `cellforge-domain`. Use the
standard library `argparse` API and an `IntEnum` exit-code contract: success, validation failure,
usage error, missing input, existing destination, and unavailable bundled resource. Successful and
failed commands render either concise human text or a deterministic JSON envelope. Validation
errors retain the domain `ValidationFinding` code, severity, source path, and message.

The CLI delegates all YAML/JSON and cross-file validation to Task 003. It adds only project-level
preflight findings for a missing directory or `cell.yaml`; it does not fork domain validation.
Inspection first requires a valid project, then summarizes the canonical `CellProject` without
resolving capabilities or interpreting safety connections.

Source checkouts discover the repository's canonical `schemas/` and `examples/pen_engraving/`
directories by walking from the package location. Wheel builds force-include those same source
trees under package resources, so installed commands do not depend on the repository layout. The
resource locator prefers packaged resources and returns sanitized failures.

`project init` writes a new project through a same-parent temporary directory and atomic rename.
The starter contains one metadata-only passive workspace marker, an OpenUSD scene, an empty
BehaviorTree.CPP document, and a simulation-only deployment profile. It declares no process
capabilities, production mode, hardware adapter, or executable safety behavior. Project and example
copy operations refuse to overwrite existing paths.

No external production dependency is added. The CLI uses only the Python standard library plus the
existing domain package; its removal path is deleting the independent workspace package and its
root quality-gate entries.

## Work sequence
1. Add this ExecPlan and confirm the intended CLI/resource/error contracts; acceptance: the plan
   records scope, baseline, safety boundary, and exact validation commands.
2. Add the CLI workspace package, entry point, resource discovery, project operations, output
   envelopes, and all five command families; acceptance: strict mypy and Ruff pass for both Python
   packages.
3. Add temporary-directory tests for init, copy-and-validate, invalid structured output, inspect,
   schema listing, overwrite refusal, usage status, and forbidden dependency imports; acceptance:
   focused and repository pytest pass.
4. Document command usage and exit codes, update workspace test/type-check configuration, generate
   the lock update, and verify the built/installed console entry point where the environment permits.
5. Run Task 004 acceptance and regression checks, inspect and stage only the scoped diff, update
   plan results, create the required commit, and verify a clean worktree and confirmed log entry.

## Validation
Run:

```text
make lint
make test
make validate-examples
uv sync --locked --all-packages
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy src/python/cellforge_domain/src src/python/cellforge_domain/tests src/python/cellforge_cli/src src/python/cellforge_cli/tests tests
uv run --frozen pytest
uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving
cellforge example copy pen-engraving <temporary-path>
cellforge validate <temporary-path>
git diff --check
git diff --cached --check
```

Expected evidence: all direct Python checks and CLI acceptance tests pass; invalid projects return
the documented nonzero validation status with structured errors. GNU Make, locked sync, ROS, or
Isaac Sim checks that the host cannot execute will be reported as unavailable rather than waived.

## Risks and rollback
Bundled resources could drift from source; wheel configuration includes the canonical repository
trees directly, and tests use the same locator. File-copy failures could leave partial output; both
generators stage in a uniquely named sibling directory and rename only after success. JSON output
could become unstable; sorted serialization and contract tests pin its envelope and exit codes.
The starter could imply production readiness; it is simulation-only, metadata-only, and explicitly
contains no hardware/safety authorization. Rollback is the single Task 004 commit; no schema,
project migration, external system, or hardware state is changed.

## Progress
- [x] 2026-08-06 — verified required documents, clean tree, branch, prerequisites, history, and
  pre-edit baseline.
- [x] 2026-08-06 — CLI package and all five command families implemented.
- [x] 2026-08-06 — temporary-directory tests, documentation, and quality wiring complete.
- [x] 2026-08-06 — installed entry-point acceptance, wheel-resource verification, and full
  regression checks complete.
- [x] 2026-08-06 — final diff review and required Task 004 Git lifecycle complete.

## Decisions
- 2026-08-06 — Reuse Task 003 validation services and preserve the pure-domain dependency
  direction; the CLI is an application-layer adapter only.
- 2026-08-06 — Use `argparse` rather than adding a CLI framework dependency.
- 2026-08-06 — Make the generic starter structurally valid but capability-free and simulation-only,
  so validation success cannot be mistaken for authorization to run a physical process.
- 2026-08-06 — Treat safety connections as inspectable data only; Task 004 adds no safety logic.
- 2026-08-06 — Verify copied project schemas byte-for-byte against bundled canonical schemas so a
  project cannot weaken its own validation contract.

## Results
Implemented the independent `cellforge-cli` workspace package with the five required command
families, stable exit codes 0–6, deterministic human/JSON rendering, overwrite-safe atomic project
generation and example copying, schema listing, validation, and typed inspection summaries. The
generic starter is schema-valid, metadata-only, capability-free, simulation-only, and contains no
executable success placeholder or safety authority.

Copied pen examples are portable through project-local schema copies. Those copies must match the
bundled canonical schema set byte-for-byte before validation, preventing local schema weakening.
Wheel builds include the canonical schemas and full pen example from their repository source trees.

Ruff format and lint pass for 82 files; strict mypy passes for 20 source files; all 49 pytest tests
pass. Canonical validation accepts 5 schemas, 6 component configuration schemas, and 11 example
YAML documents. The installed `cellforge` entry point successfully initialized and validated a
starter, copied and validated the pen example, inspected it, and listed schemas. A wheel build also
proved required schema and pen files are packaged.

GNU Make is unavailable on this Windows host, so `make lint`, `make test`, and
`make validate-examples` were attempted and reported unavailable; their direct `.venv` equivalents
all pass. ROS and Isaac Sim checks are not applicable because Task 004 adds only a pure Python
engineering CLI. Task 005 was not started.
