# Task 030 — Studio deployment and evidence workflow

## Goal
Complete the engineering workflow in Cell Studio from runtime-backed scenario execution, fault injection, timeline inspection, replay, and deterministic evidence generation through signed bundle assembly, target compatibility preflight, deterministic diffing, signature verification, and fail-closed install and rollback.

## Scope
Included:
- Scenario discovery, inspection, submission, parameter overrides, and runtime execution across L0 functional/contract scenarios and L2 physical scenarios.
- Live and recorded event timeline scrubbing, tracing, and deterministic replay verification.
- Evidence generation, storage, and structured inspection with canonical project hashes, test assertions, seed tracking, and mandatory functional safety disclaimers.
- Strict fidelity labeling and enforcement: verifying that L0 mock sequencing or CPU-only runs cannot be presented as L2 PhysX/GPU evidence, and that requesting unsupported fidelity fails closed.
- Deployment profile discovery, inspection, and schema-validated configuration.
- Signed bundle assembly producing immutable, content-addressed release directories with Ed25519 signatures and checksum inventories.
- Deterministic bundle diff engine comparing candidate bundles or working project against active releases or predecessor bundles across manifest, file digests, configs, recipes, tasks, calibrations, and target profiles.
- Ed25519 signature verification against trusted key stores, detecting invalid keys, missing signatures, or tampered file inventories.
- Target compatibility preflight checking target facts (architecture, OS, ROS distribution, GPU, native packages, runtime entrypoints).
- Bundle agent status, fail-closed installation, prepare-active boot guard, and safe rollback coordination.
- Strict application-service boundaries for all UI operations, ensuring all business logic is headless-testable without Omniverse Kit or GPU.
- Omniverse Kit UI panel integration for Scenario & Simulation Control, Evidence Inspection, and Deployment / Release Management.
- Deterministic test suites and end-to-end verification script.

Excluded:
- Implementing safety logic in Python or simulation (safety remains independently enforced on rated hardware).
- Modifying production runtime packages with Studio dependencies (Studio remains an authoring/engineering tool only).
- Bypassing signature verification or target compatibility during bundle installation.

## Current state
- Tasks 015–017 provide project round-trips, component placement, and typed connection authoring.
- Task 018 provides ROS 2 simulation bridge services (`ConfigureSimulation`, `ControlSimulation`, `InjectSimulationFault`, `FinalizeSimulation`) and pure `SimulationApplication`.
- Task 020 & Task 027 provide physical pen manipulation simulation, PhysX backend, and Isaac Sim L2 runtime integration.
- Task 021 & Task 026 provide `BundleAgent`, `assemble_bundle`, Ed25519 detached signing (`signature.json`), and target preflight (`preflight_target`).
- Tasks 028–029 provide spatial configuration, calibration binding, BehaviorTree.CPP task authoring, and schema-driven recipe authoring with lifecycle management.
- Reference project `examples/pen_engraving` contains 10 L0 functional scenarios, 4 L2 physical scenarios, and 2 deployment profiles (`deployment-sim.yaml`, `deployment-l2.yaml`).

## Design
### Scenario and Evidence Service (`ScenarioEvidenceService`)
- Discovers scenarios listed in `cell.yaml` and loaded project artifacts (`scenarios/*.yaml`, `physical/scenarios/*.yaml`).
- Parses and validates scenario definitions, initial states, seeds, timeout, randomization distributions, scheduled faults, assertions, and requested fidelity (`L0`, `L1`, `L2`, `L3`).
- Submits scenario configurations to simulation backends (ROS 2 simulation client or in-process simulation service).
- Manages fault injection: scheduled triggers or dynamic runtime injection targeting required cell components or the operator.
- Maintains and streams `SimulationTraceEvent`s (sequence, event_type, component_instance_id, result_code, payload) for live timeline visualization.
- Replays recorded simulation runs, verifying deterministic event ordering and hash matching against original evidence.
- Finalizes and inspects `cellforge.simulation_evidence` JSON documents, validating canonical project & scene hashes, test assertion outcomes, randomization samples, and trace events.
- Enforces strict fidelity labeling:
  - Verifies achieved fidelity matches adapter capabilities.
  - Refuses to report L2 if running on L0 mock adapters or CPU-only backends without GPU/PhysX.
  - Emits explicit limitations and the mandatory functional safety disclaimer:
    `"Simulation status and evidence are standard-control engineering data only. Functional safety remains independently enforced and validated by rated hardware."`

