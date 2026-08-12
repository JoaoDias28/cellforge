from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from cellforge_bundle.agent import (
    ActivationStore,
    AgentError,
    AgentPaths,
    AtomicSymlinkStore,
    BundleAgent,
    HealthConfiguration,
    LoopbackHealthChecker,
    ServiceManager,
    install_systemd_units,
    preflight_target,
    verify_bundle,
)
from cellforge_bundle.agent_cli import main
from cellforge_bundle.assembly import signature_payload
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()
_TEST_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw
)
_TEST_KEY_ID = hashlib.sha256(_TEST_PUBLIC_KEY).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _make_bundle(
    root: Path,
    *,
    marker: str,
    secret_reference: bool = False,
    extra_files: dict[str, bytes] | None = None,
) -> str:
    root.mkdir(parents=True)
    files: dict[str, bytes] = {
        "config/agent.json": _canonical(
            {
                "schema_version": "0.1.0",
                "systemd_unit": "cellforge-runtime.target",
                "health": {
                    "url": "http://127.0.0.1:9080/health",
                    "timeout_seconds": 2,
                    "interval_seconds": 0.05,
                },
            }
        ),
        "config/cell.yaml": f"cell: {marker}\n".encode(),
        "config/target-profile.yaml": yaml.safe_dump(
            {
                "schema_version": "0.1.0",
                "profile": {"id": "test-amd64", "name": "Test target"},
                "platform": {
                    "arch": "amd64",
                    "os": "ubuntu-24.04",
                    "ros_distribution": "jazzy",
                    "gpu": {"required": False},
                },
                "runtime": {"native_packages": ["cellforge_supervisor"], "containers": []},
                "network": {},
                "modes": ["simulation"],
                "external_prerequisites": ["test-runtime"],
            },
            sort_keys=True,
        ).encode(),
        "scripts/start-runtime": b"#!/bin/sh\nexec /usr/bin/true\n",
    }
    if secret_reference:
        files["config/secret-references.json"] = _canonical(
            {
                "schema_version": "0.1.0",
                "environment": {"LASER_API_TOKEN": "laser/api-token"},
            }
        )
    files.update(extra_files or {})
    for relative, content in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        if relative == "scripts/start-runtime":
            destination.chmod(0o755)

    manifest: dict[str, Any] = {
        "schema_version": "0.1.0",
        "bundle_id": "0" * 64,
        "source_revision": "1" * 40,
        "cell_id": "c032cd26-58fe-4d1b-8a58-9cb50c3c9317",
        "target_profile": "test-amd64",
        "execution_mode": "simulation",
        "capabilities": [],
        "components": [],
        "recipes": [],
        "tasks": [],
        "calibrations": [],
        "native_packages": ["cellforge_supervisor"],
        "containers": [],
        "external_prerequisites": ["test-runtime"],
        "evidence": {"required": False, "status": "not-required"},
        "files": [
            {"path": relative, "sha256": _digest(content), "size": len(content)}
            for relative, content in sorted(files.items())
        ],
    }
    hash_input = dict(manifest)
    del hash_input["bundle_id"]
    bundle_id = _digest(_canonical(hash_input))
    manifest["bundle_id"] = bundle_id
    (root / "manifest.json").write_bytes(_canonical(manifest))
    signature = _canonical(
        {
            "algorithm": "Ed25519",
            "bundle_id": bundle_id,
            "key_id": _TEST_KEY_ID,
            "schema_version": "0.1.0",
            "signature": base64.b64encode(
                _TEST_PRIVATE_KEY.sign(
                    signature_payload(bundle_id, {**files, "manifest.json": _canonical(manifest)})
                )
            ).decode(),
        }
    )
    (root / "signature.json").write_bytes(signature)
    checksum_files = {**files, "manifest.json": _canonical(manifest), "signature.json": signature}
    (root / "checksums.txt").write_text(
        "".join(
            f"{_digest(content)}  {relative}\n"
            for relative, content in sorted(checksum_files.items())
        ),
        encoding="utf-8",
        newline="\n",
    )
    return bundle_id


def _write_target_facts(path: Path, *, arch: str = "amd64") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        _canonical(
            {
                "schema_version": "0.1.0",
                "profile_id": "test-amd64",
                "platform": {
                    "arch": arch,
                    "os": "ubuntu-24.04",
                    "ros_distribution": "jazzy",
                    "gpu": {"available": False},
                },
                "native_packages": ["cellforge_supervisor"],
                "external_prerequisites": ["test-runtime"],
            }
        )
    )


class MemoryActivation(ActivationStore):
    def __init__(self) -> None:
        self.active: str | None = None
        self.activations: list[str | None] = []

    def current_bundle_id(self) -> str | None:
        return self.active

    def activate(self, bundle_id: str) -> None:
        self.active = bundle_id
        self.activations.append(bundle_id)

    def clear(self) -> None:
        self.active = None
        self.activations.append(None)


