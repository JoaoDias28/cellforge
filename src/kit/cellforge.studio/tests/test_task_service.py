"""Tests for TaskAuthoringService: plugin manifests, XML serialization, and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from cellforge.studio.application import ProjectContents
from cellforge.studio.task_service import (
    NodeCategory,
    TaskAuthoringService,
)

ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = ROOT / "schemas"
EXAMPLES_PEN = ROOT / "examples" / "pen_engraving"


@pytest.fixture
def service() -> TaskAuthoringService:
    return TaskAuthoringService(SCHEMAS)


@pytest.fixture
def pen_contents() -> ProjectContents:
    cell_yaml = (EXAMPLES_PEN / "cell.yaml").read_text(encoding="utf-8")
    scene_usda = (EXAMPLES_PEN / "scene.usda").read_text(encoding="utf-8")
    tree_xml = (EXAMPLES_PEN / "behavior_tree.xml").read_bytes()
    return ProjectContents(
        cell_yaml=cell_yaml,
        scene_usda=scene_usda,
        artifacts={"behavior_tree.xml": tree_xml},
    )


def test_discover_registered_nodes(service: TaskAuthoringService) -> None:
    specs = service.discover_node_specs(EXAMPLES_PEN)
    node_types = {s.type for s in specs}

    # Verify standard control and decorator nodes
    assert "Sequence" in node_types
    assert "Fallback" in node_types
    assert "Parallel" in node_types
    assert "ReactiveSequence" in node_types
    assert "ReactiveFallback" in node_types
    assert "Repeat" in node_types
    assert "RetryUntilSuccessful" in node_types
    assert "Inverter" in node_types
    assert "ForceSuccess" in node_types
    assert "ForceFailure" in node_types
    assert "KeepRunningUntilFailure" in node_types

    # Verify discovered plugin nodes from pen_engraving
    assert "ExecuteProcess" in node_types
    assert "LocateProduct" in node_types
    assert "InspectProduct" in node_types
    assert "LoadFixture" in node_types
    assert "CheckRequiredDevicesReady" in node_types

    # Check port attributes on a known plugin node
    proc_spec = next(s for s in specs if s.type == "ExecuteProcess")
    assert proc_spec.category == NodeCategory.ACTION
    port_names = {p.name for p in proc_spec.ports}
    assert "program" in port_names
    assert "recipe_id" in port_names


def test_parse_and_format_xml_round_trip(
    service: TaskAuthoringService, pen_contents: ProjectContents
) -> None:
    raw_xml = pen_contents.artifacts["behavior_tree.xml"].decode("utf-8")
    tree_model = service.parse_task_xml(raw_xml)

    assert tree_model.id == "PenEngraving"
    assert tree_model.main_tree_to_execute == "PenEngraving"
    assert tree_model.root is not None
    assert tree_model.root.type in ("Sequence", "ReactiveSequence")

    # Serialize back to XML
    emitted_xml = service.generate_task_xml(tree_model, include_layout=True)
    assert "<root" in emitted_xml
    assert 'BTCPP_format="4"' in emitted_xml
    assert "<BehaviorTree" in emitted_xml

    # Re-parse emitted XML and ensure equivalence
    reparsed = service.parse_task_xml(emitted_xml)
    assert reparsed.main_tree_to_execute == tree_model.main_tree_to_execute
    assert reparsed.root.type == tree_model.root.type
    assert len(reparsed.root.children) == len(tree_model.root.children)


def test_layout_metadata_preservation(service: TaskAuthoringService) -> None:
    xml_with_layout = """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence _x="100.5" _y="200.0" _collapsed="false">
      <CheckRequiredDevicesReady _x="50.0" _y="300.0" ready="true"/>
    </Sequence>
  </BehaviorTree>
  <TreeNodesModel/>
</root>"""
    model = service.parse_task_xml(xml_with_layout)
    assert model.root.layout.get("x") == 100.5 or model.root.layout.get("x") == "100.5"
    assert model.root.layout.get("y") == 200.0 or model.root.layout.get("y") == "200.0"
    assert (
        model.root.layout.get("collapsed") is False or model.root.layout.get("collapsed") == "false"
    )
    assert (
        model.root.children[0].layout.get("x") == 50.0
        or model.root.children[0].layout.get("x") == "50.0"
    )

    emitted = service.generate_task_xml(model, include_layout=True)
    assert '_x="100.5"' in emitted
    assert '_y="200.0"' in emitted
    assert '_x="50.0"' in emitted


def test_validation_rejects_unknown_node_type(service: TaskAuthoringService) -> None:
    bad_xml = """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <NonExistentCustomAction foo="bar"/>
    </Sequence>
  </BehaviorTree>
