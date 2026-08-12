UV ?= uv
ROS_DISTRO ?= jazzy
ROS_SETUP ?= /opt/ros/$(ROS_DISTRO)/setup.bash
ROS_WORKSPACE ?= ros_ws
COLCON ?= colcon

.PHONY: lint test validate-examples kit-extension-check studio-project-scene-check studio-component-placement-check studio-connections-check studio-simulation-check motion-service-check pen-physical-sim-check bundle-agent-check bundle-assembly-check operator-api-check integrated-runtime-check ros-build ros-test

lint:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen ruff format --check .
	$(UV) run --frozen ruff check .
	$(UV) run --frozen mypy src/python/cellforge_domain/src src/python/cellforge_domain/tests src/python/cellforge_bundle/src src/python/cellforge_bundle/tests src/python/cellforge_cli/src src/python/cellforge_cli/tests ros_ws/src/cellforge_device_sdk/cellforge_device_sdk ros_ws/src/cellforge_mock_adapters/cellforge_mock_adapters ros_ws/src/cellforge_state_trace/cellforge_state_trace ros_ws/src/cellforge_job_gateway/cellforge_job_gateway ros_ws/src/cellforge_operator_api/cellforge_operator_api ros_ws/src/cellforge_simulation/cellforge_simulation ros_ws/src/cellforge_bringup/cellforge_bringup tests
	$(UV) run --frozen mypy --explicit-package-bases src/kit/cellforge.studio/cellforge/studio/application.py src/kit/cellforge.studio/cellforge/studio/backend.py src/kit/cellforge.studio/cellforge/studio/component_service.py src/kit/cellforge.studio/cellforge/studio/connection_service.py src/kit/cellforge.studio/cellforge/studio/project_service.py src/kit/cellforge.studio/cellforge/studio/scene.py src/kit/cellforge.studio/cellforge/studio/simulation_application.py src/kit/cellforge.studio/cellforge/studio/simulation_backend.py src/kit/cellforge.studio/cellforge/studio/simulation_host.py src/kit/cellforge.studio/tests

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

studio-component-placement-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest src/kit/cellforge.studio/tests/test_component_service.py
	$(UV) run --frozen python scripts/verify_studio_component_placement.py

studio-connections-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest src/kit/cellforge.studio/tests/test_connection_service.py
	$(UV) run --frozen python scripts/verify_studio_connections.py

studio-simulation-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest tests/test_simulation_control.py src/kit/cellforge.studio/tests/test_simulation_application.py
	$(UV) run --frozen python scripts/verify_studio_simulation.py

motion-service-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest tests/test_motion_service_package.py tests/test_ros_interface_definitions.py
	$(UV) run --frozen python scripts/verify_motion_service.py

pen-physical-sim-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest tests/test_pen_physical_sim.py
	$(UV) run --frozen python scripts/verify_pen_physical_sim.py

bundle-agent-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest src/python/cellforge_bundle/tests/test_agent.py tests/test_state_trace.py
	$(UV) run --frozen python scripts/verify_bundle_agent.py

bundle-assembly-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest src/python/cellforge_bundle/tests/test_assembly.py src/python/cellforge_bundle/tests/test_agent.py

operator-api-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest tests/test_operator_api.py tests/test_ros_interface_definitions.py
	$(UV) run --frozen python scripts/verify_operator_api.py

integrated-runtime-check:
	$(UV) sync --locked --all-packages
	$(UV) run --frozen pytest tests/test_integrated_runtime.py src/python/cellforge_bundle/tests/test_compiler.py
	bash -c 'set -eo pipefail; source "$(ROS_SETUP)"; set -u; cd "$(ROS_WORKSPACE)"; $(COLCON) build --packages-up-to cellforge_bringup --event-handlers console_direct+'
	bash -c 'set -eo pipefail; source "$(ROS_SETUP)"; cd "$(ROS_WORKSPACE)"; source "install/setup.bash"; set -u; $(COLCON) test --packages-select cellforge_bringup --return-code-on-test-failure --event-handlers console_direct+; $(COLCON) test-result --test-result-base build/cellforge_bringup --verbose'

ros-build:
	bash -c 'set -eo pipefail; source "$(ROS_SETUP)"; set -u; cd "$(ROS_WORKSPACE)"; $(COLCON) build --symlink-install --event-handlers console_direct+'

ros-test:
	bash -c 'set -eo pipefail; source "$(ROS_SETUP)"; cd "$(ROS_WORKSPACE)"; source "install/setup.bash"; set -u; $(COLCON) test --return-code-on-test-failure --event-handlers console_direct+; $(COLCON) test-result --verbose'
