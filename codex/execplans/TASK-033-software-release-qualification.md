# Task 033 — Complete software release qualification

## Goal
Prove the complete simulation-first industrial robot cell software platform across clean engineering, platform, and cell runtime environments: executing an automated end-to-end Studio-to-L0/L2-to-evidence-to-signed-bundle-to-runtime qualification workflow, qualifying all required nominal and failure scenarios (nominal, fault, cancel, timeout, restart, corrupt-bundle, offline-platform, stale-device, uncertain-process), proving that one behavior tree and recipe execute across L0 and L2 without simulator-specific workflow branches, generating an Ed25519-signed software release qualification report with complete provenance and explicit limitations, and updating all documentation, operator/recovery guides, roadmap, and repository status to unlock Task 034.

## Scope
Included:
- Automated end-to-end qualification pipeline integrating:
  1. Studio scene, component, connection, task, recipe, calibration, and scenario inspection.
  2. Multi-fidelity scenario execution across L0 contract simulation and L2 Isaac physical simulation with seed control and fidelity limits enforcement.
  3. Structured, content-addressed evidence record generation and Ed25519 signing.
  4. Platform recipe approval lifecycle enforcing dual-role non-self signoff.
  5. Deterministic cell compilation with evidence-policy enforcement producing immutable bundle manifests.
  6. Bundle assembly, checksum inventory generation, and detached Ed25519 bundle signing.
  7. Bundle agent deployment, preflight validation, checksum/signature verification, atomic activation, and health checks.
  8. ROS 2 runtime stack boot, job gateway freezing, BehaviorTree.CPP supervisor execution, state aggregation, operator API endpoints, and monotonic trace event generation.
  9. Production result and trace persistence in local SQLite stores and idempotent batch synchronization with platform services.
- Comprehensive qualification scenario matrix:
  1. `nominal`: complete end-to-end pen engraving cycle with full trace capture and golden trace match.
  2. `fault`: injected equipment and sensor failure paths (laser unready, fixture seating failed, vision inspection mismatch, pen dropped, motion collision) entering defined fault states.
  3. `cancel`: operator cancellation mid-cycle safely halting motion, releasing resources, canceling action goals, and restoring clean state.
  4. `timeout`: execution timeout (laser process timeout) triggering bounded abort and entering recoverable fault.
  5. `restart`: runtime/service restart or rollback restoring clean state machine and accepting subsequent jobs idempotently.
  6. `corrupt-bundle`: bundle tampering (modified files, invalid SHA-256, forged or corrupted signatures) failing closed during compiler and agent preflight.
  7. `offline-platform`: cell runtime operating fully offline without platform services, buffering jobs and traces, and synchronizing idempotently upon reconnection.
  8. `stale-device`: required device or safety heartbeat loss/unready state causing immediate job refusal and fault transition.
  9. `uncertain-process`: communication loss during irreversible process execution entering `OUTCOME_UNKNOWN` without unsafe automatic retry.
- Parity proof verifying that `examples/pen_engraving/behavior_tree.xml` and `examples/pen_engraving/recipe.yaml` run in L0 and L2 without simulator-specific workflow branches or conditionals.
- Cryptographically signed software release qualification report (`SoftwareReleaseQualificationReport`) capturing exact Git revisions, bundle IDs, component versions, recipe versions, seeds, scenario matrix results, and explicit limitations (functional safety disclaimer, laser mark/material quality disclaimer, hardware qualification deferred to Task 034).
- Acceptance probe script `scripts/verify_software_release_qualification.py` and Makefile/CI targets.
- Comprehensive documentation updates across `README.md`, `ROADMAP.md`, `CODEX_TASK_INDEX.md`, `docs/architecture.md`, `docs/cell-runtime.md`, `docs/cell-studio.md`, `docs/deployment.md`, `docs/developer-setup.md`, `docs/observability.md`, `docs/safety-security.md`, `docs/simulation.md`, `docs/testing.md`, and operator recovery procedures.

Excluded:
- Physical hardware execution or real equipment commissioning (strictly deferred to Task 034).
- Functional-safety implementation in general-purpose software (safety enforcement belongs strictly to external rated hardware).
- Simulating laser beam/material physics or mark metallurgical properties.
- Modifying immutable historical task commits or altering backward-compatible schemas.

