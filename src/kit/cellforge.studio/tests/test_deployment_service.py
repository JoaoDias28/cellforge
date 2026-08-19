"""Unit and contract tests for DeploymentService."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cellforge_bundle.agent import AgentPaths
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cellforge.studio.application import ProjectContents
from cellforge.studio.deployment_service import (
    DeploymentService,
)

ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = ROOT / "schemas"
PEN_PROJECT = ROOT / "examples" / "pen_engraving"


@pytest.fixture
def pen_contents() -> ProjectContents:
    cell_yaml = (PEN_PROJECT / "cell.yaml").read_text(encoding="utf-8")
    scene_usda = (PEN_PROJECT / "scene.usda").read_text(encoding="utf-8")
    return ProjectContents(cell_yaml=cell_yaml, scene_usda=scene_usda)


@pytest.fixture
def deployment_service() -> DeploymentService:
    return DeploymentService(SCHEMAS)


@pytest.fixture
def signing_key_pair(tmp_path: Path) -> tuple[Path, Path, str]:
    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = tmp_path / "signing.pem"
    key_file.write_bytes(pem)

    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = hashlib.sha256(public_bytes).hexdigest()
    trusted_dir = tmp_path / "trusted-keys"
    trusted_dir.mkdir(parents=True, exist_ok=True)
    pub_file = trusted_dir / f"{key_id}.pub"
    pub_file.write_bytes(public_bytes)

    return key_file, trusted_dir, key_id


def test_browse_deployment_profiles(
    deployment_service: DeploymentService, pen_contents: ProjectContents
) -> None:
    result = deployment_service.browse_deployment_profiles(PEN_PROJECT, pen_contents)

    assert len(result.profiles) == 3
    ids = {p.id for p in result.profiles}
    assert "pen-sim-amd64" in ids
    assert "pen-isaac-l2-win64" in ids
    assert "pen-hardware-cell" in ids


def test_inspect_deployment_profile(
    deployment_service: DeploymentService, pen_contents: ProjectContents
) -> None:
    detail = deployment_service.inspect_deployment_profile(
        PEN_PROJECT, pen_contents, profile_id_or_path="deployment-sim"
    )

    assert detail is not None
    assert detail.summary.id == "pen-sim-amd64"
    assert detail.summary.target_profile == "pen-sim-amd64"
    assert detail.summary.execution_mode == "simulation"
    assert detail.summary.simulation_fidelity == "L0"


def test_assemble_and_verify_signed_bundle(
    deployment_service: DeploymentService,
    signing_key_pair: tuple[Path, Path, str],
    tmp_path: Path,
) -> None:
    key_path, trusted_dir, expected_key_id = signing_key_pair
    output_dir = tmp_path / "test_bundle_release"

    # Assemble bundle
    result = deployment_service.assemble_bundle_release(
        project_path=PEN_PROJECT,
        schemas_path=SCHEMAS,
        target_profile="pen-sim-amd64",
        mode="simulation",
        source_revision="0123456789abcdef0123456789abcdef01234567",
        output_dir=output_dir,
        signing_key_path=key_path,
    )

    assert result.success is True
    assert len(result.bundle_id) == 64
    assert result.key_id == expected_key_id
    assert output_dir.is_dir()
    assert (output_dir / "manifest.json").is_file()
    assert (output_dir / "signature.json").is_file()
    assert (output_dir / "checksums.txt").is_file()

    # Verify signature
    sig_result = deployment_service.verify_bundle_signature(output_dir, trusted_dir)
    assert sig_result.valid is True
    assert sig_result.key_id == expected_key_id
    assert sig_result.algorithm == "Ed25519"
    assert sig_result.error_code is None


def test_signature_verification_detects_tampered_bundle(
    deployment_service: DeploymentService,
    signing_key_pair: tuple[Path, Path, str],
    tmp_path: Path,
) -> None:
    key_path, trusted_dir, _ = signing_key_pair
    output_dir = tmp_path / "tampered_bundle"

    result = deployment_service.assemble_bundle_release(
        project_path=PEN_PROJECT,
        schemas_path=SCHEMAS,
        target_profile="pen-sim-amd64",
        mode="simulation",
        source_revision="0123456789abcdef0123456789abcdef01234567",
        output_dir=output_dir,
        signing_key_path=key_path,
    )
    assert result.success is True

    # Tamper with a config file
    cell_config = output_dir / "config" / "cell.yaml"
    if cell_config.is_file():
        cell_config.write_text("tampered: true\n", encoding="utf-8")

    sig_result = deployment_service.verify_bundle_signature(output_dir, trusted_dir)
    assert sig_result.valid is False


def test_deterministic_bundle_diff(
    deployment_service: DeploymentService,
    signing_key_pair: tuple[Path, Path, str],
    tmp_path: Path,
) -> None:
    key_path, _, _ = signing_key_pair
    bundle_a = tmp_path / "bundle_a"
    bundle_b = tmp_path / "bundle_b"

    # Assemble bundle A
    res_a = deployment_service.assemble_bundle_release(
        project_path=PEN_PROJECT,
        schemas_path=SCHEMAS,
        target_profile="pen-sim-amd64",
        mode="simulation",
        source_revision="0123456789abcdef0123456789abcdef01234567",
        output_dir=bundle_a,
        signing_key_path=key_path,
    )
    assert res_a.success is True

    # Assemble bundle B with different revision
    res_b = deployment_service.assemble_bundle_release(
        project_path=PEN_PROJECT,
        schemas_path=SCHEMAS,
        target_profile="pen-sim-amd64",
        mode="simulation",
        source_revision="fedcba9876543210fedcba9876543210fedcba98",
        output_dir=bundle_b,
        signing_key_path=key_path,
    )
    assert res_b.success is True

    diff_result = deployment_service.diff_bundles(bundle_a, bundle_b)
    assert diff_result.is_compatible is True
    # Should detect modified source revision in manifest
    manifest_diffs = [d for d in diff_result.differences if d.category == "manifest"]
    assert any(d.key == "source_revision" for d in manifest_diffs)


def test_target_compatibility_preflight(
    deployment_service: DeploymentService,
    signing_key_pair: tuple[Path, Path, str],
    tmp_path: Path,
) -> None:
    key_path, _, _ = signing_key_pair
    bundle_dir = tmp_path / "compat_bundle"

    res = deployment_service.assemble_bundle_release(
        project_path=PEN_PROJECT,
        schemas_path=SCHEMAS,
        target_profile="pen-sim-amd64",
        mode="simulation",
        source_revision="0123456789abcdef0123456789abcdef01234567",
        output_dir=bundle_dir,
        signing_key_path=key_path,
    )
    assert res.success is True

    # Valid target facts matching pen-sim-amd64
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
    facts_file = tmp_path / "target.json"
    facts_file.write_text(json.dumps(target_facts, indent=2), encoding="utf-8")

    compat = deployment_service.preflight_target_compatibility(bundle_dir, facts_file)
    assert compat.compatible is True
    assert len(compat.missing_packages) == 0

    # Incompatible facts missing package
    target_facts_missing = dict(target_facts)
    target_facts_missing["native_packages"] = []
    facts_missing_file = tmp_path / "target_missing.json"
    facts_missing_file.write_text(json.dumps(target_facts_missing, indent=2), encoding="utf-8")

    compat_missing = deployment_service.preflight_target_compatibility(
        bundle_dir, facts_missing_file
    )
    assert compat_missing.compatible is False
    assert len(compat_missing.missing_packages) > 0


def test_agent_status_query(deployment_service: DeploymentService, tmp_path: Path) -> None:
    agent_paths = AgentPaths(
        install_root=tmp_path / "opt_cellforge",
        state_root=tmp_path / "var_lib_cellforge",
    )

    # Empty agent
    status = deployment_service.get_agent_status(agent_paths)
    assert status.state == "no_release"
    assert status.active_bundle_id is None

    # Write state file
    agent_paths.state_root.mkdir(parents=True, exist_ok=True)
    agent_paths.state_file.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "result": "healthy",
                "active_bundle_id": "bundle-001-active",
            }
        ),
        encoding="utf-8",
    )

    status2 = deployment_service.get_agent_status(agent_paths)
    assert status2.state == "healthy"
    assert status2.active_bundle_id == "bundle-001-active"
