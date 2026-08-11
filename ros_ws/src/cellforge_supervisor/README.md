# cellforge_supervisor

Centralized ROS 2 Jazzy supervisor for exact BehaviorTree.CPP 4 XML definitions.

The node serves the private `/cell/supervisor/run_job` `ExecuteFrozenJob` action, resolves its
`task_id` beneath the configured immutable
`tree_root`, validates XML and required blackboard inputs, then ticks the tree on a dedicated worker
thread. `CellReady` is a standard-control readiness condition. `ExecuteSkill` uses an asynchronous
ROS action client; server discovery, goal execution, timeout, and cancellation never wait in a tree
tick. Standard BehaviorTree.CPP retry and timeout decorators remain available in XML.

The supervisor publishes standard-control state on `/cell/supervisor_state` and canonical events on
`/events/job`. It reads `/cell/state` only to refuse work when the modeled readiness snapshot is not
healthy. None of these paths implements or bypasses a safety-rated function.

`task_id` is an exact versioned identifier such as `pick-part@2.1.0`, resolved as
`<tree_root>/pick-part@2.1.0.xml`; paths and traversal are rejected. Task 012 is responsible for
freezing and authorizing job, recipe, and tree references before submission. The supervisor
validates the supplied trace, bundle/source, recipe, task, mode, and calibration identity and
checks recipe/tree SHA-256 digests before constructing the tree. Public callers continue to use
the backward-compatible `RunJob` action exposed by `cellforge_job_gateway`.

Task 024 loads BehaviorTree plugins only from `behavior_tree_plugins` entries in the active
immutable bundle manifest supplied by `CELLFORGE_MANIFEST`. Each entry must name a package already
present in `native_packages`, a stable library beneath that package's ROS prefix, and a bundle-
contained node manifest with an exact SHA-256 digest. The loader verifies node-manifest identity and
registration parity before accepting work; there is no arbitrary plugin-path parameter.

The canonical pen plugin preserves leaf result codes on the blackboard. If a dispatched process
returns unknown certainty or its deadline expires without a provable result, the supervisor emits
`job.outcome_unknown`, returns `supervisor.job.outcome_unknown`, and stops the tree without retry or
inspection. Cancellation remains a standard-control request propagated to active actions.
