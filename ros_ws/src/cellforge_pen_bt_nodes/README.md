# Canonical pen behavior-tree nodes

`cellforge_pen_bt_nodes` is the production BehaviorTree.CPP plugin for the reference pen workflow.
It implements every leaf in `examples/pen_engraving/behavior_tree.xml` with fast conditions or
asynchronous typed ROS action clients. Active actions receive steady deadlines and propagate halt
as cancellation requests. Process results preserve explicit outcome certainty; an uncertain result
halts the sequence and requires reconciliation instead of retry.

The compiler freezes the reviewed JSON node/port manifest into each bundle. The supervisor verifies
that digest and loads this library only when the active immutable bundle declares both the package
and library. The Python L0 executor remains a deterministic oracle and is not a dependency of this
package.

Safety health is read-only standard-control input. These nodes can refuse normal work but do not
implement or replace emergency stop, interlocks, safe motion, or other rated safety functions.