class FakeServices(ServiceManager):
    def __init__(self) -> None:
        self.operations: list[tuple[str, str | None]] = []
        self.active = False

    def stop(self, unit: str) -> None:
        self.operations.append(("stop", unit))
        self.active = False

    def start(self, unit: str) -> None:
        self.operations.append(("start", unit))
        self.active = True

    def is_active(self, unit: str) -> bool:
        self.operations.append(("is-active", unit))
        return self.active

    def daemon_reload(self) -> None:
        self.operations.append(("daemon-reload", None))

    def enable(self, unit: str) -> None:
        self.operations.append(("enable", unit))


class ExactHealth:
    def __init__(self) -> None:
        self.failed: set[str] = set()
        self.checked: list[str] = []

    def wait_healthy(self, bundle_id: str, configuration: HealthConfiguration) -> None:
        assert configuration.url.startswith("http://127.0.0.1:")
        self.checked.append(bundle_id)
        if bundle_id in self.failed:
            raise AgentError("agent.health.timeout", "injected health failure")


def _agent(tmp_path: Path) -> tuple[BundleAgent, MemoryActivation, FakeServices, ExactHealth]:
    paths = AgentPaths(
        install_root=tmp_path / "opt",
        state_root=tmp_path / "state",
        secret_store=tmp_path / "secrets",
        target_facts=tmp_path / "target.json",
        trusted_keys=tmp_path / "trusted-keys",
    )
    _write_target_facts(paths.target_facts)
    paths.trusted_keys.mkdir(parents=True)
    (paths.trusted_keys / f"{_TEST_KEY_ID}.pub").write_bytes(_TEST_PUBLIC_KEY)
    activation = MemoryActivation()
    services = FakeServices()
    health = ExactHealth()
    return (
        BundleAgent(paths, activation=activation, services=services, health=health),
        activation,
        services,
        health,
    )


def test_verifies_complete_layout_and_rejects_corrupt_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle_id = _make_bundle(bundle, marker="original")
    assert verify_bundle(bundle).bundle_id == bundle_id

    (bundle / "config" / "cell.yaml").write_text("cell: corrupt\n", encoding="utf-8")
    with pytest.raises(AgentError, match="agent.bundle.checksum_mismatch"):
        verify_bundle(bundle)


def test_rejects_checksum_omission_and_bundled_secret_value(tmp_path: Path) -> None:
    omitted = tmp_path / "omitted"
    _make_bundle(omitted, marker="omitted")
    lines = (omitted / "checksums.txt").read_text(encoding="utf-8").splitlines()
    (omitted / "checksums.txt").write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(AgentError, match="agent.bundle.checksum_inventory"):
        verify_bundle(omitted)

    secret = tmp_path / "secret"
    _make_bundle(
        secret,
        marker="secret",
        extra_files={"config/credentials": b"do-not-bundle"},
    )
    with pytest.raises(AgentError, match="agent.secret.bundled"):
        verify_bundle(secret)


