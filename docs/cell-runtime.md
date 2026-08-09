# Cell Runtime

## 1. Startup sequence

1. systemd starts bundle agent and runtime target;
2. bundle manifest and hashes are verified;
3. configuration and schemas are validated;
4. ROS domain/network profile is loaded;
5. device adapters start but remain inactive;
6. state aggregator waits for required devices;
7. adapters configure and activate through lifecycle transitions where supported;
8. supervisor loads behavior-tree plugins and validates tree contracts;
9. recipe cache loads approved bundle recipes;
10. cell enters `READY` only when required readiness and safety status are healthy.

## 2. Job execution sequence

1. job gateway receives a job with idempotency key;
2. gateway verifies mode and exact recipe/tree references;
3. gateway freezes input payload and creates trace ID;
4. supervisor accepts `RunJob` action;
5. supervisor creates behavior-tree blackboard from frozen job and recipe;
6. tree executes capability actions/services;
7. cancellation propagates to active skills;
8. structured events are written before external acknowledgement where practical;
9. final result is committed locally;
10. job gateway returns result and later synchronizes upstream.

## 3. Behavior-tree node policy

Nodes fall into categories:

- conditions: fast, non-blocking checks;
- transformations: pure blackboard/data operations;
- skill actions: asynchronous ROS action clients;
- device services: short ROS service clients;
- recovery subtrees: explicit operator or automatic recovery;
- decorators: timeout, retry, mode, and permission checks.

No behavior-tree node should perform blocking vendor SDK calls directly. Those belong in an adapter node.

### 3.1 Supervisor execution contract

`cellforge_supervisor` serves `/cell/run_job` and treats `RunJob.task_id` as an exact versioned
identifier beneath the active bundle's configured `tree_root`. Separators and traversal are
rejected. The supervisor constructs the complete tree and rejects unknown node types, missing
required ports, and unresolved external blackboard inputs before it enters `RUNNING` or sends a
capability goal.

Initial registered nodes are:

- `CellReady` — a fast standard-control condition over the aggregated readiness snapshot;
- `ExecuteSkill` — a `StatefulActionNode` wrapper over the canonical ROS `ExecuteSkill` action.

Action-server discovery, goal dispatch, results, and cancellation are asynchronous. Tree ticks only
inspect local callback state, and the caller's steady deadline bounds both discovery and execution.
BehaviorTree.CPP retry/timeout decorators compose those actions in XML. Halting a running tree sends
cancellation to every active wrapper; cancellation is a request and does not invent certainty about
the physical outcome.

The supervisor publishes its standard-control state on `/cell/supervisor_state` and emits job,
state, and behavior-node transitions on `/events/job` for Task 010's durable recorder.
Readiness refusal is not a safety-rated protective function, and the supervisor offers no interlock
override.

## 4. Runtime packages

```text
cellforge_interfaces
cellforge_supervisor
cellforge_state
cellforge_job_gateway
cellforge_recipe_runtime
cellforge_trace
cellforge_device_sdk
cellforge_skill_sdk
cellforge_motion
cellforge_vision_core
cellforge_operator_api
```

Vendor/process packages are separate and selected into bundles.

## 5. Device lifecycle

Canonical states:

- `UNKNOWN`
- `OFFLINE`
- `CONNECTING`
- `NOT_READY`
- `READY`
- `BUSY`
- `FAULT`
- `MAINTENANCE`

Adapters publish state transitions and heartbeat timestamps. State aggregator marks stale devices offline according to component policy.

## 6. Command semantics

Long operations use ROS actions and must support:

- goal validation before acceptance;
- feedback;
- cancellation;
- timeout enforced by caller and preferably adapter;
- final result with stable code;
- unique command ID for traceability;
- behavior after communication loss.

Short deterministic queries or setpoints may use services. Continuous state uses topics.

## 7. Restart semantics

After a process restart, the runtime must not assume the previous physical command failed or completed. Adapters reconcile state with hardware and report `outcome_unknown` where necessary. The supervisor transitions to a recovery flow rather than replaying a hazardous command.

## 8. Time and ordering

Cell computers use synchronized monotonic and wall clocks. Event ordering relies on per-process sequence numbers plus timestamps. Commands/results include trace and command IDs.

## 9. Local operation

The local operator interface provides:

- cell state;
- active job and step;
- device readiness;
- faults and approved recovery instructions;
- job start/stop where role permits;
- recipe and bundle identity;
- maintenance diagnostics behind explicit authorization.

It does not expose raw arbitrary ROS calls.
