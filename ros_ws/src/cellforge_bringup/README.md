# CellForge integrated bringup

`cellforge_bringup` launches the immutable, offline L0 reference-cell runtime. It verifies the
bundle ID and launch-critical file inventory before composing contract adapters, read-only safety
status, deterministic L0 motion, state and trace services, the frozen behavior-tree supervisor,
job gateway, semantic recovery coordinator, and loopback operator API.

```bash
ros2 launch cellforge_bringup integrated_runtime.launch.py \
  bundle_root:=/absolute/path/to/bundle fidelity:=L0 \
  local_state_root:=/var/lib/cellforge operator_auth:=/etc/cellforge/operator-auth.json
```

Only the fixed manifest runtime graph is accepted. L2 is deliberately unavailable until a genuine
Isaac Sim adapter is supplied by Task 027. The coordinator performs standard-control validation;
it cannot enforce, reset, or bypass independent rated safety hardware.
