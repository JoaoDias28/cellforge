# Simulation demo workflow

Task 037 provides a small, reproducible demonstration of the reference pen cell. The command is
intentionally an engineering workflow: it shows the selected adapter backend and what evidence was
actually observed, but it cannot authorize a physical process.

## L0 contract demo

From the repository root:

```text
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --scenario nominal --seed 1001
```

This runs `cellforge_mock_adapters.headless.PenHeadlessExecutor`, which is the existing Task 013
L0 oracle for the canonical `examples/pen_engraving/behavior_tree.xml`. The runner validates the
canonical `cell.yaml`, scene, recipe, and scenario identity before executing. It does not require
ROS discovery, Isaac Sim, a GPU, hardware, or a cloud service.

The default artifact directory is:

```text
.artifacts/simulation-demo/l0/seed-1001/
```

The common contract is:

| File | Purpose |
| --- | --- |
| `report.json` | Evidence identity, source revision, input hashes, backend, adapters, fidelity, assertions, result, limitations, and safety boundary. |
| `trace.json` | Timestamp-free normalized trace from the existing L0 executor. |
| `events.json` | The same normalized event sequence as a discoverable event artifact. |
| `junit.xml` | Machine-readable assertion results. |
| `run.log` | Deterministic human-readable summary without wall-clock data. |
| `replay.txt` | Copyable replay command. |

The report uses repository-relative artifact names and stores SHA-256 identities for the source
revision, project manifest, `cell.yaml`, scene, behavior tree, recipe, selected scenario, and
adapter configuration. UUIDv5 trace and command IDs come from the existing seed-derived runner.
The wrapper may override the scenario seed, but it does not rewrite the source scenario.

To demonstrate a failed assertion while still capturing the run:

```text
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --scenario nominal --seed 1001 --assertion require-event:demo.event.missing
```

This command exits with status `1`; `report.json` contains `status: "failed"` and the failed
assertion. Additional assertion forms are `forbid-event:<event>` and
`final-status:<status>`. A malformed assertion exits with status `2` and does not claim success.

For a byte-level replay check on PowerShell:

```powershell
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --scenario nominal --seed 1001 --output-dir .artifacts/demo-a
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --scenario nominal --seed 1001 --output-dir .artifacts/demo-b
Compare-Object (Get-Content .artifacts/demo-a/trace.json) (Get-Content .artifacts/demo-b/trace.json)
Compare-Object (Get-Content .artifacts/demo-a/report.json) (Get-Content .artifacts/demo-b/report.json)
```

An empty `Compare-Object` result is expected. `run.log`, `replay.txt`, JUnit, trace, events, and
report are deterministic for the same checkout, scenario, and seed. Output directories are not
part of normalized evidence.

## Reusable kitting workflow

Task 038 adds a second workflow through the same demo surface. It is a two-part tray-kitting
sequence that resolves robot, gripper, camera, carrier, fixture, and read-only safety-status
contracts from the component manifests and canonical `cell.yaml`/USD identities. Run the nominal
path with:

```text
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --workflow kitting --scenario nominal --seed 3801
```

The default artifacts are written to `.artifacts/simulation-demo/kitting/l0/seed-3801/`. The
recovery scenario exercises one injected `gripper.motion.close_failed` fault, marks the generic
adapter ready, retries the pick, and records `fault.recovered`:

```text
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --workflow kitting --scenario gripper_close_recovery --seed 3802
```

Both reports include the canonical component-manifest, capability-contract, fault-catalog, scene,
recipe, tree, scenario, and adapter-configuration hashes, selected adapters, normalized trace,
assertions, limitations, and replay command. The kitting workflow is intentionally L0-only: it
proves declared contract reuse and deterministic sequencing, not geometry, kinematics, contact,
perception quality, hardware behavior, or functional safety.

Requesting a higher-fidelity kitting backend fails closed and writes an explicit unavailable report:

```text
uv run --frozen python scripts/run_simulation_demo.py --backend l2 --workflow kitting
```

The command must return non-zero. The report records that no genuine reusable kitting L1/L2
adapter is available; the pen-specific Task 027 Isaac path is never reused or relabeled for
kitting. The same limitation is recorded by the Task 036 qualification gate, while the existing
pen L2 qualification remains independent.

## Isaac Sim 6 L2 demo

On the supported Windows runner, use the same entry point:

```powershell
uv run --frozen python scripts/run_simulation_demo.py `
  --backend l2 `
  --isaac-sim-root C:\isaacsim
```

The wrapper performs local checks for:

* Isaac Sim 6 in `C:\isaacsim\VERSION`;
* `C:\isaacsim\kit\kit.exe` and the base Kit application;
* an NVIDIA GPU visible to `nvidia-smi`;
* the Task 027 probe's CUDA/PhysX checks inside Isaac Kit.

It then invokes the existing `scripts/verify_kit_l2_runtime.py` probe, which opens the canonical
scene, executes the seeded L2 adapter path, and writes the raw Task 027 report. The common L2
report is considered passed only if all of these are true:

* the probe reports an Isaac Sim 6 version;
* the GPU report is CUDA-backed;
* `actual_physx_executed` is `true`;
* runtime/adapter event origin is present;
* the required 100 seeded runs pass with zero failures.

The default artifacts are in `.artifacts/simulation-demo/l2/`. In addition to the common files,
the directory contains `task027-report.json`, `kit.stdout.log`, and `kit.stderr.log`. Kit logs are
diagnostic outputs and may contain wall-clock or machine-specific details; they are deliberately
not part of normalized replay comparison.

On Linux, use an Isaac Sim installation with the same `kit/kit` and `apps/isaacsim.exp.base.python.kit`
layout:

```bash
uv run --frozen python scripts/run_simulation_demo.py \
  --backend l2 \
  --isaac-sim-root /opt/isaacsim
```

The wrapper returns non-zero and writes an unavailable report when Isaac Sim 6, the GPU, or Kit
cannot be found. It returns non-zero and writes a failed report when the probe exits unsuccessfully,
the raw evidence is incomplete, or PhysX is not actually executed. CPU-model, mock, metadata-only,
or historical reports cannot be relabeled as L2 by this command.

## Evidence boundaries and troubleshooting

Every report contains these separate limitation categories:

* interface evidence — contract sequencing, configured adapter outcomes, assertions, and event
  origin;
* physics evidence — no claim at L0, and only the observed simplified OpenUSD/PhysX model at L2;
* process-quality evidence — no laser beam/material, optics, heat, text-fidelity, or mark-quality
  qualification;
* hardware evidence — no real-device commissioning or production qualification;
* safety evidence — modeled status is read-only and independent rated safety hardware remains
  authoritative.

Common failures:

* `L0 dependencies are unavailable`: run with the locked repository Python environment (`uv run
  --frozen`) and confirm the checkout is complete.
* `missing Isaac version file` or `Isaac Sim 6 required`: point `--isaac-sim-root` at the supported
  Isaac Sim 6 installation, not an older Kit release.
* `nvidia-smi did not report a GPU`: repair the NVIDIA driver/runtime or use the L0 command; no CPU
  fallback is accepted as an L2 pass.
* `actual_physx_executed` is false or the seed summary fails: inspect `kit.stdout.log`,
  `kit.stderr.log`, and `task027-report.json`; the common report remains failed.
* scenario or recipe identity errors: restore the canonical project files and rerun. Do not edit
  the behavior tree to make a demo pass.

Neither demo path selects `commissioning` or `production`, sends hardware commands, overrides an
interlock, or implements emergency stop, guard locking, safe stop, or laser enable. The output is
simulation-readiness evidence only and does not replace Task 036 qualification.
