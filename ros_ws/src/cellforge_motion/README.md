# CellForge motion service

`cellforge_motion` is the application-service boundary around MoveIt 2 and MoveIt Task Constructor
(MTC). Production task trees call `/skills/move_to_pose` and `/skills/execute_manipulation`; they do
not select OMPL algorithms, planning pipelines, controller plugins, or MTC stage implementations.

Before accepting motion, `/motion/sync_planning_scene` requires the active `cell.yaml` and USD
SHA-256 identities plus immutable component instance IDs. The MoveIt scene is a derived runtime
projection. `cell.yaml` remains the canonical operational graph and USD remains the canonical
spatial scene.

`plan_only=true` performs collision-aware planning without a controller or physical robot. The
reference config supplies the named states `home`, `process_safe`, `load_safe`, and `unload_safe`.
The included `mock_components/GenericSystem` and joint trajectory controller are test/simulation
components only.

In the L2 graph, successful MoveIt/MTC controller execution is forwarded to the immutable
`/device/robot_001/execute_trajectory` capability. The result is not reported successful until the
Isaac adapter has applied the operation and returned OpenUSD/PhysX attachment, seating, drop, and
contact observations. Missing, rejected, cancelled, or timed-out adapter execution fails closed.

The MTC builder treats `pick` and `unload` as acquiring/attaching the declared object at its target
pose; `load` places/detaches an already attached object. All three retreat to the caller-selected
declared safe pose. Gripper actuation and fixture sequencing remain separate capability calls owned
by the behavior tree, not hidden MTC workflow.

Cancellation calls MoveIt's stop request and returns a stable standard-control result. It does not
implement a safety-rated stop and cannot override or replace independent protective hardware.
Uncertain controller outcomes are reported as `motion.execution.outcome_unknown` and require
reconciliation.

## Dependencies

- MoveIt 2 (`moveit_ros_planning_interface`, `moveit_msgs`, OMPL/KDL integration): BSD-3-Clause,
  maintained by the MoveIt project and ROS community. It is used for collision-aware planning and
  controller execution. Removal path: implement the `MotionPlanner` port with another supported
  planner while retaining CellForge actions.
- MoveIt Task Constructor (`moveit_task_constructor_core`): BSD-3-Clause, maintained by the MoveIt
  project. It is used for staged pick/load/unload planning. Removal path: replace `MtcTaskBuilder`
  behind `MotionPlanner`; task/supervisor contracts remain unchanged.
- ros2_control reference controllers: Apache-2.0, maintained by the ROS controls community. They are
  used only for the supported reference fake-controller launch. Removal path: select a supported
  simulation or hardware controller adapter in the deployment bundle.

ROS 2 Jazzy resolves the package versions through rosdep on Ubuntu 24.04 or NVIDIA's maintained
IsaacSim-ros_workspaces Pixi environment on Windows 11. Normal runtime requires no internet,
browser, Cell Studio, or cloud service. The L2 target explicitly requires local Isaac Sim 6 and an
NVIDIA GPU; the L0 target does not.

## Checks

Run `make motion-service-check` for the deterministic configuration/interface probe and `make
ros-build && make ros-test` on a ROS 2 Jazzy host for C++ and ROS integration evidence. This task
does not provide Task 020 physical pen simulation or hardware-in-the-loop qualification.
