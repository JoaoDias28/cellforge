UV ?= uv
ROS_DISTRO ?= jazzy
ROS_SETUP ?= /opt/ros/$(ROS_DISTRO)/setup.bash
ROS_WORKSPACE ?= ros_ws
COLCON ?= colcon

.PHONY: lint test validate-examples ros-build ros-test

lint:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen ruff format --check .
	$(UV) run --frozen ruff check .
	$(UV) run --frozen mypy src/python/cellforge_domain/src src/python/cellforge_domain/tests tests

test:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest

validate-examples:
	@echo "Schema/example validation is not wired; Task 003 will implement it." 1>&2; exit 2

ros-build:
	bash -c 'set -eo pipefail; source "$(ROS_SETUP)"; set -u; cd "$(ROS_WORKSPACE)"; $(COLCON) build --symlink-install --event-handlers console_direct+'

ros-test:
	bash -c 'set -eo pipefail; source "$(ROS_SETUP)"; set -u; cd "$(ROS_WORKSPACE)"; $(COLCON) test --return-code-on-test-failure --event-handlers console_direct+; $(COLCON) test-result --verbose'
