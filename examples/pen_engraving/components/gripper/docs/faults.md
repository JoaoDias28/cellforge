# Reference pen gripper simulation faults

- `gripper.object.dropped`: the simulated grasp joint is absent or released and the pen height is
  below the configured carrier/fixture envelope. The cycle stops before loading or processing.

This is simulation fault detection, not a protective or safety-rated function.
