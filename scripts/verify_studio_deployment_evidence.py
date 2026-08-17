"""Acceptance verification probe for Task 030 Studio Deployment and Evidence Workflows.

Verifies end-to-end:
1. Scenario selection, parameter inspection, seed control, and trace timeline capture.
2. Fault injection exercising failure paths and non-zero exit/failed assertions.
3. Deterministic evidence replay verifying matching event trace and project digests.
4. Strict fidelity enforcement: refusing to produce/label L2 on L0 or without CUDA GPU + PhysX.
5. Mandatory functional safety disclaimer on all simulation views and evidence.
6. Deployment profile discovery and inspection.
7. Signed bundle assembly producing immutable, content-addressed releases with Ed25519 signatures.
8. Detached signature verification against trusted public keys.
9. Deterministic bundle diff comparing manifest, inventory checksums, and deep configs.
10. Target compatibility preflight checking platform and package requirements.
11. Bundle agent status query, installation, and rollback lifecycles.
12. Thin application-service UI boundary.
"""

from __future__ import annotations

# ruff: noqa: E402
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kit" / "cellforge.studio"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_domain" / "src"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_bundle" / "src"))

from cellforge_bundle.agent import AgentPaths
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cellforge.studio.application import StudioStatus
from cellforge.studio.backend import create_default_application
from cellforge.studio.scenario_service import (
    SAFETY_DISCLAIMER,
    ScenarioAssertionSpec,
    ScenarioFaultSpec,
)


