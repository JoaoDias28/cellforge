# Reference robot faults

- `robot.motion.planning_failed`
- `robot.motion.execution_failed`
- `robot.motion.protective_stop`
- `robot.communication.lost`

The Task 019 application service maps planner/controller details to these stable service outcomes:

- `motion.request.invalid_input`
- `motion.request.timeout`
- `motion.request.cancelled`
- `motion.scene.rejected`
- `motion.plan.unreachable`
- `motion.plan.collision`
- `motion.plan.failed`
- `motion.execution.failed`
- `motion.execution.outcome_unknown`

Cancellation is a standard controller request, not a safety-rated stop. Independent rated hardware
remains responsible for protective motion functions.
