from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MOTION = ROOT / "ros_ws" / "src" / "cellforge_motion"
INTERFACES = ROOT / "ros_interfaces"
REFERENCE_COMPONENT = ROOT / "examples" / "pen_engraving" / "components" / "robot"
JOINTS = {f"joint_{index}" for index in range(1, 7)}
SAFE_POSES = {"home", "process_safe", "load_safe", "unload_safe"}


def joint_names(path: Path) -> set[str]:
    root = ET.parse(path).getroot()
    return {
        name for element in root.iter("joint") if (name := element.attrib.get("name", "")) in JOINTS
    }


def verify() -> None:
    component_urdf = REFERENCE_COMPONENT / "robot_description" / "robot.urdf.xacro"
    moveit_xacro = MOTION / "config" / "reference_robot_links.xacro"
    srdf = ET.parse(MOTION / "config" / "reference_robot.srdf").getroot()
    states = {element.attrib["name"] for element in srdf.findall("group_state")}
    assert joint_names(component_urdf) == JOINTS
    assert joint_names(moveit_xacro) == JOINTS
    assert SAFE_POSES <= states
    for state in srdf.findall("group_state"):
        if state.attrib["name"] in SAFE_POSES:
            assert {joint.attrib["name"] for joint in state.findall("joint")} == JOINTS

    limits = yaml.safe_load((MOTION / "config" / "joint_limits.yaml").read_text())
    assert set(limits["joint_limits"]) == JOINTS
    kinematics = yaml.safe_load((MOTION / "config" / "kinematics.yaml").read_text())
    assert "manipulator" in kinematics
    controllers = yaml.safe_load((MOTION / "config" / "moveit_controllers.yaml").read_text())
    assert controllers["moveit_simple_controller_manager"]["reference_robot_controller"][
        "joints"
    ] == sorted(JOINTS)

    for action in ("MoveToPose.action", "ExecuteManipulation.action"):
        text = (INTERFACES / "action" / action).read_text(encoding="utf-8")
        assert "bool plan_only" in text
        assert "string command_id" in text and "string trace_id" in text
        assert not re.search(r"planner(_id)?|planning_pipeline", text, re.IGNORECASE)
    scene = (INTERFACES / "srv" / "SyncPlanningScene.srv").read_text(encoding="utf-8")
    assert "cell_yaml_sha256" in scene and "usd_sha256" in scene

    print(
        "Verified Task 019 planner-neutral actions, canonical scene identity, "
        "six-axis reference model, four safe poses, limits, and fake controller config."
    )


if __name__ == "__main__":
    verify()
