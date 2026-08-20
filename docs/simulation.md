# Simulation and test scenarios

## 1. Adapter parity

Simulation and hardware adapters expose identical ROS contracts. They may differ internally, but the task tree must not branch on manufacturer or simulator identity except through declared capability metadata or execution mode.

## 2. Simulation architecture

```text
Behavior tree / skills / recipes
              │ ROS 2
      canonical device contracts
          /                 \
Isaac Sim adapters       contract mocks
```

Isaac Sim uses the ROS 2 bridge. Simulation control should be exposed to the test runner through ROS 2 simulation interfaces or a small studio service, allowing deterministic reset, pause, step, and scenario setup.

### 2.1 L0 contract mocks

The `cellforge_mock_adapters` package provides L0 (configurable timing, deterministic outcomes,
fault injection) mocks for the six reference device families: robot motion, gripper, fixture,
vision locator, process machine, and inspection. Each mock publishes canonical `DeviceState`,
serves the canonical ROS actions, and runs the generic adapter contract suite. Timing, outcomes,
and faults are selected purely by scenario configuration; no source changes are needed to inject
a fault.

Launch the complete mock cell on a Jazzy host:

```bash
ros2 launch cellforge_mock_adapters mock_cell.launch.py
```

L0 mocks have no geometry, physics, sensor data, or process-quality evidence. They implement
no safety-rated function and consume safety status as read-only configuration.

## 3. Scenario runner

The headless runner shall:

- load cell and scenario;
- set random seed;
- spawn products and apply variations;
- configure simulated device state;
- start trace capture;
- submit job;
- inject scheduled faults;
- wait for completion/timeout;
- evaluate assertions;
- save JUnit-compatible and domain reports.

The Task 013 L0 pen runner executes the canonical behavior-tree XML directly against contract
mocks, derives trace and command UUIDs from the recorded seed, and verifies normalized golden
traces. It intentionally runs without Isaac Sim, ROS discovery, a GPU, or hardware. This is fast
sequencing and interface evidence only; Task 018 owns Isaac scenario control and Task 020 owns the
physical pen simulation.

## 4. Initial fault library

- camera unavailable;
- stale image;
- object absent;
- pose outside correction limit;
- gripper close failure;
- dropped object;
- fixture seating failure;
- process machine not ready;
- process program missing;
- process timeout;
- inspection fail;
- robot path planning failure;
- robot protective stop status;
- communication loss;
- safety status unhealthy.

## 5. Randomization

Randomization must be bounded by explicit distributions in scenario files:

- product position and orientation;
- surface color/material visual variant;
- lighting intensity/direction;
- camera noise;
- friction and mass;
- component timing;
- network delay for non-real-time protocols.

Every failed run stores the seed for reproduction.

## 6. Fidelity honesty

Simulation evidence must state what is modeled and not modeled. For example, the laser simulation may validate command sequencing and timing but not prove mark quality. Physical process qualification remains required.

## 7. Performance tests

Measure separately:

- simulation wall-clock factor;
- motion-planning time;
- perception latency;
- end-to-end cycle time;
- event/trace overhead;
- job throughput;
- repeated-run variance.

## 8. Task 018 simulation control bridge

`cellforge_simulation` owns simulation lifecycle and scenario evidence behind a pure application
service. ROS 2 and Isaac Sim are thin adapters. Typed ROS services configure a scenario from a
project, register simulated adapters, reset/start/pause/step, inject test faults, capture canonical
`JobEvent` traces, evaluate assertions, and atomically store evidence.

Inside Isaac Sim, the Cell Studio extension hosts the ROS bridge and spins it from Kit's per-frame
main-thread update callback. ROS clients therefore remain transport-only while timeline, World
reset/step, and USD operations stay inside the Isaac runtime.

Configuration always loads component instance IDs from canonical `cell.yaml` and its referenced
canonical USD scene. Evidence freezes SHA-256 identities for both files and the scenario. Adapter
registration declares the immutable instance ID, canonical capabilities, ROS endpoint, and actual
fidelity. The requested fidelity is rejected when any required adapter is weaker; manifest claims
or a loaded USD file do not upgrade actual evidence.

The default ROS launch uses the L0 contract backend:

```bash
ros2 launch cellforge_simulation simulation_bridge.launch.py
```

Run the deterministic GPU-independent Task 018 acceptance path with:

```bash
make studio-simulation-check
```

It verifies reset ordering, exact same-seed setup, adapter registration, trace assertions, and
evidence at L0. It does not claim Isaac physics or rendered perception.

From an Isaac Sim 6 installation, after installing the locked CellForge and ROS 2 workspaces into
the Isaac Python environment, run the Kit backend probe on Windows with:

