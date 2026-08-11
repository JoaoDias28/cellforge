# Cell Runtime

## 1. Startup sequence

1. systemd starts bundle agent and runtime target;
2. the bundle agent verifies the active manifest, complete checksums, local target compatibility,
   and resolves named secrets to protected cell-local state;
3. configuration and schemas are validated;
4. ROS domain/network profile is loaded;
5. device adapters start but remain inactive;
6. state aggregator waits for required devices;
7. adapters configure and activate through lifecycle transitions where supported;
8. supervisor loads behavior-tree plugins and validates tree contracts;
9. recipe cache loads approved bundle recipes;
10. cell enters `READY` only when required readiness and safety status are healthy.

The agent supplies `CELLFORGE_BUNDLE_ID`, `CELLFORGE_BUNDLE_ROOT`, and `CELLFORGE_MANIFEST` through
`/var/lib/cellforge/runtime.env`. Runtime launch passes the exact bundle ID to the supervisor,
motion service, state aggregator, and trace recorder. Activation health must echo that ID; a healthy
response from an older process is rejected and triggers rollback.

## 2. Job execution sequence

1. job gateway receives a job with idempotency key;
2. gateway verifies mode and exact recipe/tree references;
3. gateway freezes input payload and creates trace ID;
4. gateway durably records the frozen job, then submits the private `ExecuteFrozenJob` action;
5. supervisor creates behavior-tree blackboard from frozen job and recipe;
6. tree executes capability actions/services;
7. cancellation propagates to active skills;
8. structured events are written before external acknowledgement where practical;
9. gateway commits the final result locally before completing the public action;
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

`cellforge_job_gateway` serves `/cell/run_job`, while `cellforge_supervisor` serves the internal
`/cell/supervisor/run_job` endpoint using private `ExecuteFrozenJob`; public `RunJob` remains
wire-compatible. The supervisor treats `ExecuteFrozenJob.task_id` as an exact versioned
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

### 3.2 Job gateway and frozen records

The gateway resolves the active immutable bundle manifest, recipe version, and task version before
supervisor submission. It verifies content digests, exact cell and mode compatibility, recipe
capabilities, and lifecycle policy. Simulation allows non-retired development recipes;
commissioning requires `TESTED` or `APPROVED`; production requires `APPROVED`.

The private goal carries the gateway-generated trace ID, bundle and source revision, exact
recipe/task IDs and SHA-256 digests, canonical recipe YAML, execution mode, and calibration
references. The supervisor verifies these values against its active configuration and resolved tree
before constructing a tree or dispatching any capability. Identity mismatch is a deterministic
standard-control refusal.

Each accepted request is stored in a local SQLite database using its idempotency key and a canonical
request hash. Matching completed retries replay the durable result; conflicting payloads are
rejected. After restart, a nonterminal record is marked `OUTCOME_UNKNOWN` and is never automatically
replayed. These standard-control rules cannot authorize physical processing when independent rated
hardware refuses it.

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

`cellforge_supervisor` links the platform OpenSSL `libcrypto` implementation for EVP SHA-256
verification. OpenSSL is Apache-2.0 licensed, maintained by the OpenSSL project, and supplied by
the Ubuntu platform. It is required so the supervisor independently checks frozen recipe and tree
bytes; it can be removed when the same verification moves to a shared, supported platform
cryptography package without changing the frozen-job contract.

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

### 9.1 Task 022 local API contract

The loopback API exposes versioned status, active-job, faults, immutable bundle/recipe identity,
trace-summary, submit, cancel, and approved-recovery routes plus a same-origin minimal page. It uses
only local ROS state/action/service contracts and local SQLite files, so loss of the platform server
does not remove cell operation.

Viewer, operator, maintainer, and administrator roles are authenticated from token digests in
protected local configuration. Job mutation requires operator. Each recovery entry declares its
minimum role; maintenance always requires maintainer or administrator. Denied and invalid attempts
are audited as well as successful, failed, timed-out, and cancelled operations.

Recovery entries contain no executable or ROS endpoint. The fixed `/cell/operator_action` service
must independently check current fault/state and returns outcome certainty. Service unavailability
is an explicit failure, not a simulated success. Displayed safety health is standard-control
readiness information only.

## 10. Task 019 motion service contract

`cellforge_motion` serves `/skills/move_to_pose`, `/skills/execute_manipulation`, and
`/motion/sync_planning_scene`. A synchronized scene revision is required before planning. Every
action carries command/trace identity and returns stable `motion.*` codes, planning time, scene
revision, evidence JSON, and explicit outcome certainty.

`plan_only=true` requires the robot model and planning scene but no physical controller. The
reference fake controller is simulation/test infrastructure. For plan-and-execute, cancellation or
deadline expiry forwards a stop request; an adapter that cannot prove the physical result must
return `motion.execution.outcome_unknown` and require reconciliation.
