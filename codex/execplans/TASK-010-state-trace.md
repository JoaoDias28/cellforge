# TASK-010 — State aggregator and trace recorder

## Goal
Create canonical cell state aggregation and durable structured event recording for the CellForge runtime.

## Scope
**Included:**
- `cellforge_state_trace` ROS Python package in `ros_ws/src/`
- `TraceEventStore` abstract interface and `SqliteTraceEventStore` implementation
- Trace query utility (filter by trace_id, job_id, time range, event_type, severity)
- Event sequence numbering that survives process restart
- State aggregator ROS node that subscribes to per-device `DeviceState` and `SafetyState` topics
- Stale-device detection via heartbeat timeout
- Safety status freshness with configurable timeout (fail-closed)
- Required vs optional device staleness differentiation
- Aggregated `CellState` publication with readiness computation
- Durable event recorder node subscribing to `JobEvent` topic
- Correlation validation for trace events
- Tests for ordering, restart, device timeout, cell readiness, concurrency, correlation

**Explicitly excluded:**
- Supervisor integration (Task 011)
- rosbag2/MCAP integration
- Prometheus/Grafana metrics
- Any safety enforcement logic

## Current state
- `CellState.msg` defines aggregated cell state with `all_required_devices_ready`, `DeviceState[] devices`, `active_job_id`, `active_trace_id`, `bundle_id`
- `JobEvent.msg` defines structured trace events with `trace_id`, `job_id`, `cell_id`, `component_instance_id`, `command_id`, `uint64 sequence`, `event_type`, `severity`, `payload_json`
- `DeviceState.msg` provides per-device state with `component_instance_id`, `state`, `ready`, `busy`, `faulted`, `active_command_id`, `fault_code`, `fault_message`, `details_json`
- `SafetyState.msg` defines safety monitor inputs
- `DeviceStateSnapshot` (device SDK) provides canonical device state model
- `CanonicalStatePublisher` / `RosDeviceStatePublisher` convert to ROS messages
- Mock adapters publish per-device state at 1 Hz on `~/state` topics
- Six mock devices: robot-001, gripper-001, fixture-001, camera-001 (×2), laser-001
- `cell.yaml` defines component instance IDs and required capabilities
- `docs/observability.md` defines event types and storage strategy

## Design

### Package: `cellforge_state_trace`

```
ros_ws/src/cellforge_state_trace/
  cellforge_state_trace/
    __init__.py
    trace_store.py       # TraceEventStore ABC, SqliteTraceEventStore, query utilities
    state_logic.py       # DeviceStateEntry, SafetyStatusEntry, compute_top_level_cell_state
    aggregator.py        # StateAggregator ROS node
    recorder.py          # DurableEventRecorder ROS node
    correlation.py       # Correlation validation for trace events
  package.xml
  setup.py
  setup.cfg
  resource/cellforge_state_trace
```

### TraceEventStore interface

```python
@dataclass(frozen=True, slots=True)
class TraceEvent:
    trace_id: str
    job_id: str
    cell_id: str
    component_instance_id: str
    command_id: str
    sequence: int
    event_type: str
    severity: str
    payload: dict[str, Any]
    timestamp: datetime

class TraceEventStore(ABC):
    @abstractmethod
    def record(self, event: TraceEvent) -> int: ...
    @abstractmethod
    def query(...) -> list[TraceEvent]: ...
    @abstractmethod
    def close(self) -> None: ...
```

### SqliteTraceEventStore

- Stores events in `events` table with columns matching TraceEvent fields
- On construction, reads `max(sequence)` from DB to resume numbering
- Each `record()` call increments and stores sequence under a `threading.Lock`
- `UNIQUE` index on `sequence` column as second line of defense against duplicates
- `query()` supports filters: trace_id, job_id, time range, event_type, severity
- Thread-safe via WAL mode + lock-protected connection

### StateAggregator node