```powershell
isaac-sim.bat --no-window `
  --ext-folder C:\absolute\path\to\cellforge\src\kit `
  --enable cellforge.studio `
  --exec C:\absolute\path\to\cellforge\scripts\verify_kit_simulation.py
```

On Linux use `./isaac-sim.sh` and forward-slash absolute paths. The probe exercises a clean reset,
pause, single physics step, start, deterministic USD scenario metadata, and evidence storage. Task
020—not Task 018—owns physical pen manipulation. Neither backend implements or validates a
functional-safety function.

## 9. Task 019 motion planning

The supported reference six-axis model, SRDF safe states, KDL kinematics, OMPL pipeline, joint
limits, and ros2_control fake controller live in `cellforge_motion`. The deterministic headless
contract probe is:

```bash
make motion-service-check
```

On a ROS 2 Jazzy host, `make ros-build && make ros-test` builds the actual MoveIt/MTC adapter and
runs fake-backend tests for nominal, invalid, unreachable, collision, timeout, cancellation,
determinism, trace/evidence, scene, and controller failure paths. Plan-only is valid without
hardware. These checks provide motion contract/planning evidence only: they do not provide Isaac
physics, physical pen manipulation (Task 020), hardware accuracy, process quality, or independent
safety validation.

## 10. Task 020 physical pen manipulation

The reference USDA scene contains conservative internal analytic geometry for the six-axis robot,
parallel gripper, pen, input carrier, fixture, laser enclosure, and inspection camera. Collision
geometry and rigid-body metadata are authored explicitly. These shapes are approved simulation
placeholders, not vendor CAD, reach, payload, or dimensional-qualification evidence. Immutable
component instance IDs still pair the canonical `cell.yaml` operational graph with the canonical
USD spatial scene. Runtime pens live below `/World/SpawnedProducts` and do not mutate the
operational graph.

`cellforge_simulation.physical` provides deterministic bounds, seed replay, cycle state, stable
dropped-pen/failed-seating/collision faults, and planner-neutral Task 019 requests. The sequence is
pick, load, move to `process_safe`, process handshake/timing, then unload. The behavior tree owns
that sequence; MTC owns the internal pick/load/unload stage graph; the simulator owns product
physics and signals. Simulation and production adapters remain separate implementations of the
same capability contracts.

Run the CPU acceptance and reproducible 100-seed probe with:

```bash
make pen-physical-sim-check
uv run --frozen python scripts/run_pen_physical_report.py --seeds 100 --output /tmp/pen-report.json
```

The CPU report deliberately records `actual_physx_executed: false`; it proves bounded seeded
sampling, state/fault behavior, collision-result handling, and exact replay but is not L2 execution
evidence. From a supported Isaac Sim 6 installation, run the actual OpenUSD/PhysX probe on Windows:

```powershell
isaac-sim.bat --no-window `
  --ext-folder C:\absolute\path\to\cellforge\src\kit `
  --enable cellforge.studio `
  --exec C:\absolute\path\to\cellforge\scripts\verify_kit_pen_physical.py
```

Use `./isaac-sim.sh` and forward-slash paths on Linux. The probe opens the canonical scene, spawns a
rigid pen, creates/removes a fixed grasp joint, steps PhysX, and verifies seating and dropped-height
signals. Laser simulation covers readiness, command ordering, handshake, and timing only. It does
not model beam/material interaction, heat, plume, optics, engraving contrast, text fidelity, or
mark quality. Physical process qualification and independent functional-safety validation remain
required.

## 11. Task 025 fidelity selection

The reference offline runtime is explicitly L0. Its adapter configuration is immutable bundle
content and its deterministic motion backend validates scene identity, request contracts,
cancellation, and stable outcomes without claiming geometry or physics. Component manifests expose
only fidelity levels their selected entrypoint can actually provide.

Requesting L2 from the Task 025 bringup returns `bringup.fidelity.unavailable`; L0 behavior is never
relabelled as L2. Genuine Isaac Sim L2 composition remains Task 027 scope.

## 12. Task 033 software release qualification and simulation matrix

Task 033 qualifies the complete simulation stack across L0 and L2 fidelity:

- **Scenario matrix:** runs the complete 9-category scenario matrix (nominal, fault, cancel, timeout,
  restart, corrupt-bundle, offline-platform, stale-device, uncertain-process) deterministically with
  seed logging and trace event captures.
- **Tree and recipe parity:** statically and dynamically proves that the Behavior Tree XML and
  recipe YAML contain zero simulator-specific branches, executing identically across L0 and L2.
