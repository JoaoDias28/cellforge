"""GPU-independent Task 020 model, scene, MTC-contract, and 100-seed probe."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "ros_ws" / "src" / "cellforge_simulation"))
    from cellforge_simulation.physical import PenCycle, build_seed_report

    scene = (root / "examples" / "pen_engraving" / "scene.usda").read_text(encoding="utf-8")
    required_scene_tokens = (
        'def Xform "Robot"',
        'def Xform "Gripper"',
        'def Capsule "PenTemplate"',
        'def Xform "InputCarrier"',
        'def Xform "Fixture"',
        'def Xform "Laser"',
        'def Xform "Camera"',
        "PhysicsCollisionAPI",
        "PhysicsRigidBodyAPI",
    )
    missing = [token for token in required_scene_tokens if token not in scene]
    if missing:
        raise RuntimeError(f"Task 020 scene is missing {missing}")

    action = (root / "ros_interfaces" / "action" / "ExecuteManipulation.action").read_text()
    integration = (
        root
        / "ros_ws"
        / "src"
        / "cellforge_simulation"
        / "cellforge_simulation"
        / "motion_integration.py"
    ).read_text()
    srdf = (
        root / "ros_ws" / "src" / "cellforge_motion" / "config" / "reference_robot.srdf"
    ).read_text()
    for token in (
        "string operation",
        "string object_id",
        "string tool_frame",
        "string named_safe_pose",
    ):
        if token not in action:
            raise RuntimeError(f"MoveIt/MTC contract is missing '{token}'")
    for action_type in ("ExecuteManipulation.Goal", "MoveToPose.Goal"):
        if action_type not in integration:
            raise RuntimeError(f"Task 020 ROS mapping is missing '{action_type}'")
    for pose in ("load_safe", "process_safe", "unload_safe"):
        if f'name="{pose}"' not in srdf:
            raise RuntimeError(f"reference SRDF is missing '{pose}'")

    nominal = PenCycle(1001).run()
    if not nominal.passed:
        raise RuntimeError(f"nominal physical cycle failed: {nominal.fault_code}")
    operations = [command.operation for command in nominal.motion_commands]
    if operations != ["pick", "load", "process_safe", "unload"]:
        raise RuntimeError(f"unexpected MoveIt/MTC sequence: {operations}")

    first = build_seed_report()
    second = build_seed_report()
    encoded_first = json.dumps(first, sort_keys=True, separators=(",", ":")).encode()
    encoded_second = json.dumps(second, sort_keys=True, separators=(",", ":")).encode()
    if encoded_first != encoded_second:
        raise RuntimeError("100-seed report is not reproducible")
    if first["summary"] != {"passed": 100, "failed": 0}:
        raise RuntimeError(f"unexpected 100-seed summary: {first['summary']}")
    print(
        "Verified Task 020 scene, bounded spawning, MTC sequence, faults, collisions, and "
        f"100-seed replay ({hashlib.sha256(encoded_first).hexdigest()})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