### Deployment and Bundle Service (`DeploymentService`)
- Discovers and inspects deployment profiles declared in `cell.yaml` / project (`deployment_profiles`).
- Assembles signed installable bundles using `cellforge_bundle.assembly.assemble_bundle` with target profile, execution mode, source revision, output directory, and Ed25519 signing key.
- Computes deterministic structured diffs between candidate bundles and active installed releases (or reference bundles) across:
  - Manifest metadata (bundle ID, target profile, execution mode, source revision);
  - Files inventory (added, removed, modified files with SHA-256 and byte sizes);
  - Configuration files (`cell.yaml`, device configs, behavior trees, secret references);
  - Recipes and calibrations;
  - Target profiles and runtime entrypoints;
  - Evidence summaries.
- Verifies Ed25519 signatures against trusted public keys (`/etc/cellforge/trusted-keys/<key_id>.pub` or configured directory), returning structured verification status.
- Performs target compatibility preflight against target facts (`target.json`), checking platform architecture, OS, ROS distro, GPU requirements, native packages, external prerequisites, and runtime entrypoints.
- Manages bundle installation and rollback using `BundleAgent`, inspecting active/previous/candidate releases and deployment event journals.

### Studio Application and UI Integration
- Extends `ProjectBackend` and `ProjectCommandService` with pure scenario, evidence, and deployment operations.
- Extends `StudioApplication` with snapshot state holding:
  - `scenario_view`: available scenarios, selected scenario, parameter overrides, detail view.
  - `simulation_view`: simulation client state, controls, event timeline, fidelity badge & limitations, safety disclaimer.
  - `evidence_view`: available evidence files, selected evidence detail, project/scene hashes, assertions summary.
  - `deployment_view`: deployment profiles, candidate bundle assembly, deterministic diff viewer, signature verification status, target compatibility checklist, bundle agent status, install and rollback controls.
- Updates Omniverse Kit UI panels in `extension.py`:
  - Simulation & Scenario Panel: scenario selector, seed/parameter config, play/pause/step/reset, fault injection, event timeline, replay, fidelity badge, safety disclaimer.
  - Evidence Panel: evidence history, project/scene SHA-256 verification, assertions breakdown, trace viewer.
  - Deployment Panel: target profile selector, bundle assembly, Ed25519 signing, diff viewer vs active release, signature status, target compatibility checklist, agent status, install and rollback triggers.

## Work sequence
1. Implement `ScenarioEvidenceService` with scenario discovery, parsing, submission, fault injection, timeline tracing, replay verification, evidence generation/inspection, and strict fidelity labeling.
2. Implement `DeploymentService` with deployment profile inspection, bundle assembly, deterministic diff engine, Ed25519 signature verification, target compatibility preflight, and bundle agent install/rollback coordination.
3. Integrate services into `ProjectCommandService`, `ProjectBackend`, `StudioApplication`, and Kit UI panel renderers in `extension.py`.
4. Implement unit and contract test suites in `src/kit/cellforge.studio/tests/` covering scenario management, timeline, replay, evidence inspection, fidelity enforcement, bundle assembly, diffing, signature checks, compatibility preflight, and deployment operations.
5. Create comprehensive acceptance verification script `scripts/verify_studio_deployment_evidence.py`.
6. Run all repository checks: `ruff`, `mypy`, `pytest`, `validate-examples`, and the acceptance verification script.
7. Commit, push branch, open pull request, verify CI checks pass, and merge to `main`.

