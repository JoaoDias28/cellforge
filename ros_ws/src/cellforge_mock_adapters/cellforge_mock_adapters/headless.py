"""Deterministic L0 executor for the canonical pen behavior tree.

This module is test infrastructure, not the production supervisor.  It executes the deliberately
small XML subset used by the reference pen tree and sends every device operation through the same
Task 008/009 adapter contracts used by ROS mock nodes.  It models sequencing and fault behavior;
it does not model physics, process quality, or functional safety.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn, cast
from uuid import NAMESPACE_URL, uuid5
from xml.etree import ElementTree

import yaml
from cellforge_device_sdk.models import CapabilityCommand, CommandResult

from cellforge_mock_adapters.core import MockDeviceAdapter
from cellforge_mock_adapters.devices import build_device_mock
from cellforge_mock_adapters.scenarios import parse_device_scenario

SCHEMA_VERSION = "0.1.0"
PROGRAM_ID = "ALU_REFERENCE_01"
CELL_ID = "0d3c6b63-a57f-4207-8638-e4cf76efec90"
ALLOWED_TOP_LEVEL_KEYS = {
    "schema_version",
    "scenario",
    "job",
    "initial_state",
    "randomization",
    "faults",
    "assertions",
}


class ScenarioError(ValueError):
    """A stable, user-safe scenario or tree configuration failure."""


class NodeStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    scenario_id: str
    name: str
    seed: int
    timeout_seconds: float
    job: dict[str, Any]
    initial_state: dict[str, Any]
    faults: tuple[dict[str, Any], ...]
    expected_status: str
    required_events: tuple[str, ...]
    forbidden_events: tuple[str, ...]
    source: Path


@dataclass(frozen=True, slots=True)
class TraceEvent:
    sequence: int
    event_type: str
    node: str
    component_instance_id: str
    command_id: str
    result_code: str
    outcome_certain: bool
    evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_id: str
    name: str
    seed: int
    final_status: str
    passed: bool
    failures: tuple[str, ...]
    trace: tuple[TraceEvent, ...]
    fidelity: str = (
        "L0 contract mock: sequencing and interface outcomes only; no physics, rendered "
        "perception, mark-quality, hardware, or functional-safety evidence."
    )

    def normalized_trace(self) -> list[dict[str, Any]]:
        """Return timestamp-free, byte-stable trace evidence."""

        return [asdict(event) for event in self.trace]

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["trace"] = self.normalized_trace()
        return data


def _fail(where: str, message: str) -> NoReturn:
    raise ScenarioError(f"{where}: {message}")


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(where, "expected an object")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(where, "expected a non-blank string")
    return value


def load_scenario(path: Path) -> ScenarioDefinition:
    """Load one strict scenario document used by the L0 runner."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ScenarioError(f"{path}: cannot load scenario: {error}") from error
    document = _mapping(raw, str(path))
    unknown = sorted(set(document) - ALLOWED_TOP_LEVEL_KEYS)
    if unknown:
        _fail(str(path), f"unknown top-level keys {unknown}")
    if document.get("schema_version") != SCHEMA_VERSION:
        _fail(str(path), f"schema_version must be '{SCHEMA_VERSION}'")

    identity = _mapping(document.get("scenario"), f"{path}.scenario")
    job = _mapping(document.get("job"), f"{path}.job")
    initial = _mapping(document.get("initial_state"), f"{path}.initial_state")
    assertions = _mapping(document.get("assertions"), f"{path}.assertions")
    seed = identity.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        _fail(f"{path}.scenario.seed", "expected an integer")
    timeout = identity.get("timeout_seconds", 60.0)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0:
        _fail(f"{path}.scenario.timeout_seconds", "expected a positive number")
    faults = document.get("faults", [])
    if not isinstance(faults, list) or not all(isinstance(item, dict) for item in faults):
        _fail(f"{path}.faults", "expected a list of objects")

    def event_list(name: str) -> tuple[str, ...]:
        values = assertions.get(name, [])
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            _fail(f"{path}.assertions.{name}", "expected a list of strings")
        return tuple(values)

    return ScenarioDefinition(
        scenario_id=_text(identity.get("id"), f"{path}.scenario.id"),
        name=_text(identity.get("name"), f"{path}.scenario.name"),
        seed=seed,
        timeout_seconds=float(timeout),
        job=job,
        initial_state=initial,
        faults=tuple(faults),
        expected_status=_text(assertions.get("final_status"), f"{path}.assertions.final_status"),
        required_events=event_list("required_events"),
        forbidden_events=event_list("forbidden_events"),
        source=path,
    )