## Current state
- Tasks 001 to 032 are complete and merged in Git history.
- Task 006 provides the deterministic cell compiler in `cellforge_bundle.compiler`.
- Task 011 provides the BehaviorTree.CPP supervisor in `cellforge_supervisor`.
- Task 023 provides execution contracts, frozen job identity, and monotonic trace models in `cellforge_state_trace`.
- Task 024 provides the canonical pen runtime on BehaviorTree.CPP.
- Task 025 provides integrated offline runtime bringup in `cellforge_bringup`.
- Task 026 provides signed installable bundle assembly and `BundleAgent` in `cellforge_bundle`.
- Task 027 provides genuine Isaac Sim 6 L2 runtime integration.
- Task 028 provides Studio spatial configuration and USDA scene calibration round trips.
- Task 029 provides Studio task and recipe authoring.
- Task 030 provides Studio deployment and evidence workflows.
- Task 031 provides platform registry and artifact services.
- Task 032 provides platform approvals, evidence snapshots, and production result synchronization.

## Design
### Qualification Data Model & Report Generator
- `cellforge_bundle.qualification` module:
  - `ScenarioQualificationResult`: records scenario ID, category, requested/achieved fidelity, seed, duration, trace event count, final status, passed/failed, and failure reasons.
  - `ParityVerificationResult`: records AST/element analysis of behavior tree XML and recipe YAML confirming zero simulator-specific branches, and runtime equivalence across L0 and L2.
  - `SoftwareReleaseQualificationReport`: canonical Pydantic model capturing:
    - Qualification metadata (id, timestamp, suite version, qualifier identity).
    - Source control provenance (git revision, tree SHA, repo URL, dirty status).
    - Cell identity (`0d3c6b63-a57f-4207-8638-e4cf76efec90`, name, cell.yaml SHA-256, scene.usda SHA-256).
    - Component manifest inventory (IDs, versions, support levels, SHA-256 digests).
    - Recipe identity (ID, version, status, SHA-256, dual-role approval ledger).
    - Compiled bundle manifests (L0 bundle ID, L2 bundle ID, signatures, public key ID).
    - Scenario execution matrix for all 9 required categories (nominal, fault, cancel, timeout, restart, corrupt-bundle, offline-platform, stale-device, uncertain-process).
    - Parity verification proof (L0 vs L2).
    - Platform verification proof (migrations, synchronization idempotency).
    - Explicit limitations and disclaimers (safety boundary, laser process physics disclaimer, hardware deferral to Task 034).
    - Ed25519 signature of the canonical JSON representation.

### Automated End-to-End Qualification Runner
- `run_software_release_qualification(...)`:
  1. Opens project via Studio services, verifies spatial scene USDA transforms and component placements.
  2. Executes qualification scenario matrix across L0 and L2 with seed control and fidelity validation.
  3. Generates signed evidence records (simulation, calibration, commissioning, safety-review) via `cellforge_platform.auth.signing.PlatformSigner`.
  4. Publishes recipe and records two distinct approvals from distinct authorized roles (`process_engineer` + `automation_engineer` / `administrator`) while rejecting author self-approval.
  5. Compiles project in production mode with evidence-policy enforcement, producing immutable bundle manifest.
  6. Assembles signed installable deployment bundle with full checksum inventory and detached Ed25519 signature.
  7. Deploys bundle via `BundleAgent`, verifying checksums and detached signatures, activates `current` symlink, and runs preflight checks.
  8. Boots offline runtime graph (`cellforge_bringup`), submits frozen jobs via `cellforge_job_gateway`, executes BehaviorTree.CPP supervisor, checks device readiness, verifies operator API endpoints, and asserts trace events.
  9. Verifies local SQLite persistence during offline operation, restarts platform service, and executes idempotent batch synchronization (`POST /api/v1/sync/batch`).
  10. Generates, signs, and validates the complete `SoftwareReleaseQualificationReport`.

### Parity Verifier
- `verify_tree_and_recipe_parity(...)`:
  - Parses `behavior_tree.xml` and validates all nodes are capability/skill leaves or standard BT control nodes without conditional simulator branches (no `IfSim`, `IfL0`, `IfL2`, `IfHardware`).
  - Validates `recipe.yaml` contains only operational parameters and limits without simulation-specific flags.
  - Verifies identical node execution sequences and event traces across L0 and L2 runs.

