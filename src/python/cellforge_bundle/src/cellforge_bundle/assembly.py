"""Deterministic materialization and Ed25519 signing of compiler bundle manifests."""

from __future__ import annotations

import base64
import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path

from cellforge_domain import ExecutionMode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cellforge_bundle.compiler import compile_project

_SIGNATURE_CONTEXT = b"cellforge-bundle-v1\0"


class AssemblyError(Exception):
    """A stable, sanitized failure while assembling an immutable release directory."""


@dataclass(frozen=True, slots=True)
class AssemblyResult:
    """The immutable release directory emitted by one successful assembly."""

    bundle_id: str
    output: Path
    key_id: str


def signature_payload(bundle_id: str, files: dict[str, bytes]) -> bytes:
    """Return the domain-separated identity and complete signed release inventory payload."""

    lines = [
        f"{hashlib.sha256(content).hexdigest()}  {relative}\n".encode("ascii")
        for relative, content in sorted(files.items())
    ]
    return _SIGNATURE_CONTEXT + bundle_id.encode("ascii") + b"\n" + b"".join(lines)


def assemble_bundle(
    project: str | Path,
    schemas: str | Path,
    *,
    target_profile: str,
    mode: ExecutionMode,
    source_revision: str,
    output: str | Path,
    signing_key: str | Path,
) -> AssemblyResult:
    """Compile, materialize, checksum, and sign a complete installable release directory."""

    report = compile_project(
        project,
        schemas,
        target_profile=target_profile,
        mode=mode,
        source_revision=source_revision,
    )
    if not report.valid or report.manifest is None or report.manifest_json is None:
        raise AssemblyError("Bundle compilation did not produce a valid immutable manifest.")
    destination = Path(output).resolve()
    if destination.exists():
        raise AssemblyError("Bundle output already exists.")
    private_key, key_id = _load_private_key(Path(signing_key))
    source_root = Path(project).resolve()
    schema_root = Path(schemas).resolve()
    try:
        destination.mkdir(parents=True)
        sources = _source_files((source_root, schema_root))
        for item in report.manifest.files:
            content = _resolve_source(item.path, item.sha256, item.size, sources)
            _write(destination / item.path, content)
        _write(destination / "manifest.json", report.manifest_json.encode("utf-8") + b"\n")
        _write(destination / "config/agent.json", _canonical(_agent_config()))
        _write(destination / "config/launch.json", _canonical(_launch_config()))
        _write(
            destination / "evidence-summary.json", _canonical(_evidence_summary(report.manifest))
        )
        _write(destination / "scripts/start-runtime", _runtime_launcher(), executable=True)
        signature = private_key.sign(
            signature_payload(report.manifest.bundle_id, _signature_inventory(destination))
        )
        _write(
            destination / "signature.json",
            _canonical(
                {
                    "algorithm": "Ed25519",
                    "bundle_id": report.manifest.bundle_id,
                    "key_id": key_id,
                    "schema_version": "0.1.0",
                    "signature": base64.b64encode(signature).decode("ascii"),
                }
            ),
        )
        _write_checksums(destination)
    except Exception:
        if destination.exists():
            _remove_tree(destination)
        raise
    return AssemblyResult(bundle_id=report.manifest.bundle_id, output=destination, key_id=key_id)


def _load_private_key(path: Path) -> tuple[Ed25519PrivateKey, str]:
    try:
        candidate = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, TypeError, ValueError):
        raise AssemblyError(
            "Signing key is unreadable or is not an unencrypted PEM private key."
        ) from None
    if not isinstance(candidate, Ed25519PrivateKey):
        raise AssemblyError("Signing key must be an Ed25519 private key.")
    public = candidate.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return candidate, hashlib.sha256(public).hexdigest()


def _source_files(roots: tuple[Path, ...]) -> dict[tuple[str, int], list[bytes]]:
    sources: dict[tuple[str, int], list[bytes]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                content = path.read_bytes()
            except OSError:
                continue
            sources.setdefault((hashlib.sha256(content).hexdigest(), len(content)), []).append(
                content
            )
    return sources


def _resolve_source(
    path: str, digest: str, size: int, sources: dict[tuple[str, int], list[bytes]]
) -> bytes:
    matches = sources.get((digest, size), [])
    if not matches:
        raise AssemblyError(f"Compiler input for '{path}' no longer matches its manifest digest.")
    return matches[0]


def _agent_config() -> dict[str, object]:
    return {
        "health": {
            "interval_seconds": 1,
            "timeout_seconds": 30,
            "url": "http://127.0.0.1:9080/health",
        },
        "schema_version": "0.1.0",
        "systemd_unit": "cellforge-runtime.target",
    }


def _launch_config() -> dict[str, object]:
    return {
        "launch_file": "integrated_runtime.launch.py",
        "package": "cellforge_bringup",
        "schema_version": "0.1.0",
    }


def _evidence_summary(manifest: object) -> dict[str, object]:
    evidence = getattr(manifest, "evidence")
    return {
        "evidence": evidence.model_dump(mode="json"),
        "schema_version": "0.1.0",
        "source_revision": getattr(manifest, "source_revision"),
    }


def _runtime_launcher() -> bytes:
    return (
        b"#!/bin/sh\n"
        b"set -eu\n"
        b': "${CELLFORGE_BUNDLE_ROOT:?CELLFORGE_BUNDLE_ROOT is required}"\n'
        b"exec ros2 launch cellforge_bringup integrated_runtime.launch.py\n"
    )


def _canonical(document: object) -> bytes:
    return (
        json.dumps(
            document, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        + b"\n"
    )


def _write(destination: Path, content: bytes, *, executable: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    if executable:
        destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_checksums(root: Path) -> None:
    lines = []
    for path in sorted(
        item for item in root.rglob("*") if item.is_file() and item.name != "checksums.txt"
    ):
        relative = path.relative_to(root).as_posix()
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}\n")
    _write(root / "checksums.txt", "".join(lines).encode("ascii"))


def _signature_inventory(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in {"checksums.txt", "signature.json"}
    }


def _remove_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
        else:
            path.rmdir()
    root.rmdir()
