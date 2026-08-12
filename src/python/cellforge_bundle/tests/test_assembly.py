"""Task 026 installable signed bundle assembly contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cellforge_bundle.agent import (
    AgentError,
    AgentPaths,
    BundleAgent,
    HealthConfiguration,
    verify_bundle,
)
from cellforge_bundle.assembly import assemble_bundle
from cellforge_domain import ExecutionMode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPOSITORY_ROOT = Path(__file__).parents[4]


def _key_material(tmp_path: Path) -> tuple[Path, Path]:
    private = Ed25519PrivateKey.generate()
    signing_key = tmp_path / "bundle-signing-key.pem"
    signing_key.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key_id = hashlib.sha256(public).hexdigest()
    trusted = tmp_path / "trusted-keys"
    trusted.mkdir()
    (trusted / f"{key_id}.pub").write_bytes(public)
    return signing_key, trusted


def _assemble(tmp_path: Path, name: str, signing_key: Path) -> Path:
    return assemble_bundle(
        REPOSITORY_ROOT / "examples" / "pen_engraving",
        REPOSITORY_ROOT / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.SIMULATION,
        source_revision="a" * 40,
        output=tmp_path / name,
        signing_key=signing_key,
    ).output


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_assembly_is_byte_identical_and_verifies_with_local_trust(tmp_path: Path) -> None:
    signing_key, trusted = _key_material(tmp_path)
    first = _assemble(tmp_path, "first", signing_key)
    second = _assemble(tmp_path, "second", signing_key)

    assert _tree(first) == _tree(second)
    verified = verify_bundle(first, trusted_keys=trusted, require_signature=True)
    assert verified.bundle_id == json.loads((first / "manifest.json").read_text())["bundle_id"]
    assert (first / "config" / "launch.json").is_file()
    assert (first / "evidence-summary.json").is_file()
    assert (first / "scripts" / "start-runtime").is_file()


def test_invalid_signature_is_rejected_after_checksum_recalculation(tmp_path: Path) -> None:
    signing_key, trusted = _key_material(tmp_path)
    bundle = _assemble(tmp_path, "bundle", signing_key)
    signature = json.loads((bundle / "signature.json").read_text())
    signature["signature"] = (
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
    )
    (bundle / "signature.json").write_text(
        json.dumps(signature, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8"
    )
    checksums = []
    for path in sorted(
        item for item in bundle.rglob("*") if item.is_file() and item.name != "checksums.txt"
    ):
        relative = path.relative_to(bundle).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {relative}\n")
    (bundle / "checksums.txt").write_text("".join(checksums), encoding="ascii", newline="\n")

    with pytest.raises(AgentError, match="agent.signature.invalid"):
        verify_bundle(bundle, trusted_keys=trusted, require_signature=True)


def test_tampered_derived_launcher_is_rejected_after_checksum_recalculation(tmp_path: Path) -> None:
    signing_key, trusted = _key_material(tmp_path)
    bundle = _assemble(tmp_path, "bundle", signing_key)
    launcher = bundle / "config" / "launch.json"
    launcher.write_text('{"package":"untrusted"}\n', encoding="utf-8")
    checksums = []
    for path in sorted(
        item for item in bundle.rglob("*") if item.is_file() and item.name != "checksums.txt"
    ):
        relative = path.relative_to(bundle).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {relative}\n")
    (bundle / "checksums.txt").write_text("".join(checksums), encoding="ascii", newline="\n")

    with pytest.raises(AgentError, match="agent.signature.invalid"):
        verify_bundle(bundle, trusted_keys=trusted, require_signature=True)


class _Activation:
    def __init__(self) -> None:
        self.active: str | None = None

    def current_bundle_id(self) -> str | None:
        return self.active

    def activate(self, bundle_id: str) -> None:
        self.active = bundle_id

    def clear(self) -> None:
        self.active = None


class _Services:
    def stop(self, _unit: str) -> None:
        return None

    def start(self, _unit: str) -> None:
        return None

    def is_active(self, _unit: str) -> bool:
        return True

    def daemon_reload(self) -> None:
        return None

    def enable(self, _unit: str) -> None:
        return None


class _Health:
    def __init__(self) -> None:
        self.failed: set[str] = set()

    def wait_healthy(self, bundle_id: str, _configuration: HealthConfiguration) -> None:
        if bundle_id in self.failed:
            raise AgentError("agent.health.timeout", "injected health failure")


def test_assembled_bundle_installs_and_failed_health_restores_previous_release(
    tmp_path: Path,
) -> None:
    signing_key, trusted = _key_material(tmp_path)
    first = _assemble(tmp_path, "first", signing_key)
    second = assemble_bundle(
        REPOSITORY_ROOT / "examples" / "pen_engraving",
        REPOSITORY_ROOT / "schemas",
        target_profile="pen-sim-amd64",
        mode=ExecutionMode.SIMULATION,
        source_revision="b" * 40,
        output=tmp_path / "second",
        signing_key=signing_key,
    ).output
    manifest = json.loads((first / "manifest.json").read_text())
    runtime = manifest["runtime"]
    facts = {
        "schema_version": "0.1.0",
        "profile_id": "pen-sim-amd64",
        "platform": {
            "arch": "amd64",
            "gpu": {"available": False},
            "os": "ubuntu-24.04",
            "ros_distribution": "jazzy",
        },
        "native_packages": manifest["native_packages"],
        "external_prerequisites": manifest["external_prerequisites"],
        "runtime_entrypoints": sorted(
            f"{item['package']}:{item['executable']}" for item in runtime["executables"].values()
        ),
    }
    paths = AgentPaths(
        install_root=tmp_path / "opt",
        state_root=tmp_path / "state",
        secret_store=tmp_path / "secrets",
        target_facts=tmp_path / "target.json",
        trusted_keys=trusted,
    )
    paths.target_facts.write_text(json.dumps(facts), encoding="utf-8")
    activation = _Activation()
    health = _Health()
    agent = BundleAgent(paths, activation=activation, services=_Services(), health=health)
    facts["runtime_entrypoints"] = []
    paths.target_facts.write_text(json.dumps(facts), encoding="utf-8")
    with pytest.raises(AgentError, match="agent.target.entrypoints_missing"):
        agent.install(first)
    assert activation.active is None
    facts["runtime_entrypoints"] = sorted(
        f"{item['package']}:{item['executable']}" for item in runtime["executables"].values()
    )
    paths.target_facts.write_text(json.dumps(facts), encoding="utf-8")
    first_id = agent.install(first).active_bundle_id
    assert first_id is not None
    previous_environment = paths.runtime_environment.read_bytes()
    second_id = json.loads((second / "manifest.json").read_text())["bundle_id"]
    health.failed.add(second_id)

    with pytest.raises(AgentError, match="agent.activation.rolled_back"):
        agent.install(second)

    assert agent.status().active_bundle_id == first_id
    assert paths.runtime_environment.read_bytes() == previous_environment
