# cellforge_mock_adapters

L0 contract mocks for the six CellForge reference device families: robot motion, gripper,
fixture, vision locator, process machine, and inspection. Every mock is built on the Task 008
device SDK, runs the generic adapter contract suite, publishes coherent canonical state
transitions, and selects timing, deterministic outcomes, and faults from a validated JSON
scenario configuration.

These are L0 (configurable timing and interface behaviour only — no geometry, physics, or
process-quality evidence). They are safe to run without Isaac Sim, hardware, or a GPU. They
implement no safety-rated function; interlock status is consumed as read-only scenario data.

## Fault catalog

| Device | Supported fault codes |
|---|---|
| robot | `robot.motion.planning_failed`, `robot.motion.execution_failed`, `robot.motion.protective_stop`, `robot.communication.lost` |
| gripper | `gripper.motion.open_failed`, `gripper.motion.close_failed`, `gripper.object.dropped` |
| fixture | `fixture.motion.clamp_failed`, `fixture.motion.release_failed`, `fixture.sensor.seating_failed` |
| vision locator | `camera.communication.unavailable`, `camera.image.stale`, `vision.object.not_found`, `vision.pose.correction_limit` |
| process machine | `laser.communication.timeout`, `laser.program.not_found`, `laser.process.interlock_not_ready`, `laser.process.timeout`, `laser.process.outcome_unknown` |
| inspection | `camera.communication.unavailable`, `camera.image.stale`, `vision.inspection.measurement_invalid` |

All mocks also support `sdk.test.injected_fault` as a documented test hook. The uncatalogued
`laser.process.outcome_unknown` is treated as an explicit uncertain outcome: the mock reports
`outcome_certain: false` and transitions to `UNKNOWN`, forcing supervised recovery.

## Quick start

```bash
# Build the workspace (Jazzy host)
cd ros_ws
colcon build --packages-select cellforge_mock_adapters

# Run the complete mock cell
source install/setup.bash
ros2 launch cellforge_mock_adapters mock_cell.launch.py
```

The launch file starts six nodes (`mock_robot`, `mock_gripper`, `mock_fixture`,
`mock_vision_locator`, `mock_inspection`, `mock_laser`) from
`config/mock_cell_scenarios.json`. Each node publishes canonical `DeviceState`, serves
capability-specific ROS 2 actions, and exposes a `GetDeviceState` service.

A node refuses to start on an invalid scenario (fail-fast).

## Dependencies

| Dependency | License | Reason | Removal path |
|---|---|---|---|
| `rclpy` | Apache 2.0 | ROS 2 node runtime; maintained by OSRF | delete the package |
| `cellforge_interfaces` | Proprietary | Shared action/message definitions | internal workspace |
| `cellforge_device_sdk` | Proprietary | Adapter lifecycle and contract harness | internal workspace |
| `setuptools` | MIT | Package build | standard ament tool |

## Limitations (honest)

- L0 fidelity only: configurable timing and contract behaviour; no geometry, kinematics, physics,
  sensor data, or process-quality evidence.
- The vision locator and inspection adapters share component instance `camera-001` (as in the
  reference cell), which means two `DeviceState` publishers exist for the same instance. The
  state aggregator (Task 010) must handle this.
- ROS action feedback is minimal (one start and one completion update). Periodic progress
  feedback is not published.
- Safety interlock status is a read-only configuration parameter, not a live topic subscription.

## Functional-safety boundary

This package **is not a safety-rated component.** It may display read-only safety status and
refuse operation with stable fault codes. All protective functions (emergency stop, guard
locking, laser enable, safe stop) belong to independent rated hardware outside the scope of
this software.
