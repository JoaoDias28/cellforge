"""Execute the fail-closed software release qualification gates.

The default CI mode runs every gate available without Isaac Sim and writes a report that
explicitly marks external Task 027 L2 evidence unavailable. Use ``--require-l2`` for a
release decision that must include a validated actual-PhysX report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_domain" / "src"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_bundle" / "src"))
sys.path.insert(0, str(ROOT / "src" / "python" / "cellforge_platform" / "src"))

from cellforge_bundle.qualification import (  # noqa: E402
    SoftwareReleaseQualificationReport,
    run_software_release_qualification,
    verify_qualification_report,
    verify_report_integrity,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        type=Path,
        default=ROOT / "examples" / "pen_engraving",
        help="canonical project to qualify",
    )
    parser.add_argument(
        "--schemas",
        type=Path,
        default=ROOT / "schemas",
        help="canonical schema directory",
    )
    parser.add_argument(
        "--l2-report",
        type=Path,
        help="external Task 027 Isaac Sim 6 actual-PhysX seed report",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=ROOT / ".artifacts" / "task036",
        help="directory for observed command and probe artifacts",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "examples"
        / "pen_engraving"
        / "reports"
        / "software_release_qualification_report.json",
        help="qualification report JSON output",
    )
    parser.add_argument(
        "--signing-key",
        type=Path,
        help="optional Ed25519 PEM key for the report signature",
    )
    parser.add_argument(
        "--require-l2",
        action="store_true",
        help="fail unless a valid Task 027 actual-PhysX report is supplied",
    )
    return parser


def _load_signing_key(path: Path | None) -> Ed25519PrivateKey | None:
    if path is None:
        return None
    value = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(value, Ed25519PrivateKey):
        raise ValueError("qualification signing key must be an Ed25519 private key")
    return value


def _artifact_is_intact(path_value: object, digest_value: object) -> bool:
    if not isinstance(path_value, str) or not path_value:
        return False
    path = Path(path_value)
    if not path.is_file() or not isinstance(digest_value, str) or not digest_value:
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == digest_value


def _report_failures(report: SoftwareReleaseQualificationReport) -> list[str]:
    failures: list[str] = []
    if not report.parity.passed:
        failures.append("canonical tree/recipe parity failed")
    if not report.parity.dynamic_observed:
        failures.append("L0 runner output was not observed")
    l0_gate = next(
        (item for item in report.evidence if item.get("gate") == "l0_scenarios"),
        {},
    )
    if l0_gate.get("status") != "passed":
        failures.append("L0 headless scenario command failed")
    if not _artifact_is_intact(
        l0_gate.get("command_artifact_path"), l0_gate.get("command_artifact_sha256")
    ):
        failures.append("L0 command artifact is missing or tampered")
    if not report.platform.passed or not report.platform.observed:
        failures.append("platform qualification probe failed or was not observed")
    l0_bundle = report.bundles.get("l0_sim", {})
    if not isinstance(l0_bundle, dict) or l0_bundle.get("passed") is not True:
        failures.append("signed L0 bundle assembly/agent verification failed")
    for scenario in report.scenarios:
        if not scenario.observed or not scenario.available or not scenario.passed:
            failures.append(f"scenario gate failed: {scenario.scenario_id}")
        if not _artifact_is_intact(scenario.artifact_path, scenario.artifact_sha256):
            failures.append(f"scenario artifact is missing or tampered: {scenario.scenario_id}")
    if not _artifact_is_intact(report.platform.artifact_path, report.platform.artifact_sha256):
        failures.append("platform command artifact is missing or tampered")
    if report.l2.get("status") == "passed" and not _artifact_is_intact(
        report.l2.get("report_path"), report.l2.get("report_sha256")
    ):
        failures.append("Task 027 L2 report artifact is missing or tampered")
    if not verify_report_integrity(report):
        failures.append("qualification report integrity seal is invalid")
    return failures


def run_acceptance_probe(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    project = arguments.project.resolve()
    schemas = arguments.schemas.resolve()
    signing_key = _load_signing_key(arguments.signing_key)
    command = shlex.join([sys.executable, *sys.argv])

    report = run_software_release_qualification(
        project,
        schemas,
        signing_key=signing_key,
        l2_report_path=arguments.l2_report.resolve() if arguments.l2_report else None,
        evidence_dir=arguments.evidence_dir.resolve(),
        repository_root=ROOT,
        qualification_command=command,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Qualification report: {arguments.output.resolve()}")
    print(f"Git revision: {report.git_revision or '<unavailable>'}")
    print(f"Git clean: {report.git_clean}")
    for scenario in report.scenarios:
        status = "PASS" if scenario.passed else "FAIL"
        print(
            f"[{status}] {scenario.category.value}: {scenario.scenario_id} "
            f"observed={scenario.observed} artifact={scenario.artifact_path}"
        )
    l2_status = str(report.l2.get("status", "failed"))
    if l2_status == "unavailable":
        print("[UNAVAILABLE] L2: no external Task 027 actual-PhysX report supplied")
    elif l2_status == "passed":
        print("[PASS] L2: Task 027 actual Isaac Sim 6/OpenUSD/PhysX evidence validated")
    else:
        print(f"[FAIL] L2: {report.l2.get('failure_reasons', [])}")

    failures = _report_failures(report)
    if report.signature:
        if signing_key is None or not verify_qualification_report(report, signing_key.public_key()):
            failures.append("qualification report signature is invalid")
        else:
            print("[PASS] Ed25519 qualification report signature verified")
    else:
        print("[PASS] SHA-256 qualification report integrity seal verified")

    if report.overall_passed:
        if failures or l2_status != "passed":
            print("QUALIFICATION OVERALL: FALSE (inconsistent evidence)", file=sys.stderr)
            return 1
        print("QUALIFICATION OVERALL: TRUE")
        return 0

    if failures:
        print("QUALIFICATION OVERALL: FALSE", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    if l2_status == "failed":
        print("QUALIFICATION OVERALL: FALSE (invalid L2 evidence)", file=sys.stderr)
        return 1
    if l2_status == "unavailable":
        print("QUALIFICATION OVERALL: FALSE (L2 unavailable; L0 evidence only)")
        return 1 if arguments.require_l2 else 0
    print("QUALIFICATION OVERALL: FALSE (a required gate did not pass)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(run_acceptance_probe())
