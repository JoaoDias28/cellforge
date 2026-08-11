# Observability and traceability

## 1. Correlation

All events carry:

- `trace_id` for the job;
- `job_id`;
- `command_id` for an action/service operation;
- `cell_id`;
- `component_instance_id` where applicable;
- bundle, recipe, and task versions.

## 2. Event types

- job accepted/rejected/started/completed;
- cell state changed;
- behavior-tree node entered/completed;
- device command requested/accepted/completed;
- device state changed;
- perception result;
- inspection result;
- fault raised/cleared;
- recovery requested/completed;
- operator acknowledgement;
- deployment activated/rolled back.

Task 021 adds `bundle_id` as an explicit canonical `JobEvent` and durable trace column. Runtime
producers receive it from the active systemd environment/launch configuration. The trace database
migrates older stores by adding an empty-default column; new events preserve the exact active ID.
Bundle activation and rollback also append durable cell-local deployment events containing the
candidate, previous, and final active IDs, including failed-health rollback outcomes.

## 3. Storage

Local cell storage is authoritative during outages. Structured events use an append-only local database or durable journal. Selected ROS topics use rosbag2 with MCAP. Attachments are referenced by content hash.

### 3.1 Operator audit journal

Task 022 stores an append-only local SQLite sequence for each operator mutation. Records contain a
request ID, principal ID and role, semantic action, resource ID, outcome, stable code, sanitized
details, and UTC timestamp. `REQUESTED` is committed before runtime dispatch; `COMPLETED`, `DENIED`,
`FAILED`, `TIMED_OUT`, or `CANCELLED` is committed before response where an outcome is available.
Raw bearer tokens and job input payloads are never audit fields. The journal remains authoritative
when the platform server is offline and may be synchronized later without changing local operation.

## 4. Metrics

Initial metrics:

- jobs/pass/fail/reject counts;
- cycle time distributions;
- skill duration distributions;
- fault counts by code/component;
- retries;
- device availability;
- perception confidence distributions;
- inspection measurements;
- storage and synchronization health.

Prometheus/Grafana may be added, but the event model must not depend on them.

## 5. Privacy and retention

Product text, images, and operator identifiers may be sensitive. Retention and access policies are configurable by evidence type. Debug bags must not be recorded indefinitely by default.

## 6. Simulation evidence

Task 018 scenario evidence is canonical JSON with normalized sequence ordering, exact seed and
randomization samples, scenario/cell.yaml/USD SHA-256 identities, registered adapter capabilities
and actual fidelity, requested-versus-achieved fidelity, limitations, assertion outcomes, and the
captured trace. Evidence write failure fails finalization; a run is never reported successful when
its required evidence could not be stored.

## 7. Motion evidence

Task 019 motion results preserve command ID, trace ID, synchronized scene revision, plan-only or
plan-and-execute mode, stable result code, planning duration, MTC completed/failed stages, and
outcome certainty. Scene synchronization evidence preserves the exact cell ID and canonical
`cell.yaml`/USD SHA-256 values. Motion events use the canonical `JobEvent` stream. This evidence
does not claim that controller cancellation is a safety-rated stop or that a simulated trajectory
qualifies physical hardware.

## 8. Physical pen simulation evidence

Task 020 seed reports preserve the explicit bounds, each seed and sampled pose, ordered cycle and
motion-request events, stable fault code, aggregate counts, backend identity, achieved fidelity,
and whether PhysX actually executed. Failed runs remain replayable by seed. CPU-model reports state
that PhysX did not execute. Neither CPU nor Isaac reports qualify laser mark quality, real hardware,
production parameters, or independent functional safety.
