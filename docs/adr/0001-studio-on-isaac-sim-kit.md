# ADR 0001: Build Cell Studio on Isaac Sim and Omniverse Kit

## Status
Accepted for the initial platform.

## Decision
Use Isaac Sim as the simulation host and Omniverse Kit extensions as the main engineering application shell.

## Rationale
The platform needs a 3D viewport, OpenUSD scene graph, physics, robot/sensor simulation, UI toolkit, extension system, and ROS 2 bridge. Building these foundations independently would dominate cost and schedule.

## Consequences
The engineering workstation requires compatible NVIDIA hardware. Production cells remain independent of Isaac Sim. Domain logic must stay outside Kit-specific modules to reduce lock-in and enable headless tests.
