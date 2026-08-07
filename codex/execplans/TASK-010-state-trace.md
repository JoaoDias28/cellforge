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
- Aggregated `CellState` publication with readiness computation
- Event recorder that publishes `JobEvent` messages
- Tests for ordering, restart, device timeout, and cell readiness

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
    aggregator.py        # StateAggregator ROS node
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
    def record(self, event: TraceEvent) -> None: ...
    @abstractmethod
    def query(...) -> list[TraceEvent]: ...
    @abstractmethod
    def close(self) -> None: ...
```

### SqliteTraceEventStore

- Stores events in `events` table with columns matching TraceEvent fields
- On construction, reads `max(sequence)` from DB to resume numbering
- Each `record()` call increments and stores sequence
- `query()` supports filters: trace_id, job_id, time range, event_type, severity
- Thread-safe via WAL mode + connection per operation

### StateAggregator node

- Subscribes to per-device `DeviceState` topics
- Subscribes to `SafetyState` topic
- Maintains in-memory map of last seen device states
- Detects stale devices when heartbeat exceeds timeout (default 3.0s)
- Computes cell state: OFFLINE, STARTING, IDLE, READY, RUNNING, PAUSED, RECOVERABLE_FAULT, TERMINAL_FAULT, MAINTENANCE, STOPPING
- Publishes aggregated `CellState` at configurable rate

### Cell readiness

```
all_required_devices_ready = all(
    device.ready for device in required_devices
) and safety_healthy
```

Required device IDs come from cell configuration parameter.

### Stale device detection

Device considered stale if `(now - heartbeat.stamp) > timeout`. State aggregator publishes a degraded cell state when devices are stale.

## Work sequence

1. Run pre-existing tests to establish baseline
2. Create package scaffolding (package.xml, setup.py, setup.cfg, resource marker)
3. Implement `TraceEventStore` ABC and `SqliteTraceEventStore`
4. Implement trace query utility
5. Implement state aggregator node with stale detection
6. Implement event recorder (publishes `JobEvent`, uses trace store)
7. Write comprehensive tests
8. Update Makefile mypy paths
9. Run lint, test, validate-examples
10. Commit

## Validation
- `make lint` — ruff format/check, mypy (add `cellforge_state_trace` to mypy paths)
- `make test` — pytest for all test paths
- `make validate-examples` — pen engraving examples validate
- `make ros-build` — colcon build succeeds (if ROS available)
- Manual: state aggregator computes correct readiness, events survive restart, stale detection works

## Risks and rollback
- New package is additive; no existing code modified
- SQLite dependency is stdlib; no new external dependencies
- Rollback: delete the package directory and revert Makefile change

## Progress
- [ ] 2026-08-07 — package scaffolding and trace store implementation
- [ ] 2026-08-07 — state aggregator node
- [ ] 2026-08-07 — tests, lint, commit

## Decisions
- 2026-08-07 — Combine state aggregator and trace recorder in one package (`cellforge_state_trace`) since they share the ROS package dependency and are both core runtime services
- 2026-08-07 — Use SQLite WAL mode for concurrent read/write safety
- 2026-08-07 — Sequence numbers are per-event monotonic, persisted in SQLite, resumed on restart via `SELECT max(sequence)`
- 2026-08-07 — Stale device detection timeout defaults to 3.0s (3x the 1Hz heartbeat rate)
- 2026-08-07 — Pure Python tests (no ROS dependency) follow the SDK test pattern
