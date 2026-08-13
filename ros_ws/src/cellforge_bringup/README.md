# CellForge integrated bringup

`cellforge_bringup` launches the immutable, offline L0 or genuine Isaac Sim 6 L2 reference-cell
runtime. It verifies the
bundle ID and launch-critical file inventory before composing contract adapters, read-only safety
status, deterministic L0 motion, state and trace services, the frozen behavior-tree supervisor,
job gateway, semantic recovery coordinator, and loopback operator API.

```bash
ros2 launch cellforge_bringup integrated_runtime.launch.py \
  bundle_root:=/absolute/path/to/bundle fidelity:=L0 \
  local_state_root:=/var/lib/cellforge operator_auth:=/etc/cellforge/operator-auth.json
```

For L2, use the `pen-isaac-l2-win64` bundle and pass a declared scenario when overriding the
bundle's nominal scenario:

```powershell
ros2 launch cellforge_bringup integrated_runtime.launch.py `
  bundle_root:=C:\path\to\bundle fidelity:=L2 `
  l2_scenario:=C:\path\to\scenario.yaml \
  l2_scenario_root:=C:\path\to\examples\pen_engraving \
  l2_report:=C:\path\to\adapter-events.json
```

Only the two fixed manifest runtime graphs are accepted. L2 starts the real MoveIt/MTC service and
the single Kit-hosted adapter process; it never substitutes L0 mocks when Isaac or its GPU is
unavailable. The coordinator performs standard-control validation; it cannot enforce, reset, or
bypass independent rated safety hardware.
