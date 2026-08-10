from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).parents[1]
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def load_workflow() -> dict[str, Any]:
    loaded = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))

    assert isinstance(loaded, dict)
    return loaded


def test_ci_workflow_is_valid_yaml_with_required_jobs() -> None:
    workflow = load_workflow()

    assert workflow["on"]
    assert set(workflow["jobs"]) == {"python", "ros-jazzy"}


def test_ci_targets_supported_platforms_without_isaac_sim() -> None:
    workflow = load_workflow()
    serialized = CI_WORKFLOW.read_text(encoding="utf-8").lower()

    assert workflow["jobs"]["python"]["runs-on"] == "ubuntu-24.04"
    assert workflow["jobs"]["ros-jazzy"]["runs-on"] == "ubuntu-24.04"
    assert "jazzy" in serialized
    assert "isaac" not in serialized


def test_ci_runs_schema_and_example_validation() -> None:
    workflow = load_workflow()
    python_steps = workflow["jobs"]["python"]["steps"]

    assert any(step.get("run") == "make validate-examples" for step in python_steps)
    assert any(step.get("run") == "make studio-simulation-check" for step in python_steps)