def test_target_mismatch_fails_before_service_or_release_mutation(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _make_bundle(bundle, marker="target")
    agent, activation, services, _ = _agent(tmp_path)
    _write_target_facts(agent.paths.target_facts, arch="arm64")

    with pytest.raises(AgentError, match="agent.target.incompatible"):
        agent.install(bundle)
    assert services.operations == []
    assert activation.active is None
    assert not agent.paths.releases.exists()


def test_health_failure_restores_previous_release_and_trace_identity(tmp_path: Path) -> None:
    first_source = tmp_path / "first"
    second_source = tmp_path / "second"
    first_id = _make_bundle(first_source, marker="first")
    second_id = _make_bundle(second_source, marker="second")
    agent, activation, services, health = _agent(tmp_path)

    first_status = agent.install(first_source)
    assert first_status.active_bundle_id == first_id
    assert (agent.paths.releases / first_id).is_dir()
    if os.name != "nt":
        assert all(
            path.stat().st_mode & 0o222 == 0
            for path in (agent.paths.releases / first_id).rglob("*")
        )
    assert agent.paths.runtime_environment.read_text(encoding="utf-8").find(first_id) >= 0

    health.failed.add(second_id)
    with pytest.raises(AgentError, match="agent.activation.rolled_back"):
        agent.install(second_source)

    assert activation.active == first_id
    assert activation.activations[-2:] == [second_id, first_id]
    assert health.checked[-2:] == [second_id, first_id]
    assert services.active
    assert (agent.paths.releases / second_id).is_dir()
    assert first_id in agent.paths.runtime_environment.read_text(encoding="utf-8")
    events = [json.loads(line) for line in agent.paths.event_journal.read_text().splitlines()]
    assert events[-1]["event_type"] == "deployment.rolled_back"
    assert events[-1]["candidate_bundle_id"] == second_id
    assert events[-1]["active_bundle_id"] == first_id


def test_secrets_resolve_only_to_protected_local_state(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle_id = _make_bundle(bundle, marker="secret-ref", secret_reference=True)
    agent, _, _, _ = _agent(tmp_path)
    secret = agent.paths.secret_store / "laser" / "api-token"
    secret.parent.mkdir(parents=True)
    secret.write_text("local-only-value", encoding="utf-8")

    agent.install(bundle)

    release = agent.paths.releases / bundle_id
    assert all(
        b"local-only-value" not in path.read_bytes()
        for path in release.rglob("*")
        if path.is_file()
    )
    secret_environment = agent.paths.secret_environment.read_text(encoding="utf-8")
    assert 'LASER_API_TOKEN="local-only-value"' in secret_environment
    if os.name != "nt":
        assert agent.paths.secret_environment.stat().st_mode & 0o777 == 0o600


def test_local_rollback_selects_previous_known_good_release(tmp_path: Path) -> None:
    first_source = tmp_path / "first"
    second_source = tmp_path / "second"
    first_id = _make_bundle(first_source, marker="first")
    second_id = _make_bundle(second_source, marker="second")
    agent, activation, _, health = _agent(tmp_path)
    agent.install(first_source)
    agent.install(second_source)

    status = agent.rollback()

    assert status.active_bundle_id == first_id
    assert activation.active == first_id
    assert health.checked[-1] == first_id
    assert set(status.release_ids) == {first_id, second_id}
    assert status.last_result == "rolled-back"


def test_local_rollback_restores_candidate_when_previous_is_unhealthy(tmp_path: Path) -> None:
    first_source = tmp_path / "first"
    second_source = tmp_path / "second"
    first_id = _make_bundle(first_source, marker="first")
    second_id = _make_bundle(second_source, marker="second")
    agent, activation, _, health = _agent(tmp_path)
    agent.install(first_source)
    agent.install(second_source)
    health.failed.add(first_id)

    with pytest.raises(AgentError, match="agent.rollback.failed"):
        agent.rollback()

    assert activation.active == second_id
    assert health.checked[-2:] == [first_id, second_id]


def test_status_cli_reports_no_active_release_without_systemd(tmp_path: Path, capsys: Any) -> None:
    result = main(
        [
            "--install-root",
            str(tmp_path / "opt"),
            "--state-root",
            str(tmp_path / "state"),
            "--secret-store",
            str(tmp_path / "secrets"),
            "--target-facts",
            str(tmp_path / "target.json"),
            "status",
            "--json",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["active_bundle_id"] is None


def test_systemd_templates_install_explicitly_and_enable_target(tmp_path: Path) -> None:
    services = FakeServices()
    installed = install_systemd_units(tmp_path / "units", services)
    assert {path.name for path in installed} == {
        "cellforge-bundle-agent.service",
        "cellforge-runtime.service",
        "cellforge-runtime.target",
    }
    runtime = (tmp_path / "units" / "cellforge-runtime.service").read_text(encoding="utf-8")
    assert "EnvironmentFile=/var/lib/cellforge/runtime.env" in runtime
    assert "ExecStart=/opt/cellforge/current/scripts/start-runtime" in runtime
    assert services.operations[-2:] == [
        ("daemon-reload", None),
        ("enable", "cellforge-runtime.target"),
    ]


def test_loopback_health_requires_exact_bundle_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read(_limit: int = -1) -> bytes:
            return b'{"status":"healthy","bundle_id":"' + b"d" * 64 + b'"}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    LoopbackHealthChecker().wait_healthy(
        "d" * 64,
        HealthConfiguration(
            url="http://127.0.0.1:9080/health", timeout_seconds=1, interval_seconds=0.05
        ),
    )


def test_loopback_health_times_out_on_stale_bundle_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StaleResponse:
        def __enter__(self) -> StaleResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read(_limit: int = -1) -> bytes:
            return b'{"status":"healthy","bundle_id":"stale"}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: StaleResponse())
    with pytest.raises(AgentError, match="agent.health.timeout"):
        LoopbackHealthChecker().wait_healthy(
            "d" * 64,
            HealthConfiguration(
                url="http://127.0.0.1:9080/health",
                timeout_seconds=0.01,
                interval_seconds=0.001,
            ),
        )


@pytest.mark.skipif(os.name == "nt", reason="Windows requires elevated directory-symlink privilege")
def test_real_activation_store_atomically_selects_relative_release(tmp_path: Path) -> None:
    paths = AgentPaths(install_root=tmp_path / "opt", state_root=tmp_path / "state")
    bundle_id = "a" * 64
    (paths.releases / bundle_id).mkdir(parents=True)
    activation = AtomicSymlinkStore(paths)
    activation.activate(bundle_id)
    assert paths.current.is_symlink()
    assert os.readlink(paths.current) == f"releases/{bundle_id}"
    assert activation.current_bundle_id() == bundle_id


def test_preflight_rejects_missing_external_prerequisite(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _make_bundle(bundle, marker="prerequisite")
    facts = tmp_path / "target.json"
    _write_target_facts(facts)
    document = json.loads(facts.read_bytes())
    document["external_prerequisites"] = []
    facts.write_bytes(_canonical(document))
    with pytest.raises(AgentError, match="agent.target.prerequisites_missing"):
        preflight_target(verify_bundle(bundle), facts)
