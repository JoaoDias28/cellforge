"""Static Task 022 local operator API integration contract check."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    package = root / "ros_ws/src/cellforge_operator_api/cellforge_operator_api"
    required = {"__init__.py", "api.py", "core.py", "main.py", "runtime.py", "ui.py"}
    if {path.name for path in package.glob("*.py")} != required:
        print("operator API module inventory does not match Task 022", file=sys.stderr)
        return 1
    runtime = (package / "runtime.py").read_text(encoding="utf-8")
    fixed_contracts = {
        'RUN_JOB_ACTION = "/cell/run_job"',
        'CELL_STATE_TOPIC = "/cell/state"',
        'JOB_EVENT_TOPIC = "/events/job"',
        'OPERATOR_ACTION_SERVICE = "/cell/operator_action"',
    }
    if not fixed_contracts <= set(line.strip() for line in runtime.splitlines()):
        print("operator ROS bridge fixed endpoint contract is incomplete", file=sys.stderr)
        return 1
    service = root / "ros_interfaces/srv/RequestOperatorAction.srv"
    packaged_service = root / "ros_ws/src/cellforge_interfaces/srv/RequestOperatorAction.srv"
    if service.read_bytes() != packaged_service.read_bytes():
        print("operator-action service source/package definitions drifted", file=sys.stderr)
        return 1
    schema_path = root / "examples/pen_engraving/operator/config.schema.json"
    example_path = root / "examples/pen_engraving/operator/operator-recovery.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    example = json.loads(example_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(example), key=lambda error: list(error.path)
    )
    if errors:
        print(f"operator recovery example is invalid: {errors[0].message}", file=sys.stderr)
        return 1
    forbidden = {"service", "service_name", "topic", "action_name", "command", "executable"}
    if any(forbidden.intersection(action) for action in example["actions"]):
        print("operator recovery example contains dynamic control fields", file=sys.stderr)
        return 1
    print("Task 022 local operator API integration contract verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
