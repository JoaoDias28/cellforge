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
file changes. The `cellforge_domain` package currently has no runtime dependencies.

Task 001 does not implement schema/example validation. `make validate-examples` deliberately exits
with status 2 and explains that Task 003 must wire the validator. This failure must not be waived or
reported as successful validation.

## ROS 2 workspace

Follow the official ROS 2 Jazzy installation instructions for Ubuntu 24.04 and install colcon:

```bash
sudo apt install ros-jazzy-ros-base python3-colcon-common-extensions
make ros-build
make ros-test
```

The Make targets source `/opt/ros/jazzy/setup.bash` themselves. Override `ROS_SETUP` only when using
an intentional nonstandard installation. Build products stay under `ros_ws/build`, `ros_ws/install`,
and `ros_ws/log` and are ignored by Git.

The `cellforge_interfaces` package is only a buildable placeholder. Canonical files in
`ros_interfaces/` remain source design artifacts until Task 007 adds ROS type generation.

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

No browser, cloud service, or engineering workstation is required by any production ROS node as a
result of this bootstrap.