def load_scenarios(root: Path) -> tuple[ScenarioDefinition, ...]:
    scenarios = tuple(load_scenario(path) for path in sorted(root.glob("*.yaml")))
    if not scenarios:
        raise ScenarioError(f"{root}: no .yaml scenarios found")
    identifiers = [scenario.scenario_id for scenario in scenarios]
    if len(identifiers) != len(set(identifiers)):
        raise ScenarioError(f"{root}: duplicate scenario identifiers")
    return scenarios


class PenHeadlessExecutor:
    """Execute pen leaf nodes against deterministic L0 adapters."""

    def __init__(self, scenario: ScenarioDefinition, tree_path: Path) -> None:
        self.scenario = scenario
        self.tree_path = tree_path
        self.trace_id = str(uuid5(NAMESPACE_URL, f"cellforge:{scenario.seed}:trace"))
        self.events: list[TraceEvent] = []
        self.command_ordinal = 0
        self.blackboard = self._blackboard()
        self.adapters = self._adapters()
        self.job_started = False
        self._tree_root = self._load_tree()

    def _blackboard(self) -> dict[str, Any]:
        job = self.scenario.job
        payload = _mapping(job.get("input_payload"), f"{self.scenario.source}.job.input_payload")
        recipe_version = job.get("recipe_version")
        if isinstance(recipe_version, bool) or not isinstance(recipe_version, int):
            _fail(f"{self.scenario.source}.job.recipe_version", "expected an integer")
        return {
            "job_id": str(uuid5(NAMESPACE_URL, f"cellforge:{self.scenario.seed}:job")),
            "cell_id": CELL_ID,
            "recipe_id": _text(job.get("recipe_id"), f"{self.scenario.source}.job.recipe_id"),
            "recipe_version": recipe_version,
            "input_payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":")),
            "execution_mode": "simulation",
            "cell_ready": bool(self.scenario.initial_state.get("safety_healthy", True)),
        }

    def _operation(self, fault: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"duration_seconds": 0.001}
        if fault:
            result["fault"] = fault
        return result

    def _fault_requested(self, name: str) -> bool:
        aliases = {
            "process_timeout": "laser.process.timeout",
            "communication_loss": "laser.process.outcome_unknown",
        }
        return any(
            aliases.get(str(item.get("fault")), item.get("fault")) == name
            for item in self.scenario.faults
        )

    def _adapters(self) -> dict[str, MockDeviceAdapter]:
        initial = self.scenario.initial_state
        process_fault = None
        if self._fault_requested("laser.process.timeout"):
            process_fault = "laser.process.timeout"
        elif self._fault_requested("laser.process.outcome_unknown"):
            process_fault = "laser.process.outcome_unknown"
        documents: dict[str, dict[str, Any]] = {
            "robot": {
                "component_instance_id": "robot-001",
                "device_kind": "robot",
                "operations": {"robot_motion.action.execute_trajectory": self._operation()},
            },
            "gripper": {
                "component_instance_id": "gripper-001",
                "device_kind": "gripper",
                "operations": {
                    "gripper.action.open": self._operation(),
                    "gripper.action.close": self._operation(),
                },
            },
            "fixture": {
                "component_instance_id": "fixture-001",
                "device_kind": "fixture",
                "operations": {
                    "fixture.action.clamp": self._operation(),
                    "fixture.action.release": self._operation(),
                    "fixture.action.verify_seated": self._operation(),
                },
                "device": {"seated": bool(initial.get("fixture_seated", True))},
            },
            "locator": {
                "component_instance_id": "camera-001",
                "device_kind": "vision_locator",
                "operations": {"vision.action.locate_object": self._operation()},
                "device": {
                    "object_present": bool(initial.get("product_present", True)),
                    "within_correction_limit": bool(initial.get("pose_within_limit", True)),
                },
            },
            "process": {
                "component_instance_id": "laser-001",
                "device_kind": "process_machine",
                "operations": {
                    "process.action.select_program": self._operation(),
                    "process.action.execute_cycle": self._operation(process_fault),
                },
                "device": {
                    "known_programs": [PROGRAM_ID],
                    "interlock_permitted": bool(initial.get("laser_ready", True)),
                },
            },
            "inspection": {
                "component_instance_id": "camera-001",
                "device_kind": "inspection",
                "operations": {"vision.action.inspect_object": self._operation()},
                "device": {
                    "accepted": bool(initial.get("inspection_matches", True)),
                    "measurements": {
                        "contrast": 0.9,
                        "text_match": bool(initial.get("inspection_matches", True)),
                    },
                },
            },
        }
        adapters = {
            name: build_device_mock(parse_device_scenario(document, where=f"{name}_mock"))
            for name, document in documents.items()
        }
        for adapter in adapters.values():
            adapter.mark_ready()
        return adapters

    def _load_tree(self) -> ElementTree.Element:
        try:
            root = ElementTree.parse(self.tree_path).getroot()
        except (OSError, ElementTree.ParseError) as error:
            raise ScenarioError(f"{self.tree_path}: cannot load behavior tree: {error}") from error
        tree = root.find("BehaviorTree")
        if tree is None or len(tree) != 1:
            raise ScenarioError(f"{self.tree_path}: expected one BehaviorTree child root")
        return tree[0]

    def emit(
        self,
        event_type: str,
        *,
        node: str = "",
        component: str = "",
        command_id: str = "",
        result_code: str = "",
        outcome_certain: bool = True,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            TraceEvent(
                sequence=len(self.events) + 1,
                event_type=event_type,
                node=node,
                component_instance_id=component,
                command_id=command_id,
                result_code=result_code,
                outcome_certain=outcome_certain,
                evidence=evidence or {},
            )
        )

    def _resolve(self, value: str) -> Any:
        if value.startswith("{") and value.endswith("}"):
            key = value[1:-1]
            if key not in self.blackboard:
                raise ScenarioError(f"{self.tree_path}: unresolved blackboard port '{key}'")
            return self.blackboard[key]
        return value

    def _ports(self, element: ElementTree.Element) -> dict[str, Any]:
        output_ports = {"output_pose", "measurements"}
        return {
            name: value[1:-1]
            if name in output_ports and value.startswith("{") and value.endswith("}")
            else self._resolve(value)
            for name, value in element.attrib.items()
        }

    def _cancel_before(self, node: str) -> bool:
        return any(
            item.get("at") == f"before:{node}" and item.get("fault") == "operator_cancelled"
            for item in self.scenario.faults
        )

    async def command(
        self,
        node: str,
        adapter_name: str,
        capability: str,
        payload: dict[str, Any],
    ) -> CommandResult:
        self.command_ordinal += 1
        command_id = str(
            uuid5(
                NAMESPACE_URL,
                f"cellforge:{self.scenario.seed}:{self.command_ordinal}:{node}:{capability}",
            )
        )
        adapter = self.adapters[adapter_name]
        component = adapter.scenario.component_instance_id
        specialized = (
            "process.command.requested"
            if capability.endswith("execute_cycle")
            else "device.command.requested"
        )
        self.emit(
            specialized,
            node=node,
            component=component,
            command_id=command_id,
            evidence={"capability": capability},
        )
        result = await adapter.execute(
            CapabilityCommand(
                command_id=command_id,
                trace_id=self.trace_id,
                capability=capability,
                input_payload_json=json.dumps(payload, sort_keys=True),
                timeout=timedelta(seconds=1),
            )
        )
        self.emit(
            result.result_code,
            node=node,
            component=component,
            command_id=command_id,
            result_code=result.result_code,
            outcome_certain=result.outcome_certain,
        )
        return result

    async def _leaf(self, element: ElementTree.Element) -> NodeStatus:
        node = element.tag
        ports = self._ports(element)
        if self._cancel_before(node):
            self.emit("operator.cancelled", node=node)
            return NodeStatus.CANCELLED
        self.emit("behavior_tree.node.entered", node=node)
        handler = getattr(self, f"node_{node}", None)
        if handler is None:
            raise ScenarioError(f"{self.tree_path}: unsupported pen node '{node}'")
        typed_handler = cast(Callable[[dict[str, Any]], Awaitable[NodeStatus]], handler)
        status = await typed_handler(ports)
        self.emit(
            "behavior_tree.node.completed",
            node=node,
            result_code=status.value,
            evidence={"status": status.value},
        )
        return status

    async def _execute_element(self, element: ElementTree.Element) -> NodeStatus:
        if element.tag == "Sequence":
            for child in element:
                status = await self._execute_element(child)
                if status is not NodeStatus.SUCCESS:
                    return status
            return NodeStatus.SUCCESS
        if element.tag == "RetryUntilSuccessful":
            if len(element) != 1:
                raise ScenarioError(f"{self.tree_path}: RetryUntilSuccessful needs one child")
            attempts_text = element.attrib.get("num_attempts", "")
            try:
                attempts = int(attempts_text)
            except ValueError as error:
                raise ScenarioError(
                    f"{self.tree_path}: invalid retry count '{attempts_text}'"
                ) from error
            if attempts < 1:
                raise ScenarioError(f"{self.tree_path}: retry count must be positive")
            for _ in range(attempts):
                status = await self._execute_element(element[0])
                if status is NodeStatus.SUCCESS:
                    return status
                if status in {
                    NodeStatus.CANCELLED,
                    NodeStatus.OUTCOME_UNKNOWN,
                    NodeStatus.REJECTED,
                }:
                    return status
            return NodeStatus.FAILURE
        return await self._leaf(element)

    async def node_ValidateFrozenJob(self, ports: dict[str, Any]) -> NodeStatus:
        required = (
            "job_id",
            "cell_id",
            "recipe_id",
            "recipe_version",
            "input_payload_json",
            "execution_mode",
        )
        if any(ports.get(name) in {None, ""} for name in required):
            self.emit("job.invalid_frozen_input", node="ValidateFrozenJob")
            return NodeStatus.REJECTED
        try:
            payload = json.loads(str(ports["input_payload_json"]))
        except json.JSONDecodeError:
            self.emit("job.invalid_frozen_input", node="ValidateFrozenJob")
            return NodeStatus.REJECTED
        if not isinstance(payload, dict) or not isinstance(payload.get("engraving_text"), str):
            self.emit("job.invalid_frozen_input", node="ValidateFrozenJob")
            return NodeStatus.REJECTED
        return NodeStatus.SUCCESS

    async def node_CheckSafetyHealthy(self, ports: dict[str, Any]) -> NodeStatus:
        if not bool(ports.get("healthy")):
            self.emit("safety.unhealthy", node="CheckSafetyHealthy")
            return NodeStatus.REJECTED
        return NodeStatus.SUCCESS

    async def node_CheckRequiredDevicesReady(self, ports: dict[str, Any]) -> NodeStatus:
        if not bool(ports.get("ready")):
            self.emit("devices.not_ready", node="CheckRequiredDevicesReady")
            return NodeStatus.REJECTED
        self.job_started = True
        self.emit("job.started", node="CheckRequiredDevicesReady")
        return NodeStatus.SUCCESS

    async def node_LocateProduct(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "LocateProduct",
            "locator",
            "vision.action.locate_object",
            {"object_type": ports["object_type"], "profile_id": ports["profile"]},
        )
        if result.success:
            output = json.loads(result.output_payload_json)
            self.blackboard["product_pose"] = output["estimates"][0]["pose"]
        return NodeStatus.SUCCESS if result.success else NodeStatus.FAILURE

    async def node_PickProduct(self, ports: dict[str, Any]) -> NodeStatus:
        if not isinstance(ports.get("pose"), dict):
            return NodeStatus.FAILURE
        result = await self.command("PickProduct", "gripper", "gripper.action.close", {})
        return NodeStatus.SUCCESS if result.success else NodeStatus.FAILURE

    async def node_LoadFixture(self, ports: dict[str, Any]) -> NodeStatus:
        motion = await self.command(
            "LoadFixture",
            "robot",
            "robot_motion.action.execute_trajectory",
            {"trajectory": {"waypoints": [{"pose": str(ports["fixture"])}]}},
        )
        if not motion.success:
            return NodeStatus.FAILURE
        clamp = await self.command("LoadFixture", "fixture", "fixture.action.clamp", {})
        return NodeStatus.SUCCESS if clamp.success else NodeStatus.FAILURE

    async def node_VerifyFixture(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command("VerifyFixture", "fixture", "fixture.action.verify_seated", {})
        return NodeStatus.SUCCESS if result.success else NodeStatus.FAILURE

    async def node_MoveRobotToProcessSafePose(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "MoveRobotToProcessSafePose",
            "robot",
            "robot_motion.action.execute_trajectory",
            {"trajectory": {"waypoints": [{"pose": str(ports["pose"])}]}},
        )
        return NodeStatus.SUCCESS if result.success else NodeStatus.FAILURE

    async def node_SelectProcessProgram(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "SelectProcessProgram",
            "process",
            "process.action.select_program",
            {"program_id": ports["program"], "variable_data": json.loads(ports["variable_data"])},
        )
        return NodeStatus.SUCCESS if result.success else NodeStatus.FAILURE

    async def node_ExecuteProcess(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "ExecuteProcess",
            "process",
            "process.action.execute_cycle",
            {
                "program_id": ports["program"],
                "variable_data": json.loads(ports["variable_data"]),
                "recipe_id": ports["recipe_id"],
                "recipe_version": int(ports["recipe_version"]),
            },
        )
        if not result.outcome_certain:
            return NodeStatus.OUTCOME_UNKNOWN
        if result.success:
            self.emit("process.command.completed", node="ExecuteProcess")
            return NodeStatus.SUCCESS
        return NodeStatus.FAILURE

    async def node_InspectProduct(self, ports: dict[str, Any]) -> NodeStatus:
        result = await self.command(
            "InspectProduct",
            "inspection",
            "vision.action.inspect_object",
            {"inspection_profile": ports["profile"], "expected": json.loads(ports["expected"])},
        )
        if not result.success:
            return NodeStatus.FAILURE
        output = json.loads(result.output_payload_json)
        self.blackboard["inspection"] = output
        accepted = bool(output.get("accepted"))
        self.emit(
            "inspection.accepted" if accepted else "inspection.rejected", node="InspectProduct"
        )
        return NodeStatus.SUCCESS if accepted else NodeStatus.FAILURE

    async def node_UnloadProduct(self, ports: dict[str, Any]) -> NodeStatus:
        release = await self.command("UnloadProduct", "fixture", "fixture.action.release", {})
        if not release.success:
            return NodeStatus.FAILURE
        opened = await self.command("UnloadProduct", "gripper", "gripper.action.open", {})
        return NodeStatus.SUCCESS if opened.success else NodeStatus.FAILURE

    async def node_RouteByInspection(self, ports: dict[str, Any]) -> NodeStatus:
        inspection = ports.get("inspection")
        return (
            NodeStatus.SUCCESS
            if isinstance(inspection, dict) and inspection.get("accepted")
            else NodeStatus.FAILURE
        )

    async def node_RecordProductionResult(self, ports: dict[str, Any]) -> NodeStatus:
        self.emit("production.result.recorded", node="RecordProductionResult")
        return NodeStatus.SUCCESS

    async def execute(self) -> ScenarioResult:
        self.emit("job.accepted", evidence={"trace_id": self.trace_id, "seed": self.scenario.seed})
        try:
            status = await asyncio.wait_for(
                self._execute_element(self._tree_root), timeout=self.scenario.timeout_seconds
            )
        except TimeoutError:
            status = NodeStatus.FAILURE
            self.emit("scenario.timeout")

        if status is NodeStatus.SUCCESS:
            final_status = "SUCCESS"
            self.emit("job.completed")
        elif status is NodeStatus.CANCELLED:
            final_status = "CANCELLED"
            self.emit("job.cancelled")
        elif status is NodeStatus.OUTCOME_UNKNOWN:
            final_status = "OUTCOME_UNKNOWN"
            self.emit("job.outcome_unknown", outcome_certain=False)
        elif status is NodeStatus.REJECTED:
            final_status = "REJECTED"
            self.emit("job.rejected")
        else:
            final_status = "RECOVERABLE_FAULT"
            self.emit("job.failed")

        event_types = [event.event_type for event in self.events]
        failures: list[str] = []
        if final_status != self.scenario.expected_status:
            failures.append(
                f"expected final status {self.scenario.expected_status}, got {final_status}"
            )
        for required in self.scenario.required_events:
            if required not in event_types:
                failures.append(f"required event missing: {required}")
        for forbidden in self.scenario.forbidden_events:
            if forbidden in event_types:
                failures.append(f"forbidden event present: {forbidden}")
        return ScenarioResult(
            scenario_id=self.scenario.scenario_id,
            name=self.scenario.name,
            seed=self.scenario.seed,
            final_status=final_status,
            passed=not failures,
            failures=tuple(failures),
            trace=tuple(self.events),
        )


async def run_scenario(scenario: ScenarioDefinition, tree_path: Path) -> ScenarioResult:
    return await PenHeadlessExecutor(scenario, tree_path).execute()


async def run_suite(scenario_root: Path, tree_path: Path) -> tuple[ScenarioResult, ...]:
    results = []
    for scenario in load_scenarios(scenario_root):
        results.append(await run_scenario(scenario, tree_path))
    return tuple(results)


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )


