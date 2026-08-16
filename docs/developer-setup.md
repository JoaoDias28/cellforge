# Developer setup

## Supported baseline

CellForge targets Ubuntu 24.04, Python 3.12, and ROS 2 Jazzy. Python-only work is also supported
on other operating systems, but the root ROS commands and CI baseline are Ubuntu-specific.
Isaac Sim is intentionally not part of the Task 001 development or CI environment.

## Python workspace

Install [`uv`](https://docs.astral.sh/uv/) 0.10.0 or a compatible release, then run:

```bash
uv sync --locked --all-packages
make lint
make test
```

The committed `uv.lock` is the reproducible dependency source for CI and development. Do not use
`uv sync --upgrade` during ordinary setup; dependency upgrades should be explicit, reviewed lock
file changes. Runtime dependencies and their removal paths are documented in each Python package
README.

`make validate-examples` runs the pure Task 003 schema, domain, and cross-file validator. The Task
004 console entry point is available after synchronization:

```bash
cellforge --help
cellforge example copy pen-engraving /tmp/pen-example
cellforge validate /tmp/pen-example
```

See `docs/cli.md` for commands, JSON output, and stable exit codes. These engineering commands do
not require ROS or Isaac Sim and do not authorize physical execution.

## ROS 2 workspace

Follow the official ROS 2 Jazzy installation instructions for Ubuntu 24.04 and install colcon:

```bash
sudo apt install ros-jazzy-ros-base python3-colcon-common-extensions nlohmann-json3-dev
make ros-build
make ros-test
```

The Make targets source `/opt/ros/jazzy/setup.bash` themselves. Override `ROS_SETUP` only when using
an intentional nonstandard installation. Build products stay under `ros_ws/build`, `ros_ws/install`,
and `ros_ws/log` and are ignored by Git.

The `cellforge_interfaces` package generates the canonical Task 007 messages, services, and
actions copied from `ros_interfaces/`. The parity test prevents the packaged definitions from
drifting from those canonical source files.

## Formatting and static analysis

Python formatting, linting, and type checks are configured in the root `pyproject.toml` and run by
`make lint`. C++20 formatting and static-analysis defaults are stored in `.clang-format` and
`.clang-tidy`; later ROS C++ packages must invoke them through their ament lint configuration.

## Development dependency record

Task 001 adds no production dependency. Its development/build tools are:

| Tool | License | Maintenance | Reason | Removal path |
|---|---|---|---|---|
| uv | Apache-2.0 or MIT | Actively maintained by Astral | Lock and synchronize the Python workspace | Export pinned requirements and replace Make/CI commands |
| Hatchling | MIT | Actively maintained by PyPA | Build backend for workspace libraries | Change each package build backend and regenerate the lock |
| Ruff | MIT | Actively maintained by Astral | Python formatting and linting | Replace the root lint command/configuration |
| mypy | MIT | Actively maintained | Strict Python static type checking | Replace the root type-check command/configuration |
| pytest | MIT | Actively maintained | Python unit and contract test runner | Migrate tests and the root test command |
| PyYAML | MIT | Actively maintained | Parse CI YAML in bootstrap contract tests | Replace the YAML parser in the workflow test |

## Production dependency record

| Dependency | License | Maintenance | Reason | Removal path |
|---|---|---|---|---|
| BehaviorTree.CPP 4 (`behaviortree_cpp`, Jazzy resolves 4.6.2) | MIT | Active upstream releases and ROS packaging; accepted by ADR 0004 | Runtime XML behavior-tree execution, typed ports, asynchronous stateful actions, decorators, and transition subscriptions | Replace `cellforge_supervisor`'s factory/node layer with another implementation of the same `RunJob`, capability-action, state, event, XML, timeout, and cancellation contracts; revalidate every released tree before removing the package |
| nlohmann/json 3 (`nlohmann_json`, supplied by ROS packages or conda-forge) | MIT | Actively maintained upstream and packaged by Ubuntu/ROS and conda-forge | Parse the immutable bundle and behavior-tree node manifests before loading any runtime plugin | Replace the supervisor manifest reader with another supported JSON parser while preserving exact digest, containment, declaration, and registration validation |
| PyYAML 6 (`python3-yaml` in Ubuntu/ROS) | MIT | Actively maintained and distributed by Ubuntu | Safely parse frozen recipe documents in the offline job gateway and canonical L0 scenario documents in the headless mock runner; both remain data-only | Materialize canonical JSON recipes and scenarios before removing the package |

The supervisor deliberately does not add BehaviorTree.ROS2: its initial ROS wrapper is small and
keeps CellForge's stable result codes, exact tree resolution, and event semantics within the runtime
contract.

No browser, cloud service, or engineering workstation is required by any production ROS node as a
result of this bootstrap.

## Isaac Sim 6 extension development

Cell Studio's Task 014 shell is discovered from `src/kit` as extension `cellforge.studio`. Run its
deterministic tests without Isaac Sim using `make kit-extension-check`. See `docs/cell-studio.md` for
the interactive launch command and the exact Isaac Sim 6 `--no-window` lifecycle probe.

The extension has no additional PyPI production dependency. `omni.ext` and `omni.ui` are supplied
and maintained by the supported Isaac Sim 6 / Omniverse Kit installation. Removing the extension
directory removes this engineering-only integration without affecting the runtime or domain model.

Task 017 connection authoring can be checked without Kit using `make studio-connections-check`.
The Isaac Sim 6/OpenUSD probe is documented in `docs/cell-studio.md`; it validates composition of a
mechanically snapped prim and does not exercise or claim any hardware or functional-safety behavior.

## Integrated L0 runtime

After `make ros-build`, source `ros_ws/install/setup.bash` and launch a compiled bundle with:

```bash
ros2 launch cellforge_bringup integrated_runtime.launch.py \
  bundle_root:=/absolute/path/to/bundle fidelity:=L0 \
  local_state_root:=/var/lib/cellforge operator_auth:=/etc/cellforge/operator-auth.json
```

The launch is offline and loopback-only. For deterministic acceptance in a clean Jazzy environment,
run `make integrated-runtime-check`. `launch_testing` is a ROS Jazzy test dependency, maintained by
the ROS 2 project; removing the launch test removes that dependency without changing runtime code.
