# Simulation and test scenarios

## 1. Adapter parity

Simulation and hardware adapters expose identical ROS contracts. They may differ internally, but the task tree must not branch on manufacturer or simulator identity except through declared capability metadata or execution mode.

## 2. Simulation architecture

```text
Behavior tree / skills / recipes
              │ ROS 2
      canonical device contracts
          /                 \
Isaac Sim adapters       contract mocks
```

Isaac Sim uses the ROS 2 bridge. Simulation control should be exposed to the test runner through ROS 2 simulation interfaces or a small studio service, allowing deterministic reset, pause, step, and scenario setup.

## 3. Scenario runner

The headless runner shall:

- load cell and scenario;
- set random seed;
- spawn products and apply variations;
- configure simulated device state;
- start trace capture;
- submit job;
- inject scheduled faults;
- wait for completion/timeout;
- evaluate assertions;
- save JUnit-compatible and domain reports.

## 4. Initial fault library

- camera unavailable;
- stale image;
- object absent;
- pose outside correction limit;
- gripper close failure;
- dropped object;
- fixture seating failure;
- process machine not ready;
- process program missing;
- process timeout;
- inspection fail;
- robot path planning failure;
- robot protective stop status;
- communication loss;
- safety status unhealthy.

## 5. Randomization

Randomization must be bounded by explicit distributions in scenario files:

- product position and orientation;
- surface color/material visual variant;
- lighting intensity/direction;
- camera noise;
- friction and mass;
- component timing;
- network delay for non-real-time protocols.

Every failed run stores the seed for reproduction.

## 6. Fidelity honesty

Simulation evidence must state what is modeled and not modeled. For example, the laser simulation may validate command sequencing and timing but not prove mark quality. Physical process qualification remains required.

## 7. Performance tests

Measure separately:

- simulation wall-clock factor;
- motion-planning time;
- perception latency;
- end-to-end cycle time;
- event/trace overhead;
- job throughput;
- repeated-run variance.
