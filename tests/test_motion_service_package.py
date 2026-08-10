from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ros_ws" / "src" / "cellforge_motion"


def test_motion_package_declares_cpp20_moveit_mtc_and_fake_backend_tests() -> None:
    package = ET.parse(PACKAGE / "package.xml").getroot()
    dependencies = {node.text for node in package.findall("depend")}
    assert {
        "cellforge_interfaces",
        "moveit_msgs",
        "moveit_ros_planning_interface",
        "moveit_task_constructor_core",
        "rclcpp",
        "rclcpp_action",
    } <= dependencies
    cmake = (PACKAGE / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "set(CMAKE_CXX_STANDARD 20)" in cmake
    assert "ament_add_gtest(test_motion_service" in cmake
    assert "cellforge_motion_service" in cmake


def test_task_logic_contracts_do_not_expose_planner_plugin_names() -> None:
    for name in ("MoveToPose.action", "ExecuteManipulation.action"):
        action = (ROOT / "ros_interfaces" / "action" / name).read_text(encoding="utf-8")
        assert "planner_id" not in action
        assert "planning_pipeline" not in action
        assert "plan_only" in action
    planner_config = (PACKAGE / "config" / "ompl_planning.yaml").read_text(encoding="utf-8")
    assert "planning_plugin" in planner_config


def test_reference_fake_controller_has_exactly_six_ordered_joints() -> None:
    config = yaml.safe_load((PACKAGE / "config" / "moveit_controllers.yaml").read_text())
    joints = config["moveit_simple_controller_manager"]["reference_robot_controller"]["joints"]
    assert joints == [f"joint_{index}" for index in range(1, 7)]


def test_motion_source_maps_required_stable_failures_and_cancellation() -> None:
    service = (PACKAGE / "src" / "motion_service.cpp").read_text(encoding="utf-8")
    required = {
        "motion.request.invalid_input",
        "motion.plan.unreachable",
        "motion.plan.collision",
        "motion.request.timeout",
        "motion.request.cancelled",
        "motion.execution.outcome_unknown",
        "motion.scene.rejected",
    }
    assert all(code in service for code in required)
    assert "cancelActiveRequest" in service
    assert "safety_claim" in service


def test_mtc_builder_and_node_expose_only_stable_application_services() -> None:
    builder = (PACKAGE / "src" / "mtc_task_builder.cpp").read_text(encoding="utf-8")
    assert "CurrentState" in builder
    assert builder.count("MoveTo") >= 2
    assert "ModifyPlanningScene" in builder
    assert "attachObject" in builder
    assert "detachObject" in builder

    node = (PACKAGE / "src" / "motion_node.cpp").read_text(encoding="utf-8")
    assert '"/skills/move_to_pose"' in node
    assert '"/skills/execute_manipulation"' in node
    assert '"/motion/sync_planning_scene"' in node
    assert '"/events/job"' in node
