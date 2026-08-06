# Component SDK

## 1. Purpose

The component SDK is how CellForge grows. A component package turns CAD and a vendor interface into a supported, searchable, testable building block.

## 2. Package layout

```text
components/<vendor>/<model>/
├── component.yaml
├── config.schema.json
├── assets/
│   ├── visual.usd
│   ├── collision.usd
│   └── thumbnails/
├── robot_description/           optional
│   ├── urdf/
│   ├── srdf/
│   └── moveit_config/
├── simulation/
│   ├── adapter package
│   └── tests
├── hardware/
│   ├── adapter package
│   └── protocol fixtures
├── docs/
│   ├── wiring.md
│   ├── configuration.md
│   ├── faults.md
│   └── commissioning.md
└── tests/
    ├── manifest tests
    ├── contract tests
    └── scene tests
```

## 3. Adapter contract

Every adapter shall:

- publish canonical `DeviceState`;
- expose only declared capabilities;
- return stable fault codes;
- reject commands before ready;
- support timeout and cancellation for long operations;
- distinguish command accepted from operation completed;
- report communication loss explicitly;
- enter a known state after restart;
- avoid automatic continuation after uncertain outcomes;
- include simulator tests using the same contract suite.

## 4. Support levels

- `metadata_only`: geometry and documentation, no executable adapter.
- `simulated`: adapter passes contract tests in simulation.
- `bench_tested`: real device tested outside a production cell.
- `production_qualified`: approved commissioning and production acceptance evidence.
- `deprecated`: available for existing bundles but not new designs.

## 5. Fault catalog

Fault codes use `<component-family>.<category>.<condition>`.

Examples:

- `laser.communication.timeout`
- `laser.program.not_found`
- `laser.process.interlock_not_ready`
- `fixture.sensor.seating_failed`
- `robot.motion.protective_stop`
- `camera.image.stale`

Vendor error numbers are captured separately.

## 6. Component import workflow

1. collect license-approved CAD and documentation;
2. simplify visual geometry;
3. create conservative collision geometry;
4. define root and mount frames;
5. create `component.yaml` and config schema;
6. implement simulation adapter;
7. pass generic contract tests;
8. implement hardware adapter using documented interface;
9. run bench test and record evidence;
10. commission in a cell and promote support level.

## 7. Robot component specifics

A robot package should normally wrap an existing maintained ROS 2 driver and manufacturer controller. It contains:

- authoritative URDF/Xacro and SRDF source;
- limits matching controller configuration;
- MoveIt configuration;
- controller/action mapping;
- payload and reach metadata;
- tool flange port;
- simulation setup;
- driver version and firmware compatibility;
- recovery/fault mapping.

Do not implement motor-level control when a suitable manufacturer controller and driver exist.

## 8. Process-machine specifics

A process-machine adapter should use a two-stage command model:

1. prepare/select program and variable data;
2. execute cycle after readiness and external conditions are confirmed.

It must expose enough state to distinguish:

- idle and ready;
- prepared;
- cycle active;
- cycle completed;
- cycle completed with failed process verification;
- fault;
- communication uncertainty.

For hazardous processes, ordinary software commands are subordinate to independent interlocks.