- Subscribes to per-device `DeviceState` topics
- Subscribes to `SafetyState` topic
- Maintains in-memory map of last seen device states
- Tracks safety status freshness via `SafetyStatusEntry` (configurable timeout, default 3.0s)
- Detects stale devices when heartbeat exceeds timeout (default 3.0s)
- Only required-device staleness prevents READY; optional stale devices are still shown as offline
- Computes cell state: OFFLINE, STARTING, IDLE, READY, RUNNING, PAUSED, RECOVERABLE_FAULT, TERMINAL_FAULT, MAINTENANCE, STOPPING
- Publishes aggregated `CellState` at configurable rate

### Safety freshness policy

- Safety status uses the receive timestamp (wall clock when `SafetyState` message arrives)
- Timeout is configurable via `safety_timeout_s` ROS parameter (default 3.0s)
- Stale or never-received safety → `effective_healthy = False` → cell cannot enter READY
- This is a fail-closed software readiness indication only; no functional safety is implemented

### Cell readiness

```
all_required_devices_ready = all(device.ready for device in required_devices)
safety_healthy = safety.effective_healthy  # accounts for staleness
cell_ready = all_required_devices_ready and safety_healthy
```

Required device IDs come from cell configuration parameter.

### Stale device detection

Device considered stale if `(now - heartbeat.stamp) > timeout`. Only required-device staleness prevents READY. All stale devices appear as OFFLINE in the aggregated device list.

### Durable event recorder

```
JobEvent producer(s) -> ROS /events/job topic -> DurableEventRecorderNode -> TraceEventStore
```

- Subscribes to `cellforge_interfaces/JobEvent`
- Validates correlation identifiers via `validate_correlation()`
- Converts losslessly to `TraceEvent` (preserves all fields, timestamp, payload)
- Persists using `TraceEventStore`; does not acknowledge before `record()` returns
- SQLite path configurable via `db_path` parameter
- Fails visibly on invalid/unpersistable events

### Correlation validation

- Every event requires non-empty UUID `trace_id` and `job_id`
- Command events (`device.command.requested/accepted/completed/rejected/cancelled`) additionally require non-empty UUID `command_id`
- Non-command events (cell.state.changed, operator.acknowledgement, etc.) are exempt from `command_id`

## Work sequence

1. Run pre-existing tests to establish baseline
2. Create package scaffolding (package.xml, setup.py, setup.cfg, resource marker)
3. Implement `TraceEventStore` ABC and `SqliteTraceEventStore`
4. Implement trace query utility
5. Implement state aggregator node with stale detection
6. Write comprehensive tests
7. Update Makefile mypy paths
8. Run lint, test, validate-examples
9. Commit initial implementation
10. Address review findings (safety freshness, optional staleness, concurrency, recorder, correlation, query ordering)
11. Commit review fixes
12. Audit Tasks 001-010 and the failing PR CI run; repair hidden ROS test and runtime-edge defects
13. Verify the complete repository and ROS Jazzy suite in GitHub Actions

## Validation
- `make lint` — ruff format/check, mypy (add `cellforge_state_trace` to mypy paths)
- `make test` — pytest for all test paths
- `make validate-examples` — pen engraving examples validate
- `make ros-build` — colcon build succeeds (if ROS available)
- Manual: state aggregator computes correct readiness, events survive restart, stale detection works

## Risks and rollback
- The state/trace package is additive, while this audit also corrects the Task 009 ROS test edge,
  package dependency metadata, CI commands, and stale setup documentation.
- SQLite dependency is stdlib; no new external dependencies
- Rollback: revert the final Task 010 audit commit; no schema or deployed-data migration is involved.

## Progress
- [x] 2026-08-08 — audited Tasks 001-010 against acceptance criteria and reproduced the ROS Jazzy CI failure
- [x] 2026-08-08 — fixed environment sourcing, real Jazzy smoke-test execution, node construction, fail-closed readiness, package dependencies, and cross-platform interface parity
- [x] 2026-08-08 — full repository and GitHub Actions verification
- [x] 2026-08-07 — package scaffolding and trace store implementation
- [x] 2026-08-07 — state aggregator node
- [x] 2026-08-07 — tests, lint, initial commit
- [x] 2026-08-07 — review fixes (safety freshness, optional staleness, concurrency, recorder, correlation, query ordering)

