# Task 001 repository bootstrap

## Goal

Create a reproducible monorepo bootstrap in which the pure Python domain package can be linted, type-checked, and tested, and a ROS 2 Jazzy placeholder package can be built and tested from stable root commands. This establishes the build boundary required by later tasks without implementing their domain models, schemas, interfaces, or runtime behavior.

## Scope

Included work:

- a root `Makefile` exposing `lint`, `test`, `validate-examples`, `ros-build`, and `ros-test`;
- a `uv`-managed Python workspace with a committed lock file;
- an importable, intentionally empty `cellforge_domain` package and import test;
- a buildable `ament_cmake` placeholder at `ros_ws/src/cellforge_interfaces`;
- Python and C++ formatting/static-analysis configuration;
- GitHub Actions validation for Python 3.12 on Ubuntu 24.04 and ROS 2 Jazzy;
- developer setup and command documentation.

Explicitly excluded:

- domain models and schema loading from Task 002;
- schema/example validation implementation from Task 003;
- copying or generating the canonical ROS definitions from `ros_interfaces/`, which belongs to Task 007;
- Isaac Sim dependencies or tests;
- production services, runtime nodes, hardware adapters, and functional-safety logic.

## Current state

The repository is a clean design pack containing specifications, schemas, canonical ROS interface source files, and a pen-engraving example, but no build system or implementation packages. `.github/workflows/README.md` is a CI-intent placeholder. The specified layout in `docs/architecture.md` separates pure Python under `src/python/` from ROS packages under `ros_ws/src/`. Ubuntu 24.04 and ROS 2 Jazzy are fixed by ADR 0003.

The local environment has Python 3.12.10, `uv` 0.10.0, and Docker, but lacks GNU Make, ROS 2, and colcon. Git commands require a command-local `safe.directory` override because repository ownership differs from the execution user. No production code or safety enforcement is introduced by this task.

## Design

The root is a `uv` workspace and the domain library is an independently packaged workspace member. Development tools are locked in `uv.lock`; the domain package has no runtime dependencies. Root Make targets perform frozen synchronization before Python checks so the same commands work in a clean Ubuntu checkout.

`cellforge_interfaces` is an `ament_cmake` package with metadata, CMake configuration, and standard ament lint tests only. It does not consume `ros_interfaces/` or generate types yet, preventing Task 007 scope from leaking into this task.

`validate-examples` prints that validation is deferred to Task 003 and returns a nonzero status. This is intentional failure behavior: automation and developers cannot interpret the unimplemented validator as successful validation.

GitHub Actions uses pinned action revisions/tags, Ubuntu 24.04, Python 3.12, the committed `uv.lock`, and the ROS Jazzy apt repository configured by ROS tooling. The Python job invokes root lint/test targets. The ROS job installs ROS Base plus colcon, resolves package dependencies with rosdep, and invokes the root ROS targets. Isaac Sim is absent.

## Work sequence

1. Add the ExecPlan and record the reviewed constraints; acceptance check: the plan contains all sections required by `PLANS.md` and explicitly excludes Task 002 and later-task implementation.
2. Add the Python workspace, package, test, static-analysis configuration, and lock file; acceptance check: frozen `uv` sync succeeds and direct import plus pytest pass.
3. Add the root command surface and honest unwired example-validation behavior; acceptance check: Python equivalents of `make lint` and `make test` pass locally, and the validation target is confirmed to fail clearly.
4. Add the buildable ROS placeholder and C++ configuration; acceptance check: package metadata is structurally valid locally and `colcon build/test` runs in a ROS Jazzy environment when available.
5. Replace the CI placeholder with executable Python and ROS jobs and document setup; acceptance check: workflow YAML parses and required job/step structure is covered by tests.
6. Run all available checks, inspect the final diff for Task 001 scope, and record exact results and unavailable checks in this plan.

## Validation

Required commands and expected evidence:

- `make lint` — Ruff formatting/lint and mypy succeed after a locked sync.
- `make test` — pytest succeeds and verifies `cellforge_domain` import plus CI workflow structure.
- `make validate-examples` — exits nonzero and explicitly reports that schema/example validation is not wired until Task 003.
- `make ros-build` — builds `cellforge_interfaces` with ROS 2 Jazzy and colcon.
- `make ros-test` — runs ament package tests and returns failure on any failed test.
- `uv lock --check` and `uv sync --locked --all-packages` — demonstrate a reproducible Python lock/install.
- YAML parsing tests — demonstrate syntactically parseable workflow YAML and the expected Python/ROS jobs.

