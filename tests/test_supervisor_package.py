from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ros_ws" / "src" / "cellforge_supervisor"


def test_supervisor_package_declares_cpp20_and_runtime_contracts() -> None:
    package = ET.parse(PACKAGE / "package.xml").getroot()
    dependencies = {element.text for element in package.findall("depend")}
    assert {
        "behaviortree_cpp",
        "cellforge_interfaces",
        "rclcpp",
        "rclcpp_action",
        "std_msgs",
    } <= dependencies

    cmake = (PACKAGE / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "set(CMAKE_CXX_STANDARD 20)" in cmake
    assert "cellforge_supervisor_node" in cmake
    assert "cellforge_supervisor_bt_nodes" in cmake
    assert "ament_add_gtest(test_tree_validation" in cmake
    assert "ament_add_gtest(test_supervisor_nodes" in cmake
    assert "ament_add_gtest(test_supervisor_node" in cmake


def test_action_wrapper_has_no_blocking_future_waits() -> None:
    source = (PACKAGE / "src" / "supervisor_nodes.cpp").read_text(encoding="utf-8")
    assert ".get()" not in source
    assert "wait_for_action_server" not in source
    assert "async_send_goal" in source
    assert "async_cancel_goal" in source
    assert "action_server_is_ready" in source


def test_mock_tree_uses_registered_nodes_and_versioned_filename() -> None:
    tree_path = PACKAGE / "config" / "mock_workflow@1.xml"
    root = ET.parse(tree_path).getroot()
    tags = {element.tag for element in root.iter()}
    assert {"CellReady", "ExecuteSkill"} <= tags
    assert "@1" in tree_path.stem