</root>"""
    model = service.parse_task_xml(bad_xml)
    available_specs = {s.type: s for s in service.discover_node_specs(EXAMPLES_PEN)}
    findings = service.validate_tree(model, available_specs=available_specs)
    codes = [f.code for f in findings]
    assert "compiler.behavior-tree-node-unknown" in codes


def test_validation_rejects_missing_required_ports(service: TaskAuthoringService) -> None:
    bad_xml = """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <!-- CheckRequiredDevicesReady requires ready port -->
      <CheckRequiredDevicesReady/>
    </Sequence>
  </BehaviorTree>
</root>"""
    model = service.parse_task_xml(bad_xml)
    available_specs = {s.type: s for s in service.discover_node_specs(EXAMPLES_PEN)}
    findings = service.validate_tree(model, available_specs=available_specs)
    codes = [f.code for f in findings]
    assert "compiler.behavior-tree-port-missing" in codes


def test_validation_rejects_malformed_blackboard_syntax(service: TaskAuthoringService) -> None:
    bad_xml = """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <CheckRequiredDevicesReady ready="{invalid bb pointer}"/>
    </Sequence>
  </BehaviorTree>
</root>"""
    model = service.parse_task_xml(bad_xml)
    available_specs = {s.type: s for s in service.discover_node_specs(EXAMPLES_PEN)}
    findings = service.validate_tree(model, available_specs=available_specs)
    codes = [f.code for f in findings]
    assert "compiler.behavior-tree-mapping-invalid" in codes


def test_validation_rejects_unbound_blackboard_keys(service: TaskAuthoringService) -> None:
    bad_xml = """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <!-- Reads {unproduced_ready} which is never produced by prior output port -->
      <CheckRequiredDevicesReady ready="{unproduced_ready}"/>
    </Sequence>
  </BehaviorTree>
</root>"""
    model = service.parse_task_xml(bad_xml)
    available_specs = {s.type: s for s in service.discover_node_specs(EXAMPLES_PEN)}
    findings = service.validate_tree(model, available_specs=available_specs)
    codes = [f.code for f in findings]
    assert "compiler.behavior-tree-mapping-unresolved" in codes


def test_validation_prohibits_execute_process_under_retry(service: TaskAuthoringService) -> None:
    bad_xml = """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <RetryUntilSuccessful num_attempts="3">
        <ExecuteProcess program="P" variable_data="{v}" recipe_id="r" recipe_version="1"/>
      </RetryUntilSuccessful>
    </Sequence>
  </BehaviorTree>
</root>"""
    model = service.parse_task_xml(bad_xml)
    available_specs = {s.type: s for s in service.discover_node_specs(EXAMPLES_PEN)}
    findings = service.validate_tree(model, available_specs=available_specs)
    codes = [f.code for f in findings]
    assert "compiler.behavior-tree-process-retry-forbidden" in codes


def test_browse_and_set_task_tree_in_memory(
    service: TaskAuthoringService, pen_contents: ProjectContents
) -> None:
    browser = service.browse(EXAMPLES_PEN, pen_contents)
    assert len(browser.tasks) > 0
    assert len(browser.available_node_specs) > 0

    task = browser.tasks[0]
    assert task.valid is True

    valid_edit_xml = """<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <CheckRequiredDevicesReady ready="true"/>
    </Sequence>
  </BehaviorTree>
  <TreeNodesModel/>
</root>"""
    result = service.set_task_tree(EXAMPLES_PEN, pen_contents, task_id=task.id, tree=valid_edit_xml)
    assert result.contents is not None
    assert len(result.validation) == 0

    # Ensure memory buffer was updated and contains the new XML
    saved_bytes = result.contents.artifacts[task.behavior_tree_path]
    assert b"CheckRequiredDevicesReady" in saved_bytes