Because GNU Make, ROS 2, and colcon are not installed locally, invoke the exact Python commands underlying the Make targets and use Docker for the closest ROS Jazzy check if the local Docker daemon is available. Report any unavailable integration command without treating metadata-only checks as equivalent.

## Risks and rollback

- CI action or ROS apt behavior may differ from local Windows validation. Keep CI steps explicit and verify in an Ubuntu/ROS environment when available.
- A placeholder ROS package can be mistaken for completed interfaces. Its README and ExecPlan must state that type generation is Task 007.
- An honest nonzero example-validation target temporarily means the full minimum command set does not all pass. This matches Task 001 acceptance and prevents a false validation claim; Task 003 will replace it.
- `uv` workspace metadata may constrain later package layouts. Use independent workspace members under the architecture-prescribed `src/python/` path so new packages remain additive.

Rollback is a reviewable deletion of the files introduced by this task; no schema, example, canonical ROS definition, database, deployment artifact, or safety configuration is migrated or mutated.

## Progress

- [x] 2026-08-06 16:22:29 +01:00 — Read `AGENTS.md`, `SYSTEM_SPEC.md`, `PLANS.md`, Task 001, repository state, architecture/testing docs, and ROS Jazzy ADR.
- [x] 2026-08-06 16:35:35 +01:00 — Implemented and locked the Python workspace; frozen sync and strict checks pass.
- [x] 2026-08-06 16:35:35 +01:00 — Added root commands and a buildable ROS placeholder without generating Task 007 interfaces.
- [x] 2026-08-06 16:35:35 +01:00 — Added executable CI and developer documentation.
- [x] 2026-08-06 16:35:35 +01:00 — Ran all acceptance checks available in Windows and Ubuntu 24.04 WSL and recorded results.

## Decisions

- 2026-08-06 16:22:29 +01:00 — Use `uv` workspaces and a committed `uv.lock` for reproducible Python development because the architecture anticipates multiple independent Python packages.
- 2026-08-06 16:22:29 +01:00 — Make unimplemented example validation fail explicitly instead of returning success; Task 001 permits it to remain unwired but forbids a false validation claim.
- 2026-08-06 16:22:29 +01:00 — Keep `cellforge_interfaces` empty but buildable; populating the canonical definitions is assigned to Task 007.
- 2026-08-06 16:22:29 +01:00 — Treat all safety-related repository content as read-only in this bootstrap; no application-layer safety logic is needed.
- 2026-08-06 16:35:35 +01:00 — Source the ROS environment before enabling Bash `nounset`; Jazzy's setup script reads an optional tracing variable that may be unset in a clean shell.

## Results

Task 001 is implemented without starting Task 002. The repository now has a locked `uv` workspace,
an import-tested `cellforge_domain` boundary with no runtime dependencies, root Make targets,
Python/C++ tooling configuration, a buildable `cellforge_interfaces` placeholder, Ubuntu/Jazzy CI,
and developer setup/dependency documentation.

Validation evidence:

- `uv lock --check` and `uv sync --locked --all-packages`: passed with 16 resolved packages and 15 installed/audited packages.
- `make lint`: passed under Ubuntu 24.04 WSL; Ruff formatting/lint and strict mypy all succeeded.
- `make test`: passed; 3 tests passed. WSL invoked the existing Windows `uv.exe` because WSL has no Linux `uv`, producing one non-fatal pytest cache permission warning; the same commands also passed directly on Windows without warnings.
- `make validate-examples`: intentionally failed with the explicit Task 003 deferral message. No example was reported as validated.
- `make ros-build`: passed in Ubuntu 24.04 WSL against `/opt/ros/jazzy`; one package built.
- `make ros-test`: passed in the same Jazzy environment with 0 errors and 0 failures. The placeholder currently defines 0 ROS tests because no interfaces or C++ sources are introduced until later tasks.
- CI workflow YAML and required job structure: parsed and asserted by passing unit tests.

The GitHub-hosted workflow itself was not dispatched from this local environment. Docker Desktop is
installed but its Linux daemon was not running; this did not block the stronger native Ubuntu 24.04
WSL ROS Jazzy build/test. Isaac Sim checks are intentionally unavailable and excluded by Task 001.
