"""Public Task 026 bundle-assembly CLI contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cellforge_cli import ExitCode
from cellforge_cli.main import main
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPOSITORY_ROOT = Path(__file__).parents[4]


def test_bundle_assemble_is_explicit_and_preserves_manifest_only_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    private = Ed25519PrivateKey.generate()
    signing_key = tmp_path / "signing-key.pem"
    signing_key.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    output = tmp_path / "release"

    result = main(
        [
            "bundle",
            "assemble",
            str(REPOSITORY_ROOT / "examples" / "pen_engraving"),
            "--target",
            "pen-sim-amd64",
            "--mode",
            "simulation",
            "--source-revision",
            "c" * 40,
            "--output",
            str(output),
            "--signing-key",
            str(signing_key),
            "--json",
        ]
    )

    assert result == ExitCode.SUCCESS
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "bundle.assemble"
    assert payload["result"]["output"] == str(output.resolve())
    assert (output / "manifest.json").is_file()
    assert (output / "signature.json").is_file()
