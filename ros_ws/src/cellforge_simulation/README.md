# cellforge_simulation

Task 018 provides a pure deterministic simulation lifecycle and evidence service with thin ROS 2
and Isaac Sim 6 adapters. The ROS node exposes `/simulation/configure`, `/simulation/control`,
`/simulation/register_adapter`, `/simulation/inject_fault`, and `/simulation/finalize`.

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
