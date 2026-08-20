# Task 038 — Reusable kitting simulation workflow

## Goal

Add a useful non-pen pick-and-place/kitting project that exercises the existing component,
capability, port, frame, recipe, behavior-tree, L0 adapter, demo, and qualification contracts.
The workflow must produce deterministic engineering evidence while remaining explicit that no
physical process, hardware, or functional-safety claim is made.

## Scope

Included: a canonical kitting cell/project, reusable component manifests and configuration
schemas, versioned capability contracts and fault catalog, a minimal USD scene, a generic
contract-driven deterministic L0 executor, nominal and recovery scenarios, demo integration,
Task 036 observed qualification integration, tests, and documentation.

Excluded: real hardware drivers, commissioning, production authorization, safety enforcement,
new ROS/public schema versions, Isaac-specific workflow branches, and an invented L1/L2 result.

## Current state

Task 036 and Task 037 are merged on the baseline. The existing demo wraps the Task 013
pen-specific L0 oracle and writes normalized evidence; the qualification runner invokes the
headless pen suite and records observed artifacts. Task 009 already provides reusable robot,
gripper, fixture, vision-locator, and inspection L0 adapter contracts with strict payload and
fault validation. The domain schemas support the required component kinds, frames, ports,
capabilities, adapters, and scenarios without a schema migration.

## Design

1. Define `examples/kitting` as a self-contained canonical project. Its cell graph uses stable
   instance IDs shared by `scene.usda`, reusable generic robot/gripper/vision/fixture/carrier
   manifests, declared frames and software ports, configuration schemas, capability-contract
   documents, and fault catalogs. A project validator checks manifest identity/version, instance
   configuration, scene instance IDs/prim references, frame references, declared tree ports, and
   recipe capabilities together.
2. Add a contract-driven `KittingHeadlessExecutor` beside the existing pen oracle. It reads the
   canonical tree and resolves every executable tree port to a declared component capability;
   only the existing generic L0 mock adapter contracts are used. Two parts are located, picked,
   placed into declared kit slots, inspected, and released. A scheduled first-attempt gripper
   fault uses the tree retry branch and emits deterministic recovery evidence.
3. Extend `run_simulation_demo.py` with `--workflow kitting` and generalized canonical input
   inventory/hashing. The same artifact schema records component/capability/fault/config hashes,
   selected adapters, L0 fidelity, assertions, limitations, and replay instructions. Requesting
   L2 for kitting writes `UNAVAILABLE`, returns non-zero, and states that no kitting L1/L2 adapter
   or PhysX probe exists; no CPU result is relabeled.
4. Extend Task 036 qualification with an observed kitting demo gate in the standard release
   qualification command. It is additive to the pen scenario model and fails the qualification
   when the observed kitting nominal/recovery evidence is absent or invalid. The existing L2
   validation remains unchanged and external.
5. Update Make/CI-facing documentation and tests. Do not add dependencies or alter canonical
   ROS/schema versions; all generated evidence is ignored and reproducible from source.

## Work sequence

1. Create this plan and the canonical kitting source artifacts; acceptance: schema validation and
   project cross-reference checks reject bad IDs/config/frames/ports and accept the source.
2. Implement the contract-driven L0 executor and demo workflow selector; acceptance: nominal and
   one scheduled gripper-fault/retry scenario pass with stable traces and invalid input fails.
3. Integrate the workflow into qualification and higher-fidelity unavailable handling; acceptance:
   the qualification records observed kitting artifacts and kitting L2 cannot pass without a
   genuine adapter.
4. Add focused/full tests, docs, Make targets, and run the required validation matrix; acceptance:
   same-seed artifacts are byte-identical and failed assertions return non-zero.
5. Inspect only Task 038 changes, commit as `task(038): add reusable kitting simulation workflow`,
   publish a ready PR, wait for all required checks, merge, and verify local/remote `main`.

## Validation

- Kitting project/manifest/config/capability/fault/scene cross-reference tests.
- Kitting nominal, invalid input, scheduled fault/retry recovery, same-seed replay, failed
  assertion, and unavailable higher-fidelity tests.
- `make lint`, `make test`, `make validate-examples`, focused demo/qualification checks, and
  `make ros-build`/`make ros-test` where the environment supports them.
- Isaac Sim 6 integration is unavailable for kitting unless a genuine reusable adapter is added;
  the test must exercise the fail-closed unavailable path rather than fabricate L2 evidence.
- `git diff --check`, staged checks, post-commit status/log, hosted CI, and mergeability.

## Risks and rollback

The main risk is accidentally coupling the new tree to the pen oracle or claiming fidelity that
the selected adapters do not provide. The validator and evidence report bind tree ports to
declared contracts, while the demo hard-codes L0 as the achieved fidelity and rejects kitting L2.
The task is additive and can be reverted as one commit without schema or persistent-data
migrations. No application code enforces rated safety; the safety component is modeled read-only.

## Progress

- [x] 2026-08-20 — Verified clean merged Task 036/037 baseline, prerequisite history, repository
  instructions, schemas, simulation contracts, and demo/qualification extension points.
- [x] 2026-08-20 — Add and validate canonical kitting source artifacts and ExecPlan implementation.
- [x] 2026-08-20 — Implement deterministic contract-driven L0 execution, recovery, and demo path.
- [x] 2026-08-20 — Integrate observed qualification evidence and unavailable higher-fidelity path.
- [ ] 2026-08-20 — Run publication, merge, and default-branch synchronization checks.

## Decisions

- 2026-08-20 — Select two-part tray kitting because it is useful pick-and-place work and reuses
  generic robot, gripper, vision, fixture, and inspection contracts without process-machine or
  pen-specific semantics.
- 2026-08-20 — Use L0 only for the new workflow. Existing generic Isaac/PhysX probes are tied to
  the reference pen/Task 027 path, so kitting L2 is unavailable until a genuine adapter exists.
- 2026-08-20 — Keep Task 036 integration additive through an observed demo gate so existing
  callers and the nine-category pen qualification schema remain backward-compatible.

## Results

- Canonical kitting validation passes for the cell/USD identity pair, six component manifests,
  thirteen configuration schemas, eight capability contracts, and one fault catalog. Capability
  documents intentionally omit the unsupported top-level `$schema` property required by the
  repository capability schema.
- Nominal seed 3801 and gripper recovery seed 3802 complete through the existing generic L0 mock
  adapter contracts. Same-seed normalized artifacts are byte-identical; failed assertions return
  non-zero; the kitting L2 request writes a structured unavailable report and returns non-zero.
- Task 036 qualification now records observed kitting nominal and recovery command/report hashes as
  an additive `kitting_workflow_l0` gate. The pen Task 027 L2 validation remains independent.
- Locked-interpreter validation: root example validation passed; full Ruff format/check passed;
  strict repository and Studio mypy passed; focused Task 038/demo/qualification tests passed; the
  clean full suite passed 464 tests with 2 platform-expected skips. `make` and `colcon` are not
  installed on this Windows host, so Make/ROS targets remain unavailable; selected kitting L2 and
  Isaac integration are not applicable because no genuine higher-fidelity kitting adapter exists.
- Publication and merge results remain pending.
