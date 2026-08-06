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
