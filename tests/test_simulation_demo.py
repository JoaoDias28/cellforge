from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "ros_ws" / "src" / "cellforge_device_sdk",
    ROOT / "ros_ws" / "src" / "cellforge_mock_adapters",
    ROOT / "ros_ws" / "src" / "cellforge_simulation",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def _load_demo_module() -> Any:
    path = ROOT / "scripts" / "run_simulation_demo.py"
    spec = importlib.util.spec_from_file_location("cellforge_simulation_demo", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


demo = _load_demo_module()
ARTIFACT_NAMES = ("report.json", "trace.json", "events.json", "junit.xml", "run.log", "replay.txt")


def _run_l0(output: Path, seed: int, *extra: str) -> int:
    return int(
        demo.main(
            [
                "--backend",
                "l0",
                "--scenario",
                "nominal",
                "--seed",
                str(seed),
                "--output-dir",
                str(output),
                *extra,
            ]
        )
    )


def _read_artifacts(output: Path) -> dict[str, bytes]:
    return {name: (output / name).read_bytes() for name in ARTIFACT_NAMES}


def test_l0_same_seed_reproduces_normalized_artifacts_byte_for_byte(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert _run_l0(first, 20260820) == 0
    assert _run_l0(second, 20260820) == 0

    assert _read_artifacts(first) == _read_artifacts(second)
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    assert report["backend"] == "l0-contract-mock"
    assert report["fidelity"] == {
        "requested": "L0",
        "achieved": "L0",
        "actual_physx_executed": False,
    }
    assert report["scenario"]["seed"] == 20260820
    assert report["project"]["project_sha256"]
    assert report["project"]["scene"]["sha256"]
    assert report["project"]["cell_yaml"]["sha256"]
    assert report["scenario"]["source_sha256"]
    assert len(report["source"]["revision"]) == 40
    assert report["execution"]["physical_operation_authorized"] is False
    assert report["execution"]["mode"] == "simulation"
    assert len(report["selected_adapters"]) == 6
    assert report["assertions"]["passed"] is True


def test_l0_failed_assertion_is_recorded_and_returns_non_zero(tmp_path: Path) -> None:
    output = tmp_path / "failed-assertion"

    assert _run_l0(output, 20260820, "--assertion", "require-event:demo.event.missing") == 1

    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["result"]["passed"] is False
    failed = [item for item in report["assertions"]["results"] if not item["passed"]]
    assert len(failed) == 1
    assert failed[0]["expression"] == "require-event:demo.event.missing"
    assert report["fidelity"]["achieved"] == "L0"
    assert report["execution"]["physical_operation_authorized"] is False


def test_l2_missing_runtime_writes_unavailable_report_and_returns_non_zero(
    tmp_path: Path,
) -> None:
    output = tmp_path / "l2-unavailable"
    missing_root = tmp_path / "not-an-isaac-install"

    exit_code = int(
        demo.main(
            [
                "--backend",
                "l2",
                "--isaac-sim-root",
                str(missing_root),
                "--output-dir",
                str(output),
            ]
        )
    )

    assert exit_code == 1
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "unavailable"
    assert report["result"]["final_status"] == "UNAVAILABLE"
    assert report["result"]["passed"] is False
    assert report["fidelity"]["achieved"] is None
    assert report["fidelity"]["actual_physx_executed"] is False
    assert report["execution"]["physical_operation_authorized"] is False
    assert any("missing Isaac" in item for item in report["isaac"]["preflight_failures"])
    assert (output / "kit.stdout.log").is_file()
    assert (output / "kit.stderr.log").is_file()


def test_l2_report_without_actual_physx_cannot_pass() -> None:
    project = ROOT / "examples" / "pen_engraving"
    scenario = project / "physical" / "scenarios" / "nominal.yaml"
    inputs = demo._canonical_inputs(project, scenario, adapter_config="runtime/l2-adapters.json")
    preflight = {
        "isaac_version": "6.0.1",
        "gpu_name": "NVIDIA test GPU",
        "failures": [],
        "kit_path": ROOT / "missing-kit",
        "app_path": ROOT / "missing-app",
    }
    report, _trace, _assertions = demo._build_l2_report(
        inputs=inputs,
        source=demo._source_identity(ROOT),
        preflight=preflight,
        raw={
            "isaac_version": "6.0.1",
            "gpu": {"name": "NVIDIA test GPU", "is_cuda": True},
            "summary": {"passed": 100, "failed": 0},
            "actual_physx_executed": False,
            "event_origin": "runtime/adapters",
        },
        probe_exit_code=0,
        artifacts={"trace": "trace.json", "task027_report": "task027-report.json"},
    )

    assert report["result"]["passed"] is False
    assert report["fidelity"]["achieved"] is None
    assert report["fidelity"]["actual_physx_executed"] is False
    assert any("actual_physx_executed" in item for item in report["result"]["failures"])


def test_invalid_assertion_fails_before_claiming_success(tmp_path: Path) -> None:
    assert _run_l0(tmp_path / "invalid", 20260820, "--assertion", "not-an-assertion") == 2