- **Strict fidelity labeling:** enforces that L2 simulation requires NVIDIA CUDA GPU and PhysX
  execution; CPU or mock execution is strictly labeled L0.
- **Mandatory disclaimers:** simulation status and evidence are engineering verification data only.
  Functional safety is independently enforced by rated hardware, and laser mark/material quality
  qualification requires physical commissioning in Task 034.

## 13. Task 037 simulation demo workflow

The supported one-command demonstration is `scripts/run_simulation_demo.py`. It is an engineering
demo wrapper around the existing Task 013 L0 runner and Task 027 Isaac Sim probe; it does not add a
second behavior-tree interpreter, qualification matrix, runtime, or safety controller.

Run the nominal L0 demo from a clean checkout on Windows or Linux with:

```text
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --scenario nominal --seed 1001
```

The default output directory is `.artifacts/simulation-demo/l0/seed-1001/`. It contains:

* `report.json` — the common machine-readable evidence report, including source revision, project,
  cell/scene/recipe/tree/scenario hashes, selected L0 adapters, fidelity, assertions, result,
  limitations, safety boundary, and replay command;
* `trace.json` and `events.json` — timestamp-free, seed-derived normalized events;
* `junit.xml` — assertion outcomes for CI/test tooling;
* `run.log` and `replay.txt` — a deterministic summary and copyable replay command.

The report references only repository-relative artifact names. Repeating the command with the same
seed produces byte-identical normalized report, trace, event, JUnit, log, and replay inputs. A
deliberately failing assertion is non-zero and is retained in the report:

```text
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --scenario nominal --seed 1001 --assertion require-event:demo.event.missing
```

Use `require-event:<event>`, `forbid-event:<event>`, or `final-status:<status>` for additional
machine-readable assertion checks. These overlays do not change the canonical scenario or tree.

The supported headless Isaac Sim 6 L2 demo invokes the unchanged Task 027 OpenUSD/PhysX probe:

```powershell
uv run --frozen python scripts/run_simulation_demo.py `
  --backend l2 `
  --isaac-sim-root C:\isaacsim
```

The runner requires an Isaac Sim 6 `VERSION`, the matching Kit executable/application, an NVIDIA
GPU visible to `nvidia-smi`, and the Task 027 runtime's CUDA/PhysX support. It writes
`.artifacts/simulation-demo/l2/report.json`, `trace.json`, `events.json`, `junit.xml`, `run.log`,
`replay.txt`, `task027-report.json`, and the Kit stdout/stderr logs. The L2 report passes only when
the probe reports Isaac 6, CUDA, `actual_physx_executed: true`, runtime/adapter event origin, and
100 successful seeded runs. Missing prerequisites, a probe error, a CPU-only result, or any failed
fidelity assertion writes an unavailable/failed report and returns non-zero.

On Linux, the same wrapper uses the supported `kit/kit` layout:

```bash
uv run --frozen python scripts/run_simulation_demo.py \
  --backend l2 \
  --isaac-sim-root /opt/isaacsim
```

The demo distinguishes interface evidence, physics evidence, process-quality evidence, hardware
evidence, and safety evidence in every report. L0 proves contract sequencing only. L2 proves only
the configured Isaac/PhysX model and its declared scenarios. Neither path qualifies a real device,
laser mark/material quality, commissioning, production operation, or independent functional safety;
`physical_operation_authorized` is always `false`.

## 14. Task 038 reusable tray-kitting workflow

The kitting example demonstrates that a second workflow can reuse the platform contracts without
copying the pen architecture. `examples/kitting/cell.yaml` is the operational graph and
`examples/kitting/scene.usda` is the spatial graph; immutable component instance IDs are checked
against both. Component manifests resolve behavior-tree ports to generic capability contracts,
frames, configuration schemas, and the shared fault catalog. The runner then maps those declared
ports to the existing Task 009 generic mock adapters.

The supported path is deterministic L0 contract-mock execution:

```text
uv run --frozen python scripts/run_simulation_demo.py --backend l0 --workflow kitting --scenario nominal --seed 3801
```

The nominal and `gripper_close_recovery` scenarios provide machine-readable report, trace, event,
JUnit, log, and replay artifacts. The recovery path proves explicit fault injection, adapter-ready
recovery, retry, and successful completion. No process machine, production authorization, rated
safety enforcement, or hardware driver is implemented.

There is no genuine reusable kitting L1/L2 adapter in this repository. An L2 request therefore
returns non-zero with a structured `unavailable` report. The existing Isaac Sim Task 027 path is
pen-specific and remains available only through the pen workflow; CPU mocks, metadata, or the pen
adapter cannot be relabeled as kitting L2 evidence.
