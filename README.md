# CellForge — Robot Cell Engineering Platform Design Pack

**Status:** real hardware adapters & on-cell commissioning complete (Task 034); all roadmap implementation tasks completed
**Primary use:** simulation-first robot cell engineering platform
**First production use case:** robotic loading, laser engraving, inspection, and unloading of pens
**Long-term scope:** reusable simulation-first engineering platform for many industrial robot cells

## What CellForge is

CellForge is an internal engineering platform for creating robot cells from reusable components. An engineer should be able to:

1. create a new cell project;
2. place robots, tools, cameras, fixtures, process machines, conveyors, and products in a 3D scene;
3. connect mechanical mounts, ROS interfaces, industrial I/O, and modeled safety dependencies;
4. compose a task from reusable skills;
5. create versioned product/process recipes;
6. simulate nominal and fault scenarios;
7. validate the cell against machine-readable rules;
8. export a deterministic deployment bundle for the physical cell;
9. operate the cell with traceability and without requiring the engineering workstation.

The platform is intentionally split into two products:

- **Cell Studio:** the engineering application built as an Isaac Sim / Omniverse Kit extension.
- **Cell Runtime:** the production ROS 2 application deployed to each physical cell.

Every component can expose a simulation adapter and a hardware adapter behind the same capability interface. The same recipe and behavior tree should therefore run in simulation and on real hardware, subject to explicit deployment configuration and safety validation.

## Non-goals

CellForge does not replace:

- a safety PLC, safety relay, safety-rated robot functions, or laser safety controller;
- a robot manufacturer's servo controller;
- certified risk assessment or machine conformity work;
- a CAD system;
- arbitrary end-to-end AI control of safety-critical machinery;
- a universal driver that magically controls unsupported industrial equipment.

## Baseline technology choices

- Ubuntu 24.04 LTS
- ROS 2 Jazzy
- Isaac Sim 6.x and Omniverse Kit for the engineering studio
- OpenUSD for the spatial scene
- YAML/JSON manifests for operational semantics and configuration
- MoveIt 2 and MoveIt Task Constructor for robot motion and manipulation planning
- BehaviorTree.CPP for runtime task orchestration
- OpenCV first, ONNX Runtime second, Isaac ROS only when acceleration or advanced perception is justified
- FastAPI, Pydantic, and PostgreSQL for registry, recipes, jobs, and deployment metadata
- OPC UA, Modbus TCP, vendor APIs, and digital I/O through device adapters
- rosbag2/MCAP and structured events for traceability

## Repository map

```text
AGENTS.md                     Codex-wide engineering rules
PLANS.md                      ExecPlan format and completion rules
SYSTEM_SPEC.md                complete product and system specification
ROADMAP.md                    phased delivery plan
CODEX_TASK_INDEX.md           task ordering and dependencies

docs/
  architecture.md             containers, services, data flow, deployment
  domain-model.md             components, ports, capabilities, cells, recipes
  component-sdk.md            how to add a supported device
  cell-studio.md              engineering UI and Isaac Sim extension design
  cell-runtime.md             ROS graph and production process execution
  simulation.md               simulation adapters, scenarios, fault injection
  deployment.md               bundle generation and installation
  safety-security.md          hard boundaries, network zones, permissions
  testing.md                  test pyramid and acceptance requirements
  observability.md            logs, traces, metrics, production records
  adr/                        architecture decision records

schemas/                      machine-readable JSON schemas
ros_interfaces/               canonical ROS interface definitions
examples/pen_engraving/       complete reference cell configuration
codex/tasks/                  staged implementation tasks for Codex
```

## How to use this pack with Codex

1. Create a new Git repository and copy this directory into it.
2. Start Codex at the repository root so it loads `AGENTS.md`.
3. Ask Codex to execute `codex/tasks/TASK-001-repository-bootstrap.md`.
4. Review the pull request and run the listed acceptance checks.
5. Continue in dependency order from `CODEX_TASK_INDEX.md`.
6. Do not ask Codex to implement the whole platform in one task.

The project is designed so early tasks produce a useful headless platform before the complete graphical studio exists.