## Work sequence
1. Implement `cellforge_bundle.qualification` containing models, scenario executors, parity checkers, report generators, and signers.
2. Implement comprehensive qualification test suite in `src/python/cellforge_bundle/tests/test_qualification.py` and `tests/test_software_release_qualification.py`.
3. Create acceptance probe script `scripts/verify_software_release_qualification.py`.
4. Update `Makefile` with `release-qualification-check` target and `.github/workflows/ci.yml`.
5. Update all documentation files:
   - `docs/architecture.md`
   - `docs/cell-runtime.md`
   - `docs/cell-studio.md`
   - `docs/deployment.md`
   - `docs/developer-setup.md`
   - `docs/observability.md`
   - `docs/safety-security.md`
   - `docs/simulation.md`
   - `docs/testing.md`
   - `README.md`
   - `ROADMAP.md`
   - `CODEX_TASK_INDEX.md`
   - `codex/tasks/TASK-033-software-release-qualification.md`
6. Run full verification: `make lint`, `make test`, `make validate-examples`, `make release-qualification-check`, `make ros-build`, `make ros-test`.
7. Generate signed qualification report artifact.
8. Commit, push branch, open PR, verify CI checks pass, merge PR, fast-forward main, and generate final report.

## Validation
- `uv run --frozen python scripts/verify_software_release_qualification.py`
- `uv run --frozen pytest --basetemp .pytest-tmp-task033 -o cache_dir=.pytest-cache/task033`
- `uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving`
- `uv run --frozen ruff format --check .`
- `uv run --frozen ruff check .`
- `uv run --frozen mypy ...`
- Windows ROS build and tests: `scripts/run_ros_windows_build.ps1` and `scripts/run_ros_windows_tests.ps1`.

## Risks and rollback
- Risk: Divergence between L0 and L2 execution causing tree or recipe specialization.
  - Mitigation: Abstract all capabilities through ROS interfaces and verify tree/recipe ASTs and traces with zero simulator branches.
- Risk: Incomplete qualification matrix missing subtle failure modes.
  - Mitigation: Explicitly model, test, and assert all 9 required scenario categories (nominal, fault, cancel, timeout, restart, corrupt-bundle, offline-platform, stale-device, uncertain-process).
- Rollback: Revert task branch commits without touching earlier tasks.

## Progress
- [x] 2026-08-18 — Checked out `task/033-software-release-qualification` from `main`, verified prerequisite commits (025-032).
- [x] 2026-08-18 — Implement `cellforge_bundle.qualification` module and data models.
- [x] 2026-08-18 — Implement qualification test suites and verification probe `scripts/verify_software_release_qualification.py`.
- [x] 2026-08-18 — Update `Makefile` and `.github/workflows/ci.yml`.
- [x] 2026-08-18 — Update all architecture, runtime, studio, deployment, safety, simulation, testing, operator/recovery docs, README, ROADMAP, and CODEX_TASK_INDEX.
- [x] 2026-08-18 — Run full test suite, linting, ROS tests, and qualification acceptance probe.
- [ ] 2026-08-18 — Commit, push, open PR, verify CI, merge, and output final report.

## Decisions
- 2026-08-18 — Qualification reports are cryptographically signed using Ed25519 over canonical JSON, providing verifiable proof of software release readiness without modifying canonical schemas.
- 2026-08-18 — Parity verification analyzes behavior tree XML and recipe YAML statically and dynamically, ensuring zero simulator-specific branches exist.
- 2026-08-18 — All 9 required qualification categories (nominal, fault, cancel, timeout, restart, corrupt-bundle, offline-platform, stale-device, uncertain-process) are explicitly captured in the qualification matrix.

## Results
- Implemented `cellforge_bundle.qualification` module and data models (`SoftwareReleaseQualificationReport`, `ScenarioQualificationResult`, `ParityVerificationResult`, `PlatformQualificationResult`).
- Verified Behavior Tree and recipe parity across L0 and L2 with zero simulator-specific branches.
- Implemented and qualified all 9 scenario categories (nominal, fault, cancel, timeout, restart, corrupt-bundle, offline-platform, stale-device, uncertain-process).
- Created CLI qualification command `cellforge qualify` and acceptance probe `scripts/verify_software_release_qualification.py`.
- Verified 442 unit and integration tests, clean linting (`ruff`), strict type checking (`mypy`), and 104 ROS C++ / Python tests with 0 failures.
- Generated and cryptographically signed the canonical `SoftwareReleaseQualificationReport` artifact under `examples/pen_engraving/reports/software_release_qualification_report.json`.
- Updated all architecture, runtime, studio, deployment, safety, simulation, testing, developer docs, README, ROADMAP, and task index, marking Task 034 eligible.
