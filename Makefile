UV ?= uv
ROS_DISTRO ?= jazzy
ROS_SETUP ?= /opt/ros/$(ROS_DISTRO)/setup.bash
ROS_WORKSPACE ?= ros_ws
COLCON ?= colcon

.PHONY: lint test validate-examples kit-extension-check studio-project-scene-check ros-build ros-test

lint:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen ruff format --check .
	$(UV) run --frozen ruff check .
	$(UV) run --frozen mypy src/python/cellforge_domain/src src/python/cellforge_domain/tests src/python/cellforge_bundle/src src/python/cellforge_bundle/tests src/python/cellforge_cli/src src/python/cellforge_cli/tests ros_ws/src/cellforge_device_sdk/cellforge_device_sdk ros_ws/src/cellforge_mock_adapters/cellforge_mock_adapters ros_ws/src/cellforge_state_trace/cellforge_state_trace ros_ws/src/cellforge_job_gateway/cellforge_job_gateway tests
	$(UV) run --frozen mypy --explicit-package-bases src/kit/cellforge.studio/cellforge/studio/application.py src/kit/cellforge.studio/cellforge/studio/backend.py src/kit/cellforge.studio/cellforge/studio/project_service.py src/kit/cellforge.studio/cellforge/studio/scene.py src/kit/cellforge.studio/tests

test:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest

validate-examples:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving

kit-extension-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest src/kit/cellforge.studio/tests
	$(UV) run --frozen python scripts/verify_kit_extension_manifest.py

studio-project-scene-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest src/kit/cellforge.studio/tests/test_project_service.py
	$(UV) run --frozen python scripts/verify_studio_project_scene.py

ros-build:
	bash -c 'set -eo pipefail; source "$(ROS_SETUP)"; set -u; cd "$(ROS_WORKSPACE)"; $(COLCON) build --symlink-install --event-handlers console_direct+'

ros-test:
	bash -c 'set -eo pipefail; source "$(ROS_SETUP)"; cd "$(ROS_WORKSPACE)"; source "install/setup.bash"; set -u; $(COLCON) test --return-code-on-test-failure --event-handlers console_direct+; $(COLCON) test-result --verbose'