def write_reports(results: tuple[ScenarioResult, ...], reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "passed": all(result.passed for result in results),
        "scenario_count": len(results),
        "results": [result.as_json() for result in results],
    }
    (reports_dir / "pen-headless-report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    failures = sum(not result.passed for result in results)
    cases = []
    for result in results:
        failure = ""
        if result.failures:
            message = "; ".join(result.failures)
            failure = f'<failure message="{_xml_escape(message)}"/>'
        cases.append(
            '  <testcase classname="cellforge.pen_headless" '
            f'name="{_xml_escape(result.scenario_id)}">{failure}</testcase>'
        )
    junit = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="pen-headless" tests="{len(results)}" failures="{failures}">\n'
        + "\n".join(cases)
        + "\n</testsuite>\n"
    )
    (reports_dir / "pen-headless-junit.xml").write_text(junit, encoding="utf-8")


def verify_or_write_golden(
    results: tuple[ScenarioResult, ...], golden_root: Path, *, write: bool
) -> tuple[str, ...]:
    failures: list[str] = []
    if write:
        golden_root.mkdir(parents=True, exist_ok=True)
    for result in results:
        path = golden_root / f"{result.scenario_id}.json"
        rendered = json.dumps(result.normalized_trace(), indent=2, sort_keys=True) + "\n"
        if write:
            path.write_text(rendered, encoding="utf-8")
        elif not path.is_file():
            failures.append(f"missing golden trace: {path}")
        elif path.read_text(encoding="utf-8") != rendered:
            failures.append(f"golden trace mismatch: {path}")
    return tuple(failures)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--golden-root", type=Path, required=True)
    parser.add_argument("--write-golden", action="store_true")
    parser.add_argument("--seed", type=int, help="Run only the scenario with this replay seed.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenarios = load_scenarios(args.scenario_root)
    if args.seed is not None:
        scenarios = tuple(item for item in scenarios if item.seed == args.seed)
        if not scenarios:
            raise ScenarioError(f"no scenario has seed {args.seed}")
        results = tuple(asyncio.run(run_scenario(item, args.tree)) for item in scenarios)
    else:
        results = asyncio.run(run_suite(args.scenario_root, args.tree))
    write_reports(results, args.reports_dir)
    golden_failures = verify_or_write_golden(results, args.golden_root, write=args.write_golden)
    for result in results:
        state = "PASS" if result.passed else "FAIL"
        print(f"{state} {result.scenario_id} seed={result.seed} status={result.final_status}")
        for failure in result.failures:
            print(f"  {failure}")
    for failure in golden_failures:
        print(f"FAIL {failure}")
    return 0 if all(result.passed for result in results) and not golden_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
