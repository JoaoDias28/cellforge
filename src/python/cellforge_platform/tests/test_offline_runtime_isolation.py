"""Verification that local cell runtime operates completely offline."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cellforge_bundle.agent import verify_bundle
from cellforge_bundle.assembly import assemble_bundle
from cellforge_domain import ExecutionMode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPOSITORY_ROOT = Path(__file__).parents[4]


def test_bundle_agent_operates_completely_offline_without_platform_service(tmp_path: Path) -> None:
    # Generate keypair
    private_key = Ed25519PrivateKey.generate()
    signing_key_path = tmp_path / "bundle-signing-key.pem"
    signing_key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key_id = hashlib.sha256(public_bytes).hexdigest()

    trusted_keys_dir = tmp_path / "trusted_keys"
    trusted_keys_dir.mkdir()
    (trusted_keys_dir / f"{key_id}.pub").write_bytes(public_bytes)

    # Assemble signed bundle from reference project
    bundle_out = tmp_path / "dist"
    assembled = assemble_bundle(
        REPOSITORY_ROOT / "examples" / "pen_engraving",
        REPOSITORY_ROOT / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.SIMULATION,
        output=bundle_out,
        signing_key=signing_key_path,
        source_revision="0" * 40,
    )

    # Verify bundle completely offline
    verified = verify_bundle(
        assembled.output,
        trusted_keys=trusted_keys_dir,
        require_signature=True,
    )
    assert verified.bundle_id == assembled.bundle_id
    assert verified.systemd_unit == "cellforge-runtime.target"
    assert (assembled.output / "checksums.txt").is_file()
    assert (assembled.output / "signature.json").is_file()
