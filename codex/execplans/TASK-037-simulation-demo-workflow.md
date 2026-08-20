# Task 037 — Reproducible simulation demo workflow

## Goal

Provide one documented L0 command for the canonical pen demo and one supported headless Isaac
Sim 6 L2 command. Both commands write a small, discoverable, machine-readable artifact set that
identifies the inputs, adapters, fidelity, assertions, trace/events, limitations, and replay
instructions. A missing or failed L2 prerequisite must be reported as unavailable or failed, never
as a pass.

## Scope

Included: additive demo runners under `scripts/*simulation_demo*`, demo-specific tests, Make
targets, simulation/demo documentation, a concise README quick start, predictable ignored output,
and compact demo fixture metadata under `examples/pen_engraving/demo/` if needed.

Excluded: Task 036 qualification, new simulation semantics, ROS/schema/public interface changes,
hardware adapters, commissioning/production authorization, functional-safety logic, and Task 038.

## Current state

Task 035 is the current clean baseline (`864e995`). The Task 013 `cellforge_mock_adapters.headless`
runner executes the canonical pen behavior-tree XML through the existing L0 adapter contracts and
produces timestamp-free seed-derived traces. Task 018 already defines canonical project/scene/
scenario evidence identities and fidelity disclaimers. Task 027's
`scripts/verify_kit_l2_runtime.py` is the existing Isaac Sim 6/OpenUSD/PhysX probe; its wrapper
requires Isaac 6, CUDA, and actual PhysX evidence and writes a 100-seed report. This workstation's
Task 027 history records a supported Isaac 6 qualification, but the demo must inspect the live
environment and must not rely on historical output.

## Design

`scripts/run_simulation_demo.py` is the single cross-platform entry point:

* L0 resolves the canonical project, recipe, tree, and selected scenario; delegates execution to
  `PenHeadlessExecutor`; optionally overrides only the deterministic seed; evaluates source and
  explicit CLI assertions; and writes `report.json`, `trace.json`, `events.json`, `junit.xml`,
  `run.log`, and `replay.txt` under `.artifacts/simulation-demo/l0/seed-<seed>/` by default.
* L2 performs local Isaac version/Kit/GPU preflight, launches the unchanged Task 027 probe, stores
  its raw report and logs, verifies Isaac 6/CUDA/`actual_physx_executed`/100 successful runs, and
  writes the same common artifact names under `.artifacts/simulation-demo/l2/`. Missing
  prerequisites and probe failures still write a failed/unavailable report and return non-zero.
* Common reports contain only repository-relative artifact references and deterministic identity
  data; wall-clock logs and output paths are not part of normalized replay inputs. Input hashes
  cover the canonical cell, scene, tree, recipe, selected scenario, and adapter configuration.
  Source revision is resolved from Git when available.
* Every report declares simulation-only execution, `physical_operation_authorized: false`, and
  separate interface, physics, process-quality, hardware, and safety limitations. No demo mode
  selects commissioning/production or implements a safety function.

## Work sequence

1. Add this living plan and inspect the existing runner/probe contracts; acceptance: ownership and
   failure boundaries are explicit.
2. Implement the L0 common artifact writer and assertion handling; acceptance: nominal execution,
   same-seed byte replay, and a deliberately failing assertion are covered by focused tests.
3. Implement the L2 preflight/probe wrapper and common report conversion; acceptance: missing
   runtime is an honest non-zero unavailable result, while only a validated actual-PhysX Task 027
   report can pass.
4. Add Make targets and documentation, then run focused and repository checks; acceptance:
   commands and limitations are discoverable on Windows and portable Linux runners.
5. Inspect the scoped diff, commit only Task 037, publish a ready PR, wait for required checks,
   merge only when green, and synchronize the local default branch.

## Validation

* `uv run --frozen pytest tests/test_simulation_demo.py`
* Two identical L0 runs with the same seed and byte comparison of normalized artifacts.
* A selected failing assertion returns non-zero and records a failed assertion.
* L2 preflight/probe command; if the supported Isaac 6/GPU is unavailable, preserve the failed
  unavailable artifact and report the integration check as unavailable.
* `make lint`, `make test`, `make validate-examples`, plus applicable simulation checks and ROS
  checks where the environment supports them.
* `git diff --check`, staged checks, post-commit status/log, hosted CI, and mergeability.

## Risks and rollback

The main risk is accidentally relabeling Task 013 mock output or Task 020 CPU output as L2. The
wrapper will only accept the existing Task 027 probe's version/GPU/PhysX markers and will fail
closed otherwise. L0 assertion overlays must not change the canonical runner. All changes are
additive and can be reverted as one task-scoped commit without schema or persistent-data
migrations.

## Progress

- [x] 2026-08-20 — Read repository instructions, Task 037, Task 035 baseline, simulation/evidence
  docs, and Task 013/018/020/027 implementation contracts; verified clean detached worktree.
- [x] 2026-08-20 — Created `task/037-simulation-demo-workflow` and this ExecPlan.
- [x] 2026-08-20 — Implemented the L0 artifact contract and assertion overlay over the existing
  Task 013 executor; focused tests prove same-seed byte replay and non-zero assertion failure.
- [x] 2026-08-20 — Implemented Isaac Sim 6 preflight/probe wrapping over the unchanged Task 027
  probe, stale-report invalidation, timeout, and strict actual-PhysX report validation.
- [x] 2026-08-20 — Added tests, docs, Make targets, and ran the available Python/example/Isaac
  checks; the live RTX 4080 run passed with actual PhysX.
- [ ] Commit, publish, review, merge, and verify default-branch synchronization.

## Decisions

- 2026-08-20 — Use one Python entry point on Windows and Linux so the L2 path can invoke the
  existing Task 027 Kit executable directly; keep the existing PowerShell probe unchanged.
- 2026-08-20 — Treat report paths and live Kit logs as operational outputs, not normalized replay
  inputs. Reports use repository-relative filenames so equivalent runs in different output roots
  compare byte-for-byte.
- 2026-08-20 — Keep the L0 demo nominal by default and support explicit assertion overlays rather
  than changing source scenarios or duplicating Task 036's qualification matrix.
- 2026-08-20 — Delete any prior Task 027 raw report before launching Kit so a probe that fails to
  write fresh evidence cannot accidentally pass from stale output.

## Results

Implemented `scripts/run_simulation_demo.py`, focused tests, Make targets, and the simulation demo
documentation. L0 runs the canonical `pen-nominal` behavior tree through the existing contract
mocks and writes deterministic report/trace/event/JUnit/log/replay artifacts. L2 launches the exact
Task 027 Isaac probe and emits the common contract only after validating Isaac 6, CUDA, actual
PhysX, runtime/adapter event origin, and 100 successful seeds. Both paths hard-code simulation-only
execution with no physical-operation authorization.

Available evidence on 2026-08-20: focused demo tests `5 passed`; full Python suite `455 passed,
1 skipped` (Windows directory-symlink privilege); Ruff format/check and strict mypy passed; example
validation passed with 10 canonical schemas, 7 component schemas, and 25 YAML documents. The live
L2 command passed with Isaac Sim `6.0.1-rc.7+release.42383.32955d8d.gl`, NVIDIA GeForce RTX 4080,
`actual_physx_executed: true`, `summary.passed: 100`, `summary.failed: 0`, and
`event_origin: runtime/adapters`. Literal `make` commands remain unavailable because GNU Make is
not installed on this Windows host; their locked interpreter equivalents were executed.

Commit/publication/merge verification remains pending.
