"""Acceptance verification probe for Task 033 Complete Software Release Qualification.

Verifies end-to-end:
1. Automated Studio-to-L0/L2-to-evidence-to-signed-bundle-to-runtime qualification workflow.
2. Full qualification scenario matrix: nominal, fault, cancel, timeout, restart,
   corrupt-bundle, offline-platform, stale-device, uncertain-process.
3. Parity proof: behavior tree and recipe run across L0 and L2 with zero simulator branches.
4. Platform lifecycle: reversible migrations, dual-role recipe approvals, author self-approval
   rejection, content-addressed evidence records, and idempotent production synchronization.
5. Signed qualification report with Git revisions, cell/component identities, versions, seeds,
   and explicit limitations.
"""

from __future__ import annotations

# ruff: noqa: E402
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_domain" / "src"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_bundle" / "src"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_platform" / "src"))
sys.path.insert(0, str(ROOT / "src" / "kit" / "cellforge.studio"))

from cellforge_bundle.qualification import (
    QualificationCategory,
    run_software_release_qualification,
    verify_qualification_report,
    verify_tree_and_recipe_parity,
)


def run_acceptance_probe() -> int:
    print("================================================================================")
    print("  CellForge Task 033: Complete Software Release Qualification Probe")
    print("================================================================================")

    project_path = ROOT / "examples" / "pen_engraving"
    schemas_path = ROOT / "schemas"

    # -------------------------------------------------------------------------
    # Stage 1: Behavior Tree & Recipe Parity Verification
    # -------------------------------------------------------------------------
    print("\n[Stage 1] Verifying Behavior Tree & Recipe Parity (L0 vs L2)...")
    parity = verify_tree_and_recipe_parity(project_path)
    if not parity.passed:
        print(f"FAILED: Parity verification failed: {parity.details}", file=sys.stderr)
        return 1
    if parity.has_simulator_branches:
        print(
            f"FAILED: Simulator-specific branches detected: {parity.forbidden_branch_nodes}",
            file=sys.stderr,
        )
        return 1
    print(f"  [OK] Tree ({parity.tree_path}) and recipe ({parity.recipe_path}) verified.")
    print("  [OK] Zero simulator-specific branch nodes or conditionals present.")

    # -------------------------------------------------------------------------
    # Stage 2: Qualification Scenario Matrix Execution
    # -------------------------------------------------------------------------
    print("\n[Stage 2] Executing Complete Qualification Scenario Matrix...")
    signing_key = Ed25519PrivateKey.generate()
    report = run_software_release_qualification(
        project_path,
        schemas_path,
        signing_key=signing_key,
        key_id="cellforge-task033-qualification-key",
    )

    categories_tested = {s.category for s in report.scenarios}
    required_categories = {
        QualificationCategory.NOMINAL,
        QualificationCategory.FAULT,
        QualificationCategory.CANCEL,
        QualificationCategory.TIMEOUT,
        QualificationCategory.RESTART,
        QualificationCategory.CORRUPT_BUNDLE,
        QualificationCategory.OFFLINE_PLATFORM,
        QualificationCategory.STALE_DEVICE,
        QualificationCategory.UNCERTAIN_PROCESS,
    }

    missing_categories = required_categories - categories_tested
    if missing_categories:
        print(
            f"FAILED: Missing qualification scenario categories: {missing_categories}",
            file=sys.stderr,
        )
        return 1

    for sc in report.scenarios:
        status_str = "PASS" if sc.passed else "FAIL"
        cat_str = f"{sc.category.value:18}"
        id_str = f"{sc.scenario_id:28}"
        print(
            f"  - [{status_str}] {cat_str} | ID: {id_str} | "
            f"Fidelity: {sc.achieved_fidelity} | Status: {sc.final_status}"
        )
        if not sc.passed:
            print(
                f"FAILED: Scenario '{sc.scenario_id}' failed: {sc.failure_reasons}",
                file=sys.stderr,
            )
            return 1

    # -------------------------------------------------------------------------
    # Stage 3: Platform Lifecycle & Dual-Role Approvals Verification
    # -------------------------------------------------------------------------
    print("\n[Stage 3] Verifying Platform Lifecycle, Approvals, & Results Sync...")
    plat = report.platform
    if not (
        plat.migrations_passed
        and plat.dual_role_approval_verified
        and plat.self_approval_rejected
        and plat.evidence_records_verified
        and plat.offline_buffering_verified
        and plat.idempotent_sync_verified
    ):
        print(f"FAILED: Platform qualification verification failed: {plat}", file=sys.stderr)
        return 1
    print("  [OK] Reversible migrations (levels 0-4) verified.")
    print("  [OK] Two-role append-only recipe approval ledger verified (self-approval rejected).")
    print("  [OK] Offline local persistence and idempotent sync verified.")

    # -------------------------------------------------------------------------
    # Stage 4: Cryptographic Report Signature & Limitations Verification
    # -------------------------------------------------------------------------
    print("\n[Stage 4] Verifying Signed Qualification Report & Limitations...")
    if not report.signature:
        print("FAILED: Qualification report missing Ed25519 signature", file=sys.stderr)
        return 1

    if not verify_qualification_report(report, signing_key.public_key()):
        print("FAILED: Cryptographic verification of qualification report failed", file=sys.stderr)
        return 1

    # Verify mandatory limitations
    for req_limit in ("functional_safety", "laser_process_simulation", "hardware_qualification"):
        if req_limit not in report.limitations:
            print(
                f"FAILED: Missing mandatory qualification disclaimer '{req_limit}'",
                file=sys.stderr,
            )
            return 1

    print("  [OK] Ed25519 cryptographic signature verified.")
    print("  [OK] Mandatory safety, process physics, and Task 034 hardware disclaimers verified.")

    # -------------------------------------------------------------------------
    # Stage 5: Save Canonical Qualification Report Artifact
    # -------------------------------------------------------------------------
    reports_dir = project_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "software_release_qualification_report.json"
    report_file.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    print(f"  [OK] Saved signed qualification report to: {report_file}")

    print("\n================================================================================")
    print("  QUALIFICATION COMPLETE: All Software-Side MVP Acceptance Criteria Passed!")
    print("  Task 034 (First Real Hardware Adapters) is Eligible for Implementation.")
    print("================================================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_acceptance_probe())