## Validation
- `uv run --frozen pytest --basetemp .pytest-tmp -o cache_dir=.pytest-cache/task030 src/kit/cellforge.studio/tests`
- `uv run --frozen python scripts/verify_studio_deployment_evidence.py`
- `uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving`
- `uv run --frozen ruff format --check .`
- `uv run --frozen ruff check .`
- `uv run --frozen mypy ...`
- Local Git verification: `git status --short`, `git log -1 --oneline`.

## Risks and rollback
- Risk: Bundle assembly or agent operations could attempt to write outside designated output or test directories.
  - Mitigation: Enforce strict path resolution, sandboxing, and validation in `DeploymentService`.
- Risk: Incomplete fidelity validation could allow L0/CPU mock runs to be mislabeled as L2.
  - Mitigation: Require explicit verification of adapter capabilities and backend physical execution before recording or displaying achieved fidelity.
- Risk: Incompatible bundle diffing could miss subtle configuration changes.
  - Mitigation: Implement canonical JSON/YAML parsing and line/field-level diffing in addition to SHA-256 file inventory comparison.
- Rollback: Revert task branch commits without affecting existing tasks.

## Progress
- [x] 2026-08-17 — Synced with default branch, created task branch `task/030-studio-deployment-evidence`, verified prerequisite commits (026, 027, 029 in history).
- [x] 2026-08-17 — Executed baseline tests and verified example schemas.
- [x] 2026-08-17 — Implement `ScenarioEvidenceService` and fidelity verification.
- [x] 2026-08-17 — Implement `DeploymentService`, deterministic diff, and signature/agent coordination.
- [x] 2026-08-17 — Integrate services into `ProjectCommandService`, `StudioApplication`, and `extension.py`.
- [x] 2026-08-17 — Add unit, contract, and acceptance test suites.
- [x] 2026-08-17 — Run full lint, type checks, test suite, and verification script.
- [ ] 2026-08-17 — Commit, push, open PR, verify CI, and merge.

## Decisions
- 2026-08-17 — Separate scenario/evidence operations into `scenario_service.py` and deployment/bundle operations into `deployment_service.py`, maintaining clear separation of concerns and headless testability.
- 2026-08-17 — Require explicit fidelity categorization (`L0` mock sequencing, `L1` kinematics, `L2` PhysX GPU, `L3` rendered perception) and refuse to claim L2 without verified Isaac Sim GPU PhysX execution.
- 2026-08-17 — Build deterministic bundle diffing by combining manifest-level field diffs, file inventory changes, and deep configuration diffs.

## Results
- Scenario discovery, parameter inspection, seed control, timeline tracing, fault injection, deterministic replay, and `cellforge.simulation_evidence` artifact generation implemented in `ScenarioEvidenceService`.
- Strict fidelity enforcement implemented: L0 mock adapters or CPU-only backends cannot claim L2 and fail closed with `simulation.fidelity.unsupported`.
- Mandatory functional safety disclaimer attached to all simulation and evidence views and records.
- Deployment profile discovery, Ed25519-signed bundle assembly, deterministic deep diffing, detached signature verification against trusted public keys, target compatibility preflight, and bundle agent install/rollback coordination implemented in `DeploymentService`.
- Omniverse Kit presentation and application layer integrated with thin callbacks and pure service delegation.
- 84 unit and contract tests in `src/kit/cellforge.studio/tests/` passed.
- 401 tests across the entire repository passed (1 skipped for Windows non-elevated directory symlink).
- Acceptance probe `scripts/verify_studio_deployment_evidence.py` verified end-to-end scenario execution, timeline generation, replay, fidelity enforcement, bundle assembly, diffing, signature verification, compatibility preflight, and deployment status querying.
