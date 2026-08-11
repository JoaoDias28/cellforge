from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "pen_engraving"
PACKAGE = ROOT / "ros_ws" / "src" / "cellforge_pen_bt_nodes"


def test_pen_runtime_package_owns_every_canonical_leaf_and_typed_action_contract() -> None:
    tree = ElementTree.parse(EXAMPLE / "behavior_tree.xml").getroot()
    manifest = json.loads(
        (EXAMPLE / "behavior_tree_plugins" / "cellforge_pen_bt_nodes.json").read_text(
            encoding="utf-8"
        )
    )
    declared = {node["type"] for node in manifest["nodes"]}
    controls = {"root", "BehaviorTree", "Sequence", "RetryUntilSuccessful"}
    used = {element.tag for element in tree.iter()} - controls
    assert used == declared

    source = (PACKAGE / "src" / "pen_nodes.cpp").read_text(encoding="utf-8")
    header = (PACKAGE / "include" / "cellforge_pen_bt_nodes" / "pen_nodes.hpp").read_text(
        encoding="utf-8"
    )
    for action in (
        "LocateObject",
        "ExecuteManipulation",
        "MoveToPose",
        "ExecuteSkill",
        "ExecuteProcess",
        "InspectObject",
    ):
        assert f"action::{action}" in header
    assert "process_outcome_unknown" in source
    assert "async_send_goal" in (
        PACKAGE / "include" / "cellforge_pen_bt_nodes" / "typed_action_node_impl.hpp"
    ).read_text(encoding="utf-8")


def test_runtime_trace_expectations_are_a_normalized_projection_of_the_python_oracle() -> None:
    expectations = json.loads(
        (EXAMPLE / "runtime_trace_expectations.json").read_text(encoding="utf-8")
    )
    golden_root = EXAMPLE / "golden_traces"
    assert set(expectations) == {path.stem for path in golden_root.glob("*.json")}
    for scenario_id, expected in expectations.items():
        oracle = json.loads((golden_root / f"{scenario_id}.json").read_text(encoding="utf-8"))
        oracle_nodes = [
            event["node"] for event in oracle if event["event_type"] == "behavior_tree.node.entered"
        ]
        assert expected["nodes"] == oracle_nodes
        assert expected["final_status"] in {
            "SUCCESS",
            "RECOVERABLE_FAULT",
            "CANCELLED",
            "OUTCOME_UNKNOWN",
            "REJECTED",
        }


def test_runtime_plugin_is_bundle_declared_and_not_a_python_dependency() -> None:
    profile = (EXAMPLE / "deployment-sim.yaml").read_text(encoding="utf-8")
    assert "cellforge_pen_bt_nodes" in profile
    assert "behavior_tree_plugins:" in profile
    package = ElementTree.parse(PACKAGE / "package.xml").getroot()
    dependencies = {element.text for element in package.findall("depend")}
    assert "cellforge_mock_adapters" not in dependencies
    assert "cellforge_job_gateway" not in dependencies
