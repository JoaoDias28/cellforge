# cellforge_supervisor

Centralized ROS 2 Jazzy supervisor for exact BehaviorTree.CPP 4 XML definitions.

The node serves `/cell/run_job`, resolves `RunJob.task_id` beneath the configured immutable
`tree_root`, validates XML and required blackboard inputs, then ticks the tree on a dedicated worker
thread. `CellReady` is a standard-control readiness condition. `ExecuteSkill` uses an asynchronous
ROS action client; server discovery, goal execution, timeout, and cancellation never wait in a tree
tick. Standard BehaviorTree.CPP retry and timeout decorators remain available in XML.

The supervisor publishes standard-control state on `/cell/supervisor_state` and canonical events on
`/events/job`. It reads `/cell/state` only to refuse work when the modeled readiness snapshot is not
healthy. None of these paths implements or bypasses a safety-rated function.

`task_id` is an exact versioned identifier such as `pick-part@2.1.0`, resolved as
`<tree_root>/pick-part@2.1.0.xml`; paths and traversal are rejected. Task 012 is responsible for
freezing and authorizing job, recipe, and tree references before submission.
