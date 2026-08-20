"""End-to-end integration tests for software release qualification."""

from __future__ import annotations

import json
from pathlib import Path

from cellforge_bundle.qualification import (
    run_software_release_qualification,
    verify_qualification_report,
)
from cellforge_cli.main import main as cli_main
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROJECT = ROOT / "examples" / "pen_engraving"
SCHEMAS = ROOT / "schemas"


def test_cli_qualify_command_reports_l2_unavailable_and_writes_signed_report(
    tmp_path: Path,
) -> None:
    key = Ed25519PrivateKey.generate()
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = tmp_path / "qual_key.pem"
    key_path.write_bytes(key_pem)

    output_report_path = tmp_path / "qualification_report.json"

    exit_code = cli_main(
        [
            "qualify",
            str(EXAMPLE_PROJECT),
            "--signing-key",
            str(key_path),
            "--output",
            str(output_report_path),
        ]
    )

    assert exit_code != 0
    assert output_report_path.is_file()

    report_data = json.loads(output_report_path.read_text(encoding="utf-8"))
    assert report_data["overall_passed"] is False
    assert report_data["signature"] is not None
    assert len(report_data["scenarios"]) >= 9
    assert report_data["parity"]["passed"] is True
    assert report_data["platform"]["passed"] is True
    assert report_data["l2"]["status"] == "unavailable"
    assert all(item["observed"] and item["artifact_sha256"] for item in report_data["scenarios"])


def test_complete_software_release_qualification_pipeline(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    report = run_software_release_qualification(
        EXAMPLE_PROJECT,
        SCHEMAS,
        signing_key=key,
        evidence_dir=tmp_path / "evidence",
    )

    assert not report.overall_passed
    assert report.cell_id == "0d3c6b63-a57f-4207-8638-e4cf76efec90"
    assert report.parity.passed
    assert report.parity.dynamic_observed
    assert not report.parity.has_simulator_branches
    assert report.platform.migrations_passed
    assert report.platform.dual_role_approval_verified
    assert report.platform.self_approval_rejected
    assert report.platform.idempotent_sync_verified
    assert len(report.scenarios) >= 9
    assert report.l2["status"] == "unavailable"
    assert verify_qualification_report(report, key.public_key())
