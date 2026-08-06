> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-007 — ROS interface package

## Goal
Create a buildable `cellforge_interfaces` ROS 2 package from `ros_interfaces/`.

## Deliverables

- messages, services, and actions copied/organized into the package;
- correct dependencies and CMake configuration;
- interface documentation;
- a compatibility test that generated types are importable from C++ and Python.

## Acceptance

- `colcon build --packages-select cellforge_interfaces` passes on ROS 2 Jazzy;
- `colcon test` passes;
- no interface contains vendor-specific fields.
