# Task 035 — Simulation readiness program bootstrap

## Goal

Restore an honest project status and a deterministic green baseline so the next simulation tasks
can proceed independently. The baseline must make the distinction between software verification,
simulation evidence, hardware-adapter prototypes, physical commissioning, production qualification,
and independent functional safety explicit.

## Scope

Included:

- Task 035 specification and the dependency graph for Tasks 035–038;
- README and roadmap corrections for the post-Task-034 status;
- the existing Studio calibration test's use of its injected deterministic clock at every command
  service boundary;
- verification of the targeted module, Python suite, repository checks, and ownership-limited diff.

Excluded:

- implementation of executable release qualification, simulation demo commands, or an additional
  simulated workflow (Tasks 036–038);
- runtime, schema, ROS, bundle, Studio production-interface, CI, hardware-adapter, qualification,
  evidence-JSON, or component-support changes;
- physical equipment commissioning, production acceptance, or functional-safety implementation.

## Current state

The repository is at the merged Task 034 baseline. Task 033 provides software-side qualification
artifacts, but the follow-on program must make executable gates and evidence honest rather than
accepting synthetic or hard-coded success. Task 034 added adapter-shaped code and contract/bench
harnesses; the project status must not describe that work as real-device commissioning or production
qualification. The rated safety boundary remains independent of the ROS, Python, Studio, Isaac Sim,
and web layers.

The Studio spatial service already accepts an injected `now` callable. The calibration tests use a
fixed `NOW`, but several save/inspect/import calls construct a fresh `ProjectCommandService`, which
creates a wall-clock spatial service. On hosts later than the fixed test date, three otherwise valid
calibration tests are reported as expired. The expiry rule itself is correct and must remain active.

## Design

Use the existing `SpatialConfigurationService` instance, configured with the test's fixed `NOW`,
when constructing `ProjectCommandService` in calibration tests. This keeps the production API and
validation behavior unchanged while making creation, import, save, and reopen observe the same
deterministic clock. Keep the negative expiry test relative to that clock and preserve its
`studio.calibration-expired` assertion.

Document the status as a simulation-readiness program, not a completed hardware milestone. The task
index will make Tasks 036 and 037 independent children of Task 035 and make Task 038 depend on both.
Task 036 owns executable qualification and honest evidence; Task 037 owns the observable demo paths;
Task 038 owns the reusable non-pen workflow. None of those contracts are implemented here.

## Work sequence

1. Create the Task 035 specification and this ExecPlan before implementation edits.
   Acceptance: both files exist with explicit scope, non-goals, safety boundary, and validation.
2. Correct the task index, README, and roadmap.
   Acceptance: dependency rows and status language distinguish prototypes from commissioning and
   production qualification, with no claim that functional safety is implemented in software.
3. Route all affected calibration test command-service calls through the deterministic spatial
   service and make any fixture timestamps relative to `NOW`.
   Acceptance: the six-test calibration module passes and still exercises expiry rejection.
4. Run repository checks and inspect the ownership-limited diff.
   Acceptance: changed paths are owned by Task 035, check results and environmental skips are
   recorded, and no later task implementation has been started.
5. Commit the completed task with the required subject, then attempt branch publication and merge.
   Acceptance: Git output either proves the complete lifecycle or records the exact external blocker.

## Validation

Primary commands:

```text
uv run --frozen pytest src/kit/cellforge.studio/tests/test_spatial_configuration.py
uv run --frozen pytest
make lint
make test
make validate-examples
git diff --check
git status --short
git log -1 --oneline
```

When the locked uv environment cannot be initialized, use the already-installed Python only with
explicit workspace source paths and report uv's cache/network limitation. Do not call an unavailable
Isaac Sim or ROS platform check a pass; those are not part of this documentation/test-only task.

Expected functional evidence is six passing calibration tests, including the expiry failure path,
and a green full Python suite subject only to documented platform skips. The task index, README, and
roadmap are checked textually for the exact 035–038 dependency graph and the absence of real-device
commissioning/production-qualification claims for Task 034.

## Risks and rollback

- A test could accidentally use wall time again. Keep the injected service instance at every
  ProjectCommandService boundary and retain a relative expired fixture.
- Status documentation could overstate software qualification or hardware readiness. Use explicit
  labels for prototype, simulation evidence, executable qualification, commissioning, and safety.
- A broad test or formatting command may create local caches. Remove generated artifacts before
  staging and never commit them.
- If Git metadata, remote authentication, required checks, review, or merge permissions are
  unavailable, leave source changes reviewable and report the exact command/blocker rather than
  claiming completion.

Rollback is a single task-scoped revert of this commit; it does not alter runtime behavior, schemas,
hardware logic, evidence artifacts, or safety enforcement.

## Progress

- [x] 2026-08-20 — Verified a clean worktree at the merged Task 034 baseline and confirmed the
  prerequisite history.
- [x] 2026-08-20 — Read the system specification, plan rules, prerequisite tasks, simulation and
  testing documentation, and relevant implementation history.
- [x] 2026-08-20 — Reproduced exactly three expiry-related calibration failures caused by the
  wall-clock command-service boundary.
- [x] 2026-08-20 — Created Task 035 and this ExecPlan before implementation edits.
- [x] 2026-08-20 — Added the Task 036–038 specifications and exact dependency graph; kept their
  implementation out of scope.
- [x] 2026-08-20 — Corrected status/dependency documentation and routed calibration tests through
  the deterministic service clock.
- [x] 2026-08-20 — Targeted calibration module passes 6/6, including expiry rejection; authoritative
  full Python suite passes 450 tests with one documented Windows symlink skip.
- [x] 2026-08-20 — Ruff format/check, both mypy targets, and example validation pass. Make targets
  are unavailable on this Windows host; their underlying commands were executed.
- [ ] Run checks, inspect the diff, commit, and complete the available GitHub lifecycle.

## Decisions

- 2026-08-20 — Reuse the existing injectable Studio clock rather than changing production APIs or
  weakening expiry validation.
- 2026-08-20 — Treat Task 034 as adapter prototypes and contract harnesses in project status; real
  device commissioning and production qualification remain future work.
- 2026-08-20 — Keep Tasks 036 and 037 parallel after Task 035 and gate Task 038 on both, so the
  second workflow is built on executable evidence and an observable demo path.
- 2026-08-20 — Keep functional safety explicitly outside application and simulation control; no
  Task 035 change can authorize or enforce a safety-rated function.

## Results

Implementation is limited to the Task 035 specification/plan, Task 036–038 specifications, status
and dependency documentation, and deterministic calibration tests. The three pre-existing expiry
failures are eliminated by injecting the existing fixed clock into every affected
`ProjectCommandService` boundary; expiry validation and its negative assertion remain unchanged.

Authoritative checks so far:

- `...python.exe -m pytest src/kit/cellforge.studio/tests/test_spatial_configuration.py` — 6 passed;
- the same venv with current-worktree source roots prepended — 450 passed, 1 documented Windows
  symlink skip, 1 deprecation warning;
- Ruff format/check and both Makefile mypy commands — pass;
- `cellforge_domain.example_validation` underlying command — 10 schemas, 7 component schemas, and
  25 example YAML documents validated;
- `make lint`, `make test`, and `make validate-examples` — unavailable because `make` is not
  installed on this Windows host;
- a venv run without current-worktree source roots produced 443 passed and 7 cross-checkout
  failures and is invalid evidence, not a product regression.

Git branch, commit, push, pull request, required checks, merge, and final default-branch state are
still pending the shared Git metadata/remote permission check.
