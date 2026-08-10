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

## 3. Storage

Local cell storage is authoritative during outages. Structured events use an append-only local database or durable journal. Selected ROS topics use rosbag2 with MCAP. Attachments are referenced by content hash.

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
