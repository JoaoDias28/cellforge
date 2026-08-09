from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEVICE_SDK_ROOT = REPOSITORY_ROOT / "ros_ws" / "src" / "cellforge_device_sdk"
MOCK_ROOT = REPOSITORY_ROOT / "ros_ws" / "src" / "cellforge_mock_adapters"
for package_root in (DEVICE_SDK_ROOT, MOCK_ROOT):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from cellforge_mock_adapters.headless import (  # noqa: E402
    PenHeadlessExecutor,
    ScenarioError,
    ScenarioResult,
    load_scenario,
    load_scenarios,
    run_scenario,
    run_suite,
    verify_or_write_golden,
    write_reports,
)

EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "pen_engraving"
SCENARIO_ROOT = EXAMPLE_ROOT / "scenarios"
TREE_PATH = EXAMPLE_ROOT / "behavior_tree.xml"
GOLDEN_ROOT = EXAMPLE_ROOT / "golden_traces"


def result_by_id() -> dict[str, ScenarioResult]:
    results = asyncio.run(run_suite(SCENARIO_ROOT, TREE_PATH))
    return {result.scenario_id: result for result in results}


def test_all_required_pen_scenarios_pass_and_match_golden_traces() -> None:
    results = asyncio.run(run_suite(SCENARIO_ROOT, TREE_PATH))

    assert len(results) == 10
    assert all(result.passed for result in results)
    assert verify_or_write_golden(results, GOLDEN_ROOT, write=False) == ()
    assert {result.final_status for result in results} == {
        "SUCCESS",
        "RECOVERABLE_FAULT",
        "CANCELLED",
        "OUTCOME_UNKNOWN",
        "REJECTED",
    }


def test_seed_replay_reproduces_identical_normalized_event_sequence() -> None:
    scenario = load_scenario(SCENARIO_ROOT / "process_outcome_unknown.yaml")

    first = asyncio.run(run_scenario(scenario, TREE_PATH))
    replay = asyncio.run(run_scenario(scenario, TREE_PATH))

    assert first.normalized_trace() == replay.normalized_trace()
    assert [event.command_id for event in first.trace] == [
        event.command_id for event in replay.trace
    ]


def test_safety_unhealthy_refuses_before_any_adapter_or_process_command() -> None:
    result = result_by_id()["pen-safety-unhealthy"]
    event_types = [event.event_type for event in result.trace]

    assert result.final_status == "REJECTED"
    assert "safety.unhealthy" in event_types
    assert "device.command.requested" not in event_types
    assert "process.command.requested" not in event_types
    assert "job.started" not in event_types


def test_uncertain_process_outcome_is_not_retried_or_followed_by_inspection() -> None:
    result = result_by_id()["pen-process-outcome-unknown"]
    process_requests = [
        event for event in result.trace if event.event_type == "process.command.requested"
    ]
    entered_nodes = [
        event.node for event in result.trace if event.event_type == "behavior_tree.node.entered"
    ]

    assert result.final_status == "OUTCOME_UNKNOWN"
    assert len(process_requests) == 1
    assert not process_requests[0].outcome_certain or any(
        event.event_type == "laser.process.outcome_unknown" and not event.outcome_certain
        for event in result.trace
    )
    assert "InspectProduct" not in entered_nodes
    assert "process.command.retried" not in [event.event_type for event in result.trace]


def test_reports_are_valid_json_and_junit(tmp_path: Path) -> None:
    results = asyncio.run(run_suite(SCENARIO_ROOT, TREE_PATH))
    write_reports(results, tmp_path)

    report = json.loads((tmp_path / "pen-headless-report.json").read_text(encoding="utf-8"))
    junit = ElementTree.parse(tmp_path / "pen-headless-junit.xml").getroot()

    assert report["passed"] is True
    assert report["scenario_count"] == 10
    assert len(report["results"]) == 10
    assert junit.tag == "testsuite"
    assert junit.attrib == {"name": "pen-headless", "tests": "10", "failures": "0"}


def test_invalid_scenario_and_unknown_tree_node_fail_closed(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.yaml"
    malformed.write_text("schema_version: 9.9.9\n", encoding="utf-8")
    with pytest.raises(ScenarioError, match="schema_version"):
        load_scenario(malformed)

    scenario = load_scenario(SCENARIO_ROOT / "nominal.yaml")
    tree = tmp_path / "unknown.xml"
    tree.write_text(
        '<root BTCPP_format="4"><BehaviorTree ID="x"><UnknownNode/></BehaviorTree></root>',
        encoding="utf-8",
    )
    with pytest.raises(ScenarioError, match="unsupported pen node"):
        asyncio.run(PenHeadlessExecutor(scenario, tree).execute())


def test_reference_tree_has_explicit_frozen_and_process_port_mappings() -> None:
    tree = ElementTree.parse(TREE_PATH).getroot()
    validate = tree.find(".//ValidateFrozenJob")
    process = tree.find(".//ExecuteProcess")

    assert validate is not None
    assert set(validate.attrib) == {
        "job_id",
        "cell_id",
        "recipe_id",
        "recipe_version",
        "input_payload_json",
        "execution_mode",
    }
    assert process is not None
    assert process.attrib == {
        "program": "ALU_REFERENCE_01",
        "variable_data": "{input_payload_json}",
        "recipe_id": "{recipe_id}",
        "recipe_version": "{recipe_version}",
    }


def test_scenario_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    source = (SCENARIO_ROOT / "nominal.yaml").read_text(encoding="utf-8")
    (tmp_path / "one.yaml").write_text(source, encoding="utf-8")
    (tmp_path / "two.yaml").write_text(source, encoding="utf-8")

    with pytest.raises(ScenarioError, match="duplicate scenario identifiers"):
        load_scenarios(tmp_path)
