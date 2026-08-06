# Technical baseline references

Validate exact versions during Task 001 and pin the tested combination.

Authoritative source families used for this design:

- ROS 2 documentation — Jazzy release/support information and ROS concepts.
- NVIDIA Isaac Sim 6 documentation — ROS 2 Jazzy integration, ROS bridge, simulation control, extension APIs.
- NVIDIA Omniverse Kit documentation — building OpenUSD applications and extensions.
- OpenUSD documentation — references, variants, layers, and composition.
- MoveIt 2 documentation — motion planning and MoveIt Task Constructor.
- ros2_control documentation — hardware abstractions, lifecycle, and mock components.
- BehaviorTree.CPP documentation — ROS 2 service-oriented coordinator pattern and asynchronous actions.
- OpenAI Codex documentation — `AGENTS.md`, ExecPlans, and task-scoped prompting.

This repository intentionally avoids hard-coding unverified patch versions. Create a tested toolchain lock during bootstrap.
