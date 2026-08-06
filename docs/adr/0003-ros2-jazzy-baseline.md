# ADR 0003: Use ROS 2 Jazzy as the initial baseline

## Status
Accepted for release line 0.x.

## Decision
Target Ubuntu 24.04 and ROS 2 Jazzy for the initial platform release.

## Rationale
This baseline aligns with the selected Isaac Sim ROS bridge and provides a stable supported ROS 2 environment for the initial build.

## Consequences
Pin tested package versions. Treat a future ROS distribution migration as a platform release with compatibility testing, not a routine dependency update.
