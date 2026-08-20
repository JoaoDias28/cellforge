"""Run the reproducible CellForge L0 demo or the supported Isaac Sim 6 L2 probe.

The L0 path delegates execution to the existing Task 013 headless runner. The L2 path launches
the existing Task 027 Kit probe and accepts its result only when the report proves Isaac Sim 6,
CUDA, and actual PhysX execution. This script is an engineering demo wrapper; it never selects a
commissioning or production mode and never implements a functional-safety function.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import yaml

SCHEMA_VERSION = "0.1.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = REPOSITORY_ROOT / "examples" / "pen_engraving"
DEFAULT_ISAAC_SIM_ROOT = Path(os.environ.get("ISAAC_SIM_ROOT", "C:\\isaacsim"))
TASK027_PROBE = REPOSITORY_ROOT / "scripts" / "verify_kit_l2_runtime.py"
SAFETY_BOUNDARY = (
    "Simulation evidence is engineering verification only. Functional safety remains independently "
    "enforced and validated by rated hardware outside CellForge."
)
COMMON_LIMITATIONS = {
    "interface_evidence": (
        "The canonical task contract, adapter sequencing, assertions, and trace were exercised."
    ),
    "physics_evidence": (
        "No geometry, kinematics, contact, or physics was exercised by this backend."
    ),
    "process_quality_evidence": (
        "Laser readiness, handshake, beam/material interaction, and mark quality were not "
        "qualified."
    ),
    "hardware_evidence": "No physical robot, process machine, sensor, or I/O was used.",
    "safety_evidence": (
        "Modeled safety status is read-only evidence; no safety-rated function was implemented "
        "or validated."
    ),
}
L2_LIMITATIONS = {
    "interface_evidence": (
        "The Task 027 runtime/adapter probe exercised the modeled L2 command sequence and recorded "
        "adapter events."
    ),
    "physics_evidence": (
        "OpenUSD/PhysX execution was observed for the configured simplified pen cell and seeded "
        "fault cases."
    ),
    "process_quality_evidence": (
        "Laser timing/readiness/handshake only; beam/material interaction, optics, text fidelity, "
        "and mark quality are excluded."
    ),
    "hardware_evidence": (
        "Isaac Sim adapters are not physical device drivers and do not qualify real hardware."
    ),
    "safety_evidence": (
        "Modeled safety status is read-only evidence; independent rated hardware remains "
        "authoritative."
    ),
}
L2_UNAVAILABLE_LIMITATIONS = {
    **COMMON_LIMITATIONS,
    "interface_evidence": (
        "No passing L2 probe evidence was accepted; prerequisite or probe diagnostics are recorded "
        "for troubleshooting only."
    ),
    "physics_evidence": (
        "Isaac Sim 6/CUDA/PhysX prerequisites were unavailable or the Task 027 probe did not "
        "complete; no L2 claim was made."
    ),
}


class DemoError(RuntimeError):
    """A stable demo configuration or artifact error."""


def _json_bytes(value: Any, *, compact: bool = True) -> bytes:
    if compact:
        rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    else:
        rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    return rendered.encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as error:
        raise DemoError(f"cannot hash '{path}': {error}") from error


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value, compact=False))


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "<external>"


def _project_relative(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as error:
        raise DemoError(f"'{path}' is outside canonical project '{project}'") from error


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise DemoError(f"cannot load YAML '{path}': {error}") from error
    if not isinstance(value, dict):
        raise DemoError(f"'{path}' must contain an object")
    return value


def _git_revision(root: Path) -> str:
    try:
        completed = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={root.as_posix()}",
                "-C",
                str(root),
                "rev-parse",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    revision = completed.stdout.strip()
    return revision if revision else "unavailable"


def _ensure_simulation_import_paths(root: Path) -> None:
    for relative in (
        Path("ros_ws/src/cellforge_device_sdk"),
        Path("ros_ws/src/cellforge_mock_adapters"),
        Path("ros_ws/src/cellforge_simulation"),
    ):
        value = str((root / relative).resolve())
        if value not in sys.path:
            sys.path.insert(0, value)


def _load_l0_runner(root: Path) -> Any:
    _ensure_simulation_import_paths(root)
    try:
        from cellforge_mock_adapters.headless import (  # type: ignore[import-untyped]
            load_scenarios,
        )
    except ImportError as error:
        raise DemoError(
            "L0 dependencies are unavailable; run this command with the repository's locked "
            "Python environment"
        ) from error
    return load_scenarios


def _resolve_l0_scenario(project: Path, selector: str) -> tuple[Any, Path]:
    scenario_root = project / "scenarios"
    load_scenarios = _load_l0_runner(REPOSITORY_ROOT)
    scenarios = load_scenarios(scenario_root)
    for scenario in scenarios:
        if selector in {scenario.scenario_id, scenario.source.stem}:
            return scenario, scenario.source
    available = ", ".join(item.scenario_id for item in scenarios)
    raise DemoError(f"unknown L0 scenario '{selector}'; available scenarios: {available}")


def _canonical_inputs(
    project: Path,
    scenario_path: Path,
    *,
    adapter_config: str,
) -> dict[str, Any]:
    project = project.resolve()
    scenario_path = scenario_path.resolve()
    _ensure_simulation_import_paths(REPOSITORY_ROOT)
    try:
        from cellforge_simulation.models import load_canonical_project
    except ImportError as error:
        raise DemoError("the ROS-free simulation model package is unavailable") from error

    try:
        canonical = load_canonical_project(project, scenario_path)
    except ValueError as error:
        raise DemoError(f"canonical project validation failed: {error}") from error

    cell_path = project / "cell.yaml"
    cell_document = _load_yaml(cell_path)
    tasks = cell_document.get("tasks")
    if not isinstance(tasks, list):
        raise DemoError(f"{cell_path}.tasks must be a list")
    task = next(
        (item for item in tasks if isinstance(item, dict) and item.get("id") == "pen_engraving"),
        None,
    )
    if not isinstance(task, dict) or not isinstance(task.get("behavior_tree"), str):
        raise DemoError("canonical pen_engraving behavior tree is not declared")
    tree_path = (project / task["behavior_tree"]).resolve()

    recipes = cell_document.get("recipes")
    if not isinstance(recipes, list) or not recipes or not isinstance(recipes[0], dict):
        raise DemoError("canonical pen recipe is not declared")
    recipe_relative = recipes[0].get("path")
    if not isinstance(recipe_relative, str):
        raise DemoError("canonical pen recipe path is invalid")
    recipe_path = (project / recipe_relative).resolve()
    recipe_document = _load_yaml(recipe_path)
    recipe_identity = recipe_document.get("recipe")
    if not isinstance(recipe_identity, dict):
        raise DemoError(f"{recipe_path}.recipe must be an object")

    adapter_path = (project / adapter_config).resolve()
    selected_paths = [cell_path, Path(canonical.scene_path), tree_path, recipe_path, scenario_path]
    if adapter_path.is_file():
        selected_paths.append(adapter_path)
    manifest: list[dict[str, str]] = []
    seen: set[Path] = set()
    for path in selected_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.is_file():
            raise DemoError(f"canonical input is missing: {resolved}")
        manifest.append(
            {
                "path": _project_relative(resolved, project),
                "sha256": _sha256_path(resolved),
            }
        )
    manifest.sort(key=lambda item: item["path"])
    by_path = {item["path"]: item["sha256"] for item in manifest}
    scenario_relative = _project_relative(scenario_path, project)
    scene_relative = _project_relative(Path(canonical.scene_path), project)
    tree_relative = _project_relative(tree_path, project)
    recipe_relative = _project_relative(recipe_path, project)
    adapter_relative = _project_relative(adapter_path, project) if adapter_path.is_file() else None
    project_root_label = _repo_relative(project, REPOSITORY_ROOT)
    return {
        "project_root": project_root_label,
        "cell_id": canonical.cell_id,
        "cell_yaml": {"path": "cell.yaml", "sha256": by_path["cell.yaml"]},
        "scene": {"path": scene_relative, "sha256": by_path[scene_relative]},
        "behavior_tree": {"path": tree_relative, "sha256": by_path[tree_relative]},
        "recipe": {"path": recipe_relative, "sha256": by_path[recipe_relative]},
        "adapter_configuration": (
            {"path": adapter_relative, "sha256": by_path[adapter_relative]}
            if adapter_relative is not None
            else None
        ),
        "scenario": {"path": scenario_relative, "sha256": by_path[scenario_relative]},
        "project_sha256": _sha256_bytes(_json_bytes(manifest)),
        "input_manifest": manifest,
        "recipe_identity": {
            "id": recipe_identity.get("id"),
            "version": recipe_identity.get("version"),
        },
        "cell_path": cell_path,
        "scene_path": Path(canonical.scene_path),
        "tree_path": tree_path,
        "recipe_path": recipe_path,
        "scenario_path": scenario_path,
    }


def _source_identity(root: Path) -> dict[str, str]:
    runner_path = Path(__file__).resolve()
    return {
        "revision": _git_revision(root),
        "runner": _repo_relative(runner_path, root),
        "runner_sha256": _sha256_path(runner_path),
    }


def _l0_adapters(executor: Any) -> list[dict[str, Any]]:
    adapters: list[dict[str, Any]] = []
    for role, adapter in sorted(executor.adapters.items()):
        scenario = adapter.scenario
        device_kind = getattr(scenario.device_kind, "value", str(scenario.device_kind))
        adapters.append(
            {
                "role": role,
                "component_instance_id": scenario.component_instance_id,
                "adapter_package": "cellforge_mock_adapters",
                "entrypoint": "cellforge_mock_adapters.headless.PenHeadlessExecutor",
                "device_kind": device_kind,
                "fidelity": "L0",
                "capabilities": sorted(scenario.operations),
            }
        )
    return adapters


def _l2_adapters() -> list[dict[str, Any]]:
    capabilities = {
        "robot-001": ["robot_motion.action.execute_trajectory"],
        "gripper-001": ["gripper.action.close", "gripper.action.open"],
        "fixture-001": [
            "fixture.action.clamp",
            "fixture.action.release",
            "fixture.action.verify_seated",
        ],
        "laser-001": [
            "process.action.execute_cycle",
            "process.action.select_program",
        ],
        "camera-001": ["vision.action.inspect_object", "vision.action.locate_object"],
        "safety-status-001": ["safety.status.read_only"],
    }
    return [
        {
            "component_instance_id": component,
            "adapter_package": "cellforge_simulation",
            "entrypoint": "cellforge_simulation.l2_runtime.IsaacL2Runtime",
            "fidelity": "L2",
            "capabilities": values,
            "safety_claim": "none" if component == "safety-status-001" else None,
        }
        for component, values in sorted(capabilities.items())
    ]


def _evaluate_l0_assertions(
    result: Any,
    scenario: Any,
    expressions: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    trace = result.normalized_trace()
    event_types = [str(event["event_type"]) for event in trace]
    assertions: list[dict[str, Any]] = [
        {
            "id": "source.final_status",
            "kind": "final_status",
            "expected": scenario.expected_status,
            "actual": result.final_status,
            "passed": result.final_status == scenario.expected_status,
        }
    ]
    for index, event in enumerate(scenario.required_events, start=1):
        assertions.append(
            {
                "id": f"source.required_event.{index}",
                "kind": "required_event",
                "expected": event,
                "actual": event in event_types,
                "passed": event in event_types,
            }
        )
    for index, event in enumerate(scenario.forbidden_events, start=1):
        assertions.append(
            {
                "id": f"source.forbidden_event.{index}",
                "kind": "forbidden_event",
                "expected": event,
                "actual": event in event_types,
                "passed": event not in event_types,
            }
        )

    failures: list[str] = list(result.failures)
    for index, expression in enumerate(expressions, start=1):
        if "=" in expression:
            kind, expected = expression.split("=", 1)
        elif ":" in expression:
            kind, expected = expression.split(":", 1)
        else:
            raise DemoError(
                f"invalid assertion '{expression}'; use require-event:<event>, "
                "forbid-event:<event>, or final-status:<status>"
            )
        kind = kind.strip().lower()
        expected = expected.strip()
        if not expected or kind not in {"require-event", "forbid-event", "final-status"}:
            raise DemoError(
                f"invalid assertion '{expression}'; use require-event:<event>, "
                "forbid-event:<event>, or final-status:<status>"
            )
        if kind == "require-event":
            passed = expected in event_types
            actual: Any = expected in event_types
        elif kind == "forbid-event":
            passed = expected not in event_types
            actual = expected in event_types
        else:
            passed = result.final_status == expected
            actual = result.final_status
        assertion = {
            "id": f"cli.{index}",
            "kind": kind,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "expression": expression,
        }
        assertions.append(assertion)
        if not passed:
            failures.append(f"assertion failed: {expression}")
    return assertions, failures


def _common_fields(
    *,
    backend: str,
    requested_fidelity: str,
    achieved_fidelity: str | None,
    actual_physx_executed: bool,
    source: dict[str, str],
    inputs: dict[str, Any],
    scenario: dict[str, Any],
    selected_adapters: list[dict[str, Any]],
    limitations: dict[str, str],
    artifacts: dict[str, str],
    trace: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    result: dict[str, Any],
    replay_command: str,
    logs: dict[str, str],
) -> dict[str, Any]:
    evidence_inputs = {
        "backend": backend,
        "requested_fidelity": requested_fidelity,
        "achieved_fidelity": achieved_fidelity,
        "actual_physx_executed": actual_physx_executed,
        "source": source,
        "project": {
            key: value
            for key, value in inputs.items()
            if key
            in {
                "project_root",
                "cell_id",
                "cell_yaml",
                "scene",
                "behavior_tree",
                "recipe",
                "adapter_configuration",
                "project_sha256",
            }
        },
        "scenario": scenario,
        "selected_adapters": selected_adapters,
        "assertions": assertions,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "cellforge.simulation_demo_evidence",
        "status": "passed" if result["passed"] else "failed",
        "backend": backend,
        "execution": {
            "mode": "simulation",
            "physical_operation_authorized": False,
            "commissioning_or_production_supported": False,
        },
        "source": source,
        "project": {
            key: value
            for key, value in inputs.items()
            if key
            in {
                "project_root",
                "cell_id",
                "cell_yaml",
                "scene",
                "behavior_tree",
                "recipe",
                "adapter_configuration",
                "project_sha256",
            }
        },
        "scenario": scenario,
        "selected_adapters": selected_adapters,
        "fidelity": {
            "requested": requested_fidelity,
            "achieved": achieved_fidelity,
            "actual_physx_executed": actual_physx_executed,
        },
        "assertions": {
            "passed": all(bool(item["passed"]) for item in assertions),
            "results": assertions,
        },
        "result": result,
        "artifacts": artifacts,
        "logs": logs,
        "trace": {
            "path": artifacts["trace"],
            "event_count": len(trace),
            "normalized_sha256": _sha256_bytes(_json_bytes(trace)),
        },
        "evidence_inputs_sha256": _sha256_bytes(_json_bytes(evidence_inputs)),
        "limitations": limitations,
        "safety_boundary": SAFETY_BOUNDARY,
        "replay": {"command": replay_command, "normalized_inputs": artifacts["trace"]},
    }


def _write_junit(path: Path, assertions: list[dict[str, Any]]) -> None:
    cases: list[str] = []
    failures = 0
    for assertion in assertions:
        failure = ""
        if not assertion["passed"]:
            failures += 1
            message = f"expected {assertion['expected']!r}, actual {assertion['actual']!r}"
            failure = f'<failure message="{xml_escape(message)}" />'
        cases.append(
            f'  <testcase classname="cellforge.simulation_demo" '
            f'name="{xml_escape(str(assertion["id"]))}">{failure}</testcase>'
        )
    rendered = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="cellforge-simulation-demo" tests="{len(assertions)}" '
        f'failures="{failures}">\n' + "\n".join(cases) + "\n</testsuite>\n"
    )
    _write_text(path, rendered)


def _write_common_artifacts(
    output: Path,
    report: dict[str, Any],
    trace: list[dict[str, Any]],
    *,
    run_log: str,
    replay_text: str,
    junit_assertions: list[dict[str, Any]],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "trace.json", trace)
    _write_json(output / "events.json", trace)
    _write_json(output / "report.json", report)
    _write_junit(output / "junit.xml", junit_assertions)
    _write_text(output / "run.log", run_log)
    _write_text(output / "replay.txt", replay_text)


def _l0_output(repo: Path, seed: int, requested: Path | None) -> Path:
    if requested is not None:
        return requested.resolve()
    return repo / ".artifacts" / "simulation-demo" / "l0" / f"seed-{seed}"


def _run_l0(args: argparse.Namespace) -> int:
    project = Path(args.project_root).resolve()
    scenario, scenario_path = _resolve_l0_scenario(project, args.scenario)
    source_seed = scenario.seed
    seed = source_seed if args.seed is None else args.seed
    if seed < 0:
        raise DemoError("--seed must be non-negative")
    if args.seed is not None:
        scenario = replace(scenario, seed=seed)
    inputs = _canonical_inputs(project, scenario_path, adapter_config="runtime/l0-adapters.json")
    recipe_identity = inputs["recipe_identity"]
    if recipe_identity != {
        "id": scenario.job.get("recipe_id"),
        "version": scenario.job.get("recipe_version"),
    }:
        raise DemoError("scenario job does not reference the canonical recipe identity")
    _ensure_simulation_import_paths(REPOSITORY_ROOT)
    from cellforge_mock_adapters.headless import PenHeadlessExecutor

    async def execute() -> tuple[Any, Any]:
        executor = PenHeadlessExecutor(scenario, inputs["tree_path"])
        return await executor.execute(), executor

    result, executor = asyncio.run(execute())
    trace = result.normalized_trace()
    assertions, failures = _evaluate_l0_assertions(result, scenario, args.assertion)
    passed = not failures
    selected = _l0_adapters(executor)
    source = _source_identity(REPOSITORY_ROOT)
    scenario_identity = {
        "id": scenario.scenario_id,
        "name": scenario.name,
        "source": inputs["scenario"]["path"],
        "source_sha256": inputs["scenario"]["sha256"],
        "source_seed": source_seed,
        "seed": seed,
    }
    artifacts = {
        "report": "report.json",
        "trace": "trace.json",
        "events": "events.json",
        "junit": "junit.xml",
        "run_log": "run.log",
        "replay": "replay.txt",
    }
    replay = (
        "uv run --frozen python scripts/run_simulation_demo.py --backend l0 "
        f"--scenario {scenario_path.stem} --seed {seed}"
    )
    result_document = {
        "passed": passed,
        "final_status": result.final_status,
        "failures": failures,
        "source_runner_passed": result.passed,
    }
    report = _common_fields(
        backend="l0-contract-mock",
        requested_fidelity="L0",
        achieved_fidelity="L0",
        actual_physx_executed=False,
        source=source,
        inputs=inputs,
        scenario=scenario_identity,
        selected_adapters=selected,
        limitations=COMMON_LIMITATIONS,
        artifacts=artifacts,
        trace=trace,
        assertions=assertions,
        result=result_document,
        replay_command=replay,
        logs={"run": "run.log"},
    )
    output = _l0_output(REPOSITORY_ROOT, seed, args.output_dir)
    run_log = (
        "\n".join(
            (
                "backend=l0-contract-mock",
                f"scenario={scenario.scenario_id}",
                f"seed={seed}",
                f"final_status={result.final_status}",
                f"assertions_passed={str(passed).lower()}",
                f"trace_events={len(trace)}",
            )
        )
        + "\n"
    )
    _write_common_artifacts(
        output,
        report,
        trace,
        run_log=run_log,
        replay_text=replay + "\n",
        junit_assertions=assertions,
    )
    print(
        f"{'PASS' if passed else 'FAIL'} L0 simulation demo: "
        f"scenario={scenario.scenario_id} seed={seed} report={output / 'report.json'}"
    )
    return 0 if passed else 1


def _nvidia_gpu_name() -> tuple[str | None, str | None]:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"nvidia-smi unavailable: {error}"
    name = next((line.strip() for line in completed.stdout.splitlines() if line.strip()), None)
    if completed.returncode != 0 or name is None:
        detail = completed.stderr.strip() or f"exit code {completed.returncode}"
        return None, f"nvidia-smi did not report a GPU: {detail}"
    return name, None


def _isaac_preflight(root: Path) -> dict[str, Any]:
    version_path = root / "VERSION"
    kit_path = root / "kit" / ("kit.exe" if sys.platform == "win32" else "kit")
    app_path = root / "apps" / "isaacsim.exp.base.python.kit"
    failures: list[str] = []
    version = "unavailable"
    if not version_path.is_file():
        failures.append(f"missing Isaac version file: {version_path.name}")
    else:
        try:
            version = version_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            failures.append(f"cannot read Isaac version: {error}")
        if not version:
            failures.append("Isaac version file is empty")
        elif not version.startswith("6."):
            failures.append(f"Isaac Sim 6 required; found {version!r}")
    if not kit_path.is_file():
        failures.append(f"missing Kit executable: {kit_path.name}")
    if not app_path.is_file():
        failures.append("missing Isaac Sim base Kit application")
    gpu_name, gpu_failure = _nvidia_gpu_name()
    if gpu_failure is not None:
        failures.append(gpu_failure)
    return {
        "isaac_version": version,
        "gpu_name": gpu_name,
        "failures": failures,
        "kit_path": kit_path,
        "app_path": app_path,
    }


def _l2_trace(raw: dict[str, Any]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    runs = raw.get("runs", [])
    if not isinstance(runs, list):
        return trace
    for run in runs:
        if not isinstance(run, dict):
            continue
        events = run.get("events", [])
        if isinstance(events, list):
            trace.extend(item for item in events if isinstance(item, dict))
    return trace


def _l2_assertions(
    raw: dict[str, Any], preflight: dict[str, Any], probe_exit_code: int
) -> list[dict[str, Any]]:
    version = str(raw.get("isaac_version", preflight["isaac_version"]))
    gpu_value = raw.get("gpu")
    gpu: dict[str, Any] = gpu_value if isinstance(gpu_value, dict) else {}
    summary_value = raw.get("summary")
    summary: dict[str, Any] = summary_value if isinstance(summary_value, dict) else {}
    actual_physx = raw.get("actual_physx_executed") is True
    return [
        {
            "id": "l2.probe.exit_code",
            "kind": "probe_exit_code",
            "expected": 0,
            "actual": probe_exit_code,
            "passed": probe_exit_code == 0,
        },
        {
            "id": "l2.isaac_version",
            "kind": "isaac_version",
            "expected": "6.x",
            "actual": version,
            "passed": version.startswith("6."),
        },
        {
            "id": "l2.cuda_gpu",
            "kind": "cuda_gpu",
            "expected": True,
            "actual": bool(gpu.get("is_cuda")) and bool(preflight.get("gpu_name")),
            "passed": bool(gpu.get("is_cuda")) and bool(preflight.get("gpu_name")),
        },
        {
            "id": "l2.actual_physx_executed",
            "kind": "actual_physx_executed",
            "expected": True,
            "actual": actual_physx,
            "passed": actual_physx,
        },
        {
            "id": "l2.seed_summary",
            "kind": "seed_summary",
            "expected": {"passed": 100, "failed": 0},
            "actual": {"passed": summary.get("passed"), "failed": summary.get("failed")},
            "passed": summary.get("passed") == 100 and summary.get("failed") == 0,
        },
        {
            "id": "l2.event_origin",
            "kind": "event_origin",
            "expected": "runtime/adapters",
            "actual": raw.get("event_origin"),
            "passed": raw.get("event_origin") == "runtime/adapters",
        },
    ]


def _build_l2_report(
    *,
    inputs: dict[str, Any],
    source: dict[str, str],
    preflight: dict[str, Any],
    raw: dict[str, Any],
    probe_exit_code: int,
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    trace = _l2_trace(raw)
    assertions = _l2_assertions(raw, preflight, probe_exit_code)
    failures = [
        f"{item['id']}: expected {item['expected']!r}, actual {item['actual']!r}"
        for item in assertions
        if not item["passed"]
    ]
    passed = not failures
    actual_physx = raw.get("actual_physx_executed") is True
    scenario = {
        "id": "pen-physical-nominal",
        "name": "L2 nominal pen manipulation",
        "source": inputs["scenario"]["path"],
        "source_sha256": inputs["scenario"]["sha256"],
        "seed": raw.get("seed_range", {"first": 0, "count": 100}),
    }
    replay = "uv run --frozen python scripts/run_simulation_demo.py --backend l2"
    result = {
        "passed": passed,
        "final_status": "SUCCESS" if passed else ("FAILED" if raw else "UNAVAILABLE"),
        "failures": failures,
        "probe_exit_code": probe_exit_code,
    }
    logs = {
        "kit_stdout": "kit.stdout.log",
        "kit_stderr": "kit.stderr.log",
    }
    if "task027_report" in artifacts:
        logs["task027_report"] = artifacts["task027_report"]
    report = _common_fields(
        backend="isaac-sim-6-task027-probe",
        requested_fidelity="L2",
        achieved_fidelity="L2" if passed else None,
        actual_physx_executed=actual_physx,
        source=source,
        inputs=inputs,
        scenario=scenario,
        selected_adapters=_l2_adapters(),
        limitations=L2_LIMITATIONS if passed else L2_UNAVAILABLE_LIMITATIONS,
        artifacts=artifacts,
        trace=trace,
        assertions=assertions,
        result=result,
        replay_command=replay,
        logs=logs,
    )
    if not raw and probe_exit_code == 127:
        report["status"] = "unavailable"
    report["isaac"] = {
        "version": raw.get("isaac_version", preflight["isaac_version"]),
        "gpu": raw.get("gpu", {"name": preflight.get("gpu_name"), "is_cuda": False}),
        "preflight_failures": preflight["failures"],
        "event_origin": raw.get("event_origin"),
    }
    return report, trace, assertions


def _l2_output(repo: Path, requested: Path | None) -> Path:
    if requested is not None:
        return requested.resolve()
    return repo / ".artifacts" / "simulation-demo" / "l2"


def _run_l2(args: argparse.Namespace) -> int:
    project = Path(args.project_root).resolve()
    scenario_path = (project / "physical" / "scenarios" / "nominal.yaml").resolve()
    output = _l2_output(REPOSITORY_ROOT, args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_text(output / "kit.stdout.log", "probe not started\n")
    _write_text(output / "kit.stderr.log", "probe not started\n")
    task027_report = output / "task027-report.json"
    try:
        task027_report.unlink(missing_ok=True)
    except OSError as error:
        raise DemoError(
            f"cannot clear stale Task 027 report '{task027_report}': {error}"
        ) from error
    inputs = _canonical_inputs(project, scenario_path, adapter_config="runtime/l2-adapters.json")
    source = _source_identity(REPOSITORY_ROOT)
    preflight = _isaac_preflight(Path(args.isaac_sim_root).resolve())
    artifacts = {
        "report": "report.json",
        "trace": "trace.json",
        "events": "events.json",
        "junit": "junit.xml",
        "run_log": "run.log",
        "replay": "replay.txt",
        "task027_report": "task027-report.json",
    }
    if preflight["failures"]:
        raw: dict[str, Any] = {}
        unavailable_artifacts = {
            key: value for key, value in artifacts.items() if key != "task027_report"
        }
        report, trace, assertions = _build_l2_report(
            inputs=inputs,
            source=source,
            preflight=preflight,
            raw=raw,
            probe_exit_code=127,
            artifacts=unavailable_artifacts,
        )
        _write_common_artifacts(
            output,
            report,
            trace,
            run_log="\n".join(["status=unavailable", *preflight["failures"]]) + "\n",
            replay_text="uv run --frozen python scripts/run_simulation_demo.py --backend l2\n",
            junit_assertions=assertions,
        )
        print(
            "UNAVAILABLE L2 simulation demo: "
            f"{'; '.join(preflight['failures'])}. Report: {output / 'report.json'}",
            file=sys.stderr,
        )
        return 1

    environment = os.environ.copy()
    environment["ISAAC_SIM_ROOT"] = str(Path(args.isaac_sim_root).resolve())
    environment["CELLFORGE_L2_REPORT"] = str(task027_report)
    try:
        with (
            (output / "kit.stdout.log").open("w", encoding="utf-8", newline="\n") as stdout,
            (output / "kit.stderr.log").open("w", encoding="utf-8", newline="\n") as stderr,
        ):
            completed = subprocess.run(
                [
                    str(preflight["kit_path"]),
                    str(preflight["app_path"]),
                    "--no-window",
                    "--exec",
                    str(TASK027_PROBE),
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                check=False,
                timeout=args.timeout_seconds,
            )
    except (OSError, subprocess.SubprocessError) as error:
        completed = None
        _write_text(output / "kit.stderr.log", f"probe launch failed: {error}\n")
    probe_exit_code = 1 if completed is None else int(completed.returncode)
    raw = {}
    if task027_report.is_file():
        try:
            loaded = json.loads(task027_report.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            _write_text(output / "run.log", f"status=failed\ninvalid Task 027 report: {error}\n")
        else:
            if isinstance(loaded, dict):
                raw = loaded
            else:
                _write_text(output / "run.log", "status=failed\nTask 027 report is not an object\n")
    report, trace, assertions = _build_l2_report(
        inputs=inputs,
        source=source,
        preflight=preflight,
        raw=raw,
        probe_exit_code=probe_exit_code,
        artifacts=artifacts,
    )
    failures = report["result"]["failures"]
    run_log = (
        "\n".join(
            [
                f"status={'passed' if report['result']['passed'] else 'failed'}",
                f"probe_exit_code={probe_exit_code}",
                f"actual_physx_executed={str(report['fidelity']['actual_physx_executed']).lower()}",
                *failures,
            ]
        )
        + "\n"
    )
    _write_common_artifacts(
        output,
        report,
        trace,
        run_log=run_log,
        replay_text="uv run --frozen python scripts/run_simulation_demo.py --backend l2\n",
        junit_assertions=assertions,
    )
    if report["result"]["passed"]:
        print(
            "PASS L2 simulation demo: actual PhysX execution verified. "
            f"Report: {output / 'report.json'}"
        )
        return 0
    print(
        "FAIL L2 simulation demo: Task 027 did not prove the required result. "
        f"Report: {output / 'report.json'}",
        file=sys.stderr,
    )
    return 1


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a non-negative integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return parsed


def _positive_int(value: str) -> int:
    parsed = _nonnegative_int(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("l0", "l2"), default="l0")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--scenario", default="nominal", help="L0 scenario ID or filename stem")
    parser.add_argument("--seed", type=_nonnegative_int, help="L0 deterministic replay seed")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--assertion",
        action="append",
        default=[],
        help="L0 overlay: require-event:<event>, forbid-event:<event>, or final-status:<status>",
    )
    parser.add_argument("--isaac-sim-root", type=Path, default=DEFAULT_ISAAC_SIM_ROOT)
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=900,
        help="L2 Kit probe timeout (default: 900 seconds)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run_l0(args) if args.backend == "l0" else _run_l2(args)
    except DemoError as error:
        print(f"ERROR simulation demo: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
