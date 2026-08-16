# cellforge_simulation

Task 018 provides a pure deterministic simulation lifecycle and evidence service with thin ROS 2
and Isaac Sim 6 adapters. The ROS node exposes `/simulation/configure`, `/simulation/control`,
`/simulation/register_adapter`, `/simulation/inject_fault`, and `/simulation/finalize`.

Task 020 adds the ROS/Kit-free `physical` cycle model and the thin `pen_physics_backend` Isaac Sim
6 adapter. The former is deterministic CPU evidence; the latter is the only implementation here
that may report actual OpenUSD/PhysX execution. Both preserve the Task 019 planner-neutral motion
contract and never implement production control or functional-safety enforcement.

Task 027 adds `isaac_l2_adapter`, a Kit-hosted ROS process that exposes the canonical robot,
gripper, fixture, process-handshake, vision/inspection, and modeled safety-state contracts. Its
success and fault results come from OpenUSD prim state and PhysX attachment/contact/height
observations. The external scenario client may configure seeds and declared faults, but it cannot
publish adapter success events. `MoveItPlanner` forwards completed MoveIt/MTC work to this adapter
before the motion action succeeds.

On Windows 11, install the maintained `IsaacSim-ros_workspaces` Jazzy Pixi environment documented
by NVIDIA, build this repository's `ros_ws`, and launch the L2 bundle. Run the direct GPU gate with:

```powershell
powershell -File scripts/run_isaac_l2_gpu.ps1
```

That runner rejects non-6.x Isaac versions and unavailable CUDA, executes 100 seeded adapter
cycles plus physical drop, seating, and collision faults, and writes replayable JSON evidence.
With the integrated runtime running, submit the nominal cycle plus each L2 physical fault scenario
through the public action:

```powershell
python scripts/run_isaac_l2_runjob_acceptance.py `
  --project examples/pen_engraving --report .artifacts/task027/runjob-report.json
```

The canonical operational graph is always loaded from the selected project's `cell.yaml`; its
referenced USD file remains the canonical spatial scene. Both content hashes are frozen into every
evidence report. Simulated devices self-register immutable component instance IDs, canonical
capabilities, endpoints, and achieved fidelity. Their capability actions/services are the same
contracts used by hardware adapters.

The default launch path is deliberately L0 contract control:

```bash
ros2 launch cellforge_simulation simulation_bridge.launch.py
```

Launch the bridge together with all six Task 009 mock nodes (the camera instance has separate
locate and inspect endpoints, both registered under the same immutable instance ID):

```bash
ros2 launch cellforge_simulation contract_scenario.launch.py
```

It records setup/control/fault/trace behavior but does not provide kinematics, physics, rendered
perception, process quality, hardware, or safety evidence. An Isaac Sim 6 host can construct the
node with the `isaac` backend; that backend maps reset/play/pause/step to the supported Isaac
timeline/World APIs and writes deterministic scenario metadata to `/World`.

Fault injection is test setup only. Safety state is read-only evidence, and this package cannot
command, bypass, certify, or replace functional-safety hardware.

## Dependencies

| Dependency | License | Maintenance | Reason | Removal path |
|---|---|---|---|---|
| ROS 2 Jazzy (`rclpy`, interfaces, launch, `std_msgs`) | Apache 2.0 | ROS 2 LTS/OSRF | typed control, registration, trace, and fault bridge | keep the pure service and replace the ROS edge |
| PyYAML | MIT | actively maintained | safe loading of existing canonical scenario and cell YAML | provide JSON equivalents or a domain loader before removal |
| Isaac Sim 6 / Kit / OpenUSD | NVIDIA/Apache 2.0 components | NVIDIA supported release | timeline, physics-step, and USD scenario setup backend | use another `SimulationBackend` implementation |
| IsaacSim-ros_workspaces Pixi environment | Apache 2.0 / ROS package licenses | NVIDIA maintained | supported native Windows Jazzy, MoveIt, compiler, and bridge environment | use a supported Linux ROS Jazzy runner |

The modeled laser adapter qualifies readiness, command handshake, timing, and completion only. It
does not model or qualify beam/material interaction, heat, plume, optics, engraving contrast, text
fidelity, or mark quality.