## Decisions
- 2026-08-08 (CI) — `ament_python` is the package build type, not a resolvable Jazzy rosdep key; keep it in each package's `<export><build_type>` and declare only installable runtime/test dependencies.
- 2026-08-08 (audit) — Source the underlay and built workspace before enabling Bash nounset because generated colcon setup scripts legitimately probe unset variables.
- 2026-08-08 (audit) — An empty required-device configuration cannot authorize readiness; it fails closed as missing required state.
- 2026-08-08 (audit) — Jazzy smoke tests must execute after `rclpy.init()` and exercise actual action/service and state/trace node paths; a pre-import skip is not valid evidence.
- 2026-08-07 — Combine state aggregator and trace recorder in one package (`cellforge_state_trace`) since they share the ROS package dependency and are both core runtime services
- 2026-08-07 — Use SQLite WAL mode for concurrent read/write safety
- 2026-08-07 — Sequence numbers are per-event monotonic, persisted in SQLite, resumed on restart via `SELECT max(sequence)`
- 2026-08-07 — Stale device detection timeout defaults to 3.0s (3x the 1Hz heartbeat rate)
- 2026-08-07 — Pure Python tests (no ROS dependency) follow the SDK test pattern
- 2026-08-07 — Separated pure state logic (`state_logic.py`) from ROS node (`aggregator.py`) so tests can run without rclpy
- 2026-08-07 (review) — Safety status freshness uses receive-time timestamp with configurable timeout; stale safety is fail-closed
- 2026-08-07 (review) — Only required-device staleness prevents READY; optional stale devices are shown as OFFLINE but don't block
- 2026-08-07 (review) — `threading.Lock` protects sequence allocation with `UNIQUE` index as second defense
- 2026-08-07 (review) — Correlation validation requires UUID trace_id/job_id for all events, `command_id` only for command events
- 2026-08-07 (review) — `query_events_by_type` docstring corrected to "oldest first" chronological order matching ASC behavior

## Results
- New package `cellforge_state_trace` in `ros_ws/src/` with six modules:
  - `trace_store.py`: `TraceEventStore` ABC, `SqliteTraceEventStore` (lock-protected, UNIQUE sequence constraint), query helpers
  - `state_logic.py`: `DeviceStateEntry`, `SafetyStatusEntry`, `compute_top_level_cell_state` (pure Python, testable without ROS)
  - `aggregator.py`: `StateAggregatorNode` ROS 2 node with stale-device detection, safety freshness, required-only staleness
  - `recorder.py`: `DurableEventRecorderNode` ROS 2 node that subscribes to `JobEvent` and persists to `TraceEventStore`
  - `correlation.py`: `validate_correlation()` with event-type-aware command_id requirements
- Local repository verification: Ruff format/check clean, strict mypy clean, 181 pytest tests passed,
  and validation passed for 5 canonical schemas, 6 component configuration schemas, and 11
  example YAML documents.
- GitHub Actions run 23 on Ubuntu 24.04 / ROS 2 Jazzy: rosdep resolution passed, all 4 ROS
  packages built, and 15 colcon tests completed with 0 errors, 0 failures, and 0 skipped.
- The Python 3.12 Actions job passed lint/type checks, all repository tests, and the explicit
  schema/example validation gate.
- The audit corrected the previously skipped Task 009 ROS action/service smoke test and added
  Task 010 Jazzy integration coverage for aggregator startup/readiness and durable event recording.
- Two console entry points: `state_aggregator`, `durable_event_recorder`
- Limitations: no rosbag2 integration, no Prometheus metrics, no supervisor integration (Task 011)