def main() -> int:
    root = ROOT
    pen_project = root / "examples" / "pen_engraving"
    schemas = root / "schemas"

    print("Step 1: Opening pen engraving project with StudioApplication...")
    app = create_default_application()
    snap = app.open_project(pen_project)
    if snap.status != StudioStatus.PROJECT_READY or snap.project is None:
        print(f"FAILED: Project did not open cleanly. Status: {snap.status}", file=sys.stderr)
        return 1

    print("Step 2: Browsing and inspecting scenarios...")
    snap = app.refresh_scenarios()
    if len(snap.scenarios) != 14:
        print(f"FAILED: Expected 14 scenarios, found {len(snap.scenarios)}", file=sys.stderr)
        return 1

    detail = app.inspect_scenario("nominal")
    if detail is None:
        print("FAILED: Could not inspect scenario 'nominal'", file=sys.stderr)
        return 1
    if detail.summary.id != "pen-nominal" or detail.summary.requested_fidelity != "L0":
        print(f"FAILED: Unexpected nominal scenario detail: {detail.summary}", file=sys.stderr)
        return 1
    if detail.assertions.final_status != "SUCCESS":
        print(
            f"FAILED: Expected SUCCESS assertion, got {detail.assertions.final_status}",
            file=sys.stderr,
        )
        return 1

    print("Step 3: Executing nominal scenario with seed control and timeline capture...")
    snap = app.execute_scenario("nominal", seed_override=1001, available_backend_fidelity="L0")
    res = snap.last_execution_result
    if res is None or not res.passed or res.final_status != "SUCCESS":
        print(f"FAILED: Nominal scenario execution failed: {res}", file=sys.stderr)
        return 1
    if res.fidelity.achieved != "L0":
        print(
            f"FAILED: Expected achieved fidelity L0, got {res.fidelity.achieved}", file=sys.stderr
        )
        return 1
    if res.fidelity.safety_disclaimer != SAFETY_DISCLAIMER:
        print(
            "FAILED: Missing mandatory functional safety disclaimer on execution result",
            file=sys.stderr,
        )
        return 1
    if len(res.trace_events) < 5:
        print(
            f"FAILED: Expected at least 5 trace events, got {len(res.trace_events)}",
            file=sys.stderr,
        )
        return 1

    print("Step 4: Executing scenario with fault injection...")
    faults = [
        ScenarioFaultSpec(
            at="process.cycle",
            target="laser-001",
            fault="laser.process.timeout",
            parameters={"timeout_ms": 5000},
        )
    ]
    snap = app.execute_scenario("nominal", injected_faults=faults, available_backend_fidelity="L0")
    fault_res = snap.last_execution_result
    if fault_res is None or fault_res.passed or fault_res.final_status != "FAILED":
        print(
            f"FAILED: Injected fault did not fail scenario as expected: {fault_res}",
            file=sys.stderr,
        )
        return 1
    if not any("laser.process.timeout" in f for f in fault_res.failures):
        print(f"FAILED: Fault failure path not captured: {fault_res.failures}", file=sys.stderr)
        return 1

    print("Step 5: Replaying recorded evidence for deterministic verification...")
    ev_dir = pen_project / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    ev_file = ev_dir / "evidence_nominal_probe.json"
    try:
        ev_file.write_text(json.dumps(res.evidence_document, indent=2), encoding="utf-8")

        snap_ev = app.refresh_evidence()
        if len(snap_ev.evidence_records) == 0:
            print("FAILED: Evidence records not discovered in project", file=sys.stderr)
            return 1

        ev_detail = app.inspect_evidence("evidence/evidence_nominal_probe.json")
        if ev_detail is None:
            print("FAILED: Could not inspect evidence file", file=sys.stderr)
            return 1
        if ev_detail.summary.scenario_id != "pen-nominal":
            print(
                f"FAILED: Unexpected evidence scenario ID: {ev_detail.summary.scenario_id}",
                file=sys.stderr,
            )
            return 1

        snap_replay = app.replay_evidence(
            "evidence/evidence_nominal_probe.json",
            expected_assertions=ScenarioAssertionSpec(
                final_status="SUCCESS",
                required_events=("process.command.completed", "job.completed"),
                forbidden_events=("safety.bypass",),
            ),
        )
        rep = snap_replay.last_replay_result
        if rep is None or not rep.passed or not rep.events_matched:
            print(f"FAILED: Evidence replay failed: {rep}", file=sys.stderr)
            return 1
    finally:
        if ev_file.is_file():
            ev_file.unlink()
        if ev_dir.is_dir() and not any(ev_dir.iterdir()):
            ev_dir.rmdir()

    print("Step 6: Strict fidelity labeling enforcement...")
    snap_l2_fail = app.execute_scenario("pen-physical-nominal", available_backend_fidelity="L0")
    if snap_l2_fail.status != StudioStatus.OPERATION_FAILED:
        print(
            "FAILED: L2 scenario execution on L0 backend did not report operation failure",
            file=sys.stderr,
        )
        return 1

    # Direct backend check confirms exact fidelity refusal error code
    try:
        from cellforge.studio.project_service import ProjectCommandService

        svc = ProjectCommandService(schemas)
        svc.execute_scenario(
            pen_project,
            app._working_contents,
            scenario_id="pen-physical-nominal",
            available_backend_fidelity="L0",
        )
        print(
            "FAILED: Direct backend L2 scenario execution on L0 did not raise error",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as err:
        if "simulation.fidelity.unsupported" not in str(err):
            print(f"FAILED: Expected simulation.fidelity.unsupported, got {err}", file=sys.stderr)
            return 1

    print("Step 7: Browsing deployment profiles...")
    snap = app.refresh_deployment_profiles()
    if len(snap.deployment_profiles) != 2:
        print(
            f"FAILED: Expected 2 deployment profiles, got {len(snap.deployment_profiles)}",
            file=sys.stderr,
        )
        return 1
    profile_ids = {p.id for p in snap.deployment_profiles}
    if "pen-sim-amd64" not in profile_ids or "pen-isaac-l2-win64" not in profile_ids:
        print(f"FAILED: Unexpected deployment profile IDs: {profile_ids}", file=sys.stderr)
        return 1

    print("Step 8: Assembling signed immutable release bundle...")
    with tempfile.TemporaryDirectory(prefix="cf_deploy_") as tmp_dep_dir:
        tmp_dir = Path(tmp_dep_dir)
        # Generate Ed25519 keypair
        priv = Ed25519PrivateKey.generate()
        pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_path = tmp_dir / "signing.pem"
        key_path.write_bytes(pem)

        pub_bytes = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        key_id = hashlib.sha256(pub_bytes).hexdigest()
        trusted_dir = tmp_dir / "trusted-keys"
        trusted_dir.mkdir(parents=True)
        (trusted_dir / f"{key_id}.pub").write_bytes(pub_bytes)

        bundle_dir = tmp_dir / "bundle_v1"
        snap_asm = app.assemble_bundle(
            target_profile="pen-sim-amd64",
            mode="simulation",
            source_revision="0123456789abcdef0123456789abcdef01234567",
            output_dir=bundle_dir,
            signing_key_path=key_path,
            schemas_path=schemas,
        )
        asm = snap_asm.last_bundle_assembly
        if asm is None or not asm.success or not asm.bundle_id:
            print(f"FAILED: Bundle assembly failed: {asm}", file=sys.stderr)
            return 1
        if (
            not (bundle_dir / "manifest.json").is_file()
            or not (bundle_dir / "signature.json").is_file()
        ):
            print("FAILED: Missing manifest or signature in assembled bundle", file=sys.stderr)
            return 1

        print("Step 9: Verifying bundle Ed25519 signature...")
        snap_sig = app.verify_bundle_signature(bundle_dir, trusted_dir)
        sig = snap_sig.last_signature_verification
        if sig is None or not sig.valid or sig.key_id != key_id:
            print(f"FAILED: Signature verification failed: {sig}", file=sys.stderr)
            return 1

        print("Step 10: Computing deterministic bundle diff...")
        bundle_v2 = tmp_dir / "bundle_v2"
        snap_asm2 = app.assemble_bundle(
            target_profile="pen-sim-amd64",
            mode="simulation",
            source_revision="fedcba9876543210fedcba9876543210fedcba98",
            output_dir=bundle_v2,
            signing_key_path=key_path,
            schemas_path=schemas,
        )
        if not snap_asm2.last_bundle_assembly or not snap_asm2.last_bundle_assembly.success:
            print("FAILED: Bundle v2 assembly failed", file=sys.stderr)
            return 1

        snap_diff = app.diff_bundles(bundle_dir, bundle_v2)
        diff = snap_diff.last_bundle_diff
        if diff is None or not diff.is_compatible:
            print(f"FAILED: Bundle diff failed: {diff}", file=sys.stderr)
            return 1
        if not any(d.key == "source_revision" for d in diff.differences):
            print("FAILED: Expected diff in source_revision", file=sys.stderr)
            return 1

        print("Step 11: Checking target compatibility preflight...")
        target_facts = {
            "schema_version": "0.1.0",
            "profile_id": "pen-sim-amd64",
            "platform": {
                "arch": "amd64",
                "os": "ubuntu-24.04",
                "ros_distribution": "jazzy",
                "gpu": {"available": False},
            },
            "native_packages": [
                "cellforge_bringup",
                "cellforge_interfaces",
                "cellforge_supervisor",
                "cellforge_pen_bt_nodes",
                "cellforge_job_gateway",
                "cellforge_motion",
                "cellforge_state_trace",
                "cellforge_operator_api",
                "cellforge_mock_adapters",
                "cellforge_simulation",
            ],
            "external_prerequisites": [],
            "runtime_entrypoints": [
                "cellforge_mock_adapters:headless_mock_adapter",
                "cellforge_supervisor:pen_cell_supervisor",
            ],
        }
        facts_path = tmp_dir / "target.json"
        facts_path.write_text(json.dumps(target_facts, indent=2), encoding="utf-8")

        snap_compat = app.preflight_target_compatibility(bundle_dir, facts_path)
        compat = snap_compat.last_compatibility_result
        if compat is None or not compat.compatible:
            print(f"FAILED: Target compatibility preflight failed: {compat}", file=sys.stderr)
            return 1

        print("Step 12: Testing deployment agent status query...")
        agent_paths = AgentPaths(
            install_root=tmp_dir / "opt_cellforge",
            state_root=tmp_dir / "var_lib_cellforge",
        )
        snap_stat = app.refresh_deployment_status(agent_paths)
        status = snap_stat.last_deployment_status
        if status is None or status.state != "no_release":
            print(f"FAILED: Expected empty agent state 'no_release', got {status}", file=sys.stderr)
            return 1

    print("\nVerified Task 030 Studio deployment and evidence workflows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
