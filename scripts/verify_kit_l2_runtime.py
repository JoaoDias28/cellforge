"""Task 027 Isaac Sim 6 GPU adapter/scenario and 100-seed evidence probe."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import omni.kit.app
import omni.usd
import warp as wp
import yaml
from isaacsim.core.api import World

app = omni.kit.app.get_app()


def _execute_nominal(runtime: Any) -> None:
    command = 0

    def execute(capability: str, **payload: Any) -> Any:
        nonlocal command
        command += 1
        return runtime.execute(capability, payload, command_id=f"isaac-probe-{command:04d}")

    sequence = [
        execute("vision.action.locate_object"),
        execute("robot_motion.action.execute_trajectory", operation="pick"),
        execute("robot_motion.action.execute_trajectory", operation="load"),
        execute("fixture.action.verify_seated"),
        execute("robot_motion.action.execute_trajectory", operation="process_safe"),
        execute("process.action.select_program", program_id="ALU_REFERENCE_01"),
        execute("process.action.execute_cycle", engraving_text="CELLFORGE"),
        execute("vision.action.inspect_object"),
        execute("robot_motion.action.execute_trajectory", operation="unload"),
    ]
    failures = [
        {"result_code": outcome.result_code, "output": outcome.output}
        for outcome in sequence
        if not outcome.success
    ]
    if failures:
        raise RuntimeError(f"nominal L2 adapter sequence failed: {failures}")


def _scenario(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain an object")
    return value


async def run() -> None:
    try:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "ros_ws" / "src" / "cellforge_simulation"))
        from cellforge_simulation.l2_runtime import IsaacL2Runtime
        from cellforge_simulation.pen_physics_backend import IsaacPenPhysicsBackend
        from cellforge_simulation.physical import DEFAULT_BOUNDS, sample_pen_pose

        version = (
            (Path(os.environ.get("ISAAC_SIM_ROOT", "C:/isaacsim")) / "VERSION")
            .read_text(encoding="utf-8")
            .strip()
        )
        if not version.startswith("6."):
            raise RuntimeError(f"Task 027 requires Isaac Sim 6, found {version!r}")
        if not wp.is_cuda_available():
            raise RuntimeError("Task 027 requires an NVIDIA CUDA GPU; CPU fallback is forbidden")
        gpu = wp.get_device("cuda:0")

        context = omni.usd.get_context()
        scene = root / "examples" / "pen_engraving" / "scene.usda"
        await context.open_stage_async(str(scene))
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("Task 027 canonical USD scene was not available")
        scenario_root = root / "examples" / "pen_engraving" / "physical" / "scenarios"
        fault_documents = {
            filename: _scenario(scenario_root / filename)
            for filename in ("dropped_pen.yaml", "failed_seating.yaml", "collision.yaml")
        }
        seeds = set(range(100))
        seeds.update(int(document["scenario"]["seed"]) for document in fault_documents.values())
        stage_builder = IsaacPenPhysicsBackend(stage)
        for seed in sorted(seeds):
            stage_builder.spawn_pen(f"pen-{seed:08d}", sample_pen_pose(seed, DEFAULT_BOUNDS))
        world = World(stage_units_in_meters=1.0)
        await world.initialize_simulation_context_async()
        await world.reset_async()
        backend = IsaacPenPhysicsBackend(stage, world)

        nominal_document = _scenario(
            root / "examples" / "pen_engraving" / "physical" / "scenarios" / "nominal.yaml"
        )
        seeded_runs: list[dict[str, Any]] = []
        for seed in range(100):
            document = json.loads(json.dumps(nominal_document))
            document["scenario"]["id"] = f"pen-l2-seed-{seed:04d}"
            document["scenario"]["seed"] = seed
            runtime = IsaacL2Runtime(backend, document)
            _execute_nominal(runtime)
            seeded_runs.append(
                {
                    **runtime.evidence_metadata(),
                    "events": [event.as_json() for event in runtime.events],
                }
            )

        required_faults = {
            "dropped_pen.yaml": "simulation.pen.dropped",
            "failed_seating.yaml": "fixture.sensor.seating_failed",
            "collision.yaml": "motion.plan.collision",
        }
        fault_results: list[dict[str, Any]] = []
        for filename, expected in required_faults.items():
            runtime = IsaacL2Runtime(backend, fault_documents[filename])
            pick = runtime.execute(
                "robot_motion.action.execute_trajectory",
                {"operation": "pick"},
                command_id=f"fault-{filename}-pick",
            )
            outcome = pick
            if filename == "failed_seating.yaml" and pick.success:
                load = runtime.execute(
                    "robot_motion.action.execute_trajectory",
                    {"operation": "load"},
                    command_id="fault-seating-load",
                )
                if not load.success:
                    raise RuntimeError(f"failed seating setup did not load: {load.result_code}")
                outcome = runtime.execute(
                    "fixture.action.verify_seated", {}, command_id="fault-seating-verify"
                )
            if outcome.result_code != expected:
                raise RuntimeError(
                    f"{filename} produced {outcome.result_code!r}, expected {expected!r}"
                )
            fault_results.append(
                {
                    **runtime.evidence_metadata(),
                    "result_code": outcome.result_code,
                    "events": [event.as_json() for event in runtime.events],
                }
            )

        encoded_runs = json.dumps(seeded_runs, sort_keys=True, separators=(",", ":")).encode()
        report = {
            "schema_version": "0.1.0",
            "kind": "cellforge.isaac_l2_seed_report",
            "isaac_version": version,
            "gpu": {"name": gpu.name, "is_cuda": gpu.is_cuda},
            "scene": str(scene),
            "scene_sha256": hashlib.sha256(scene.read_bytes()).hexdigest(),
            "summary": {"passed": 100, "failed": 0},
            "seed_range": {"first": 0, "count": 100},
            "replay_sha256": hashlib.sha256(encoded_runs).hexdigest(),
            "actual_physx_executed": True,
            "event_origin": "runtime/adapters",
            "runs": seeded_runs,
            "fault_scenarios": fault_results,
            "limitations": nominal_document.get("limitations", []) or seeded_runs[0]["limitations"],
        }
        output = Path(
            os.environ.get(
                "CELLFORGE_L2_REPORT",
                str(root / ".artifacts" / "task027" / "isaac-l2-seed-report.json"),
            )
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            "Task 027 Isaac Sim 6 GPU L2 adapter probe passed: "
            f"100/100 seeds, 3/3 PhysX fault scenarios, report={output}."
        )
    except BaseException:
        traceback.print_exc()
        app.post_quit(1)
        return
    app.post_quit(0)


asyncio.ensure_future(run())
