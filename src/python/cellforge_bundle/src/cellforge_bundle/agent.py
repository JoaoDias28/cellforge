"""Fail-closed installation and activation of immutable CellForge bundles."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from cellforge_bundle.assembly import signature_payload

JsonObject = dict[str, Any]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHECKSUM = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")
_SYSTEMD_UNIT = re.compile(r"^[A-Za-z0-9_.@-]+\.target$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_SECRET_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-/]*$")
_SENSITIVE_KEYS = (
    "api_key",
    "client_secret",
    "credential",
    "password",
    "passwd",
    "private_key",
    "token",
)
_PRIVATE_KEY_MARKER = b"-----BEGIN PRIVATE KEY-----"
_ASSEMBLY_DERIVED_FILES = {
    "config/agent.json",
    "config/launch.json",
    "evidence-summary.json",
    "scripts/start-runtime",
    "signature.json",
}


class AgentError(Exception):
    """A stable, sanitized bundle-agent failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class AgentPaths:
    """Cell-local paths; defaults match the production filesystem contract."""

    install_root: Path = Path("/opt/cellforge")
    state_root: Path = Path("/var/lib/cellforge")
    secret_store: Path = Path("/etc/cellforge/secrets")
    target_facts: Path = Path("/etc/cellforge/target.json")
    trusted_keys: Path = Path("/etc/cellforge/trusted-keys")

    @property
    def releases(self) -> Path:
        return self.install_root / "releases"

    @property
    def current(self) -> Path:
        return self.install_root / "current"

    @property
    def runtime_environment(self) -> Path:
        return self.state_root / "runtime.env"

    @property
    def secret_environment(self) -> Path:
        return self.state_root / "secrets.env"

    @property
    def state_file(self) -> Path:
        return self.state_root / "agent-state.json"

    @property
    def event_journal(self) -> Path:
        return self.state_root / "deployment-events.jsonl"

    @property
    def lock_file(self) -> Path:
        return self.state_root / "agent.lock"


@dataclass(frozen=True, slots=True)
class HealthConfiguration:
    url: str
    timeout_seconds: float
    interval_seconds: float


@dataclass(frozen=True, slots=True)
class VerifiedBundle:
    root: Path
    bundle_id: str
    manifest: JsonObject
    target_profile: JsonObject
    systemd_unit: str
    health: HealthConfiguration
    secret_references: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AgentStatus:
    active_bundle_id: str | None
    release_ids: tuple[str, ...]
    service_unit: str | None
    service_active: bool
    last_result: str | None
    last_error: str | None

    def to_document(self) -> JsonObject:
        return asdict(self)


class ActivationStore(Protocol):
    def current_bundle_id(self) -> str | None: ...

    def activate(self, bundle_id: str) -> None: ...

    def clear(self) -> None: ...


class ServiceManager(Protocol):
    def stop(self, unit: str) -> None: ...

    def start(self, unit: str) -> None: ...

    def is_active(self, unit: str) -> bool: ...

    def daemon_reload(self) -> None: ...

    def enable(self, unit: str) -> None: ...


class HealthChecker(Protocol):
    def wait_healthy(self, bundle_id: str, configuration: HealthConfiguration) -> None: ...


class AtomicSymlinkStore:
    """Select releases with a same-directory atomic symlink replacement."""

    def __init__(self, paths: AgentPaths) -> None:
        self._paths = paths

    def current_bundle_id(self) -> str | None:
        current = self._paths.current
        if not current.is_symlink():
            return None
        try:
            target = Path(os.readlink(current))
        except OSError:
            return None
        bundle_id = target.name
        if _SHA256.fullmatch(bundle_id) is None:
            return None
        expected = self._paths.releases / bundle_id
        try:
            if current.resolve(strict=True) != expected.resolve(strict=True):
                return None
        except OSError:
            return None
        return bundle_id

    def activate(self, bundle_id: str) -> None:
        if _SHA256.fullmatch(bundle_id) is None:
            raise AgentError("agent.activation.invalid_id", "Bundle ID is invalid.")
        release = self._paths.releases / bundle_id
        if not release.is_dir():
            raise AgentError("agent.activation.release_missing", "Release directory is missing.")
        self._paths.install_root.mkdir(parents=True, exist_ok=True)
        temporary = self._paths.install_root / f".current-{os.getpid()}-{time.time_ns()}"
        try:
            temporary.symlink_to(Path("releases") / bundle_id, target_is_directory=True)
            os.replace(temporary, self._paths.current)
            _fsync_directory(self._paths.install_root)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise AgentError(
                "agent.activation.link_failed", "Could not atomically select the release."
            ) from None

    def clear(self) -> None:
        try:
            self._paths.current.unlink(missing_ok=True)
            _fsync_directory(self._paths.install_root)
        except OSError:
            raise AgentError(
                "agent.activation.clear_failed", "Could not clear active release."
            ) from None


class SystemdServiceManager:
    """Fixed-argument systemd integration without shell execution."""

    def _run(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["systemctl", *arguments],
                check=check,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            raise AgentError("agent.systemd.failed", "systemd operation failed.") from None

    def stop(self, unit: str) -> None:
        self._run("stop", unit)

    def start(self, unit: str) -> None:
        self._run("start", unit)

    def is_active(self, unit: str) -> bool:
        return self._run("is-active", "--quiet", unit, check=False).returncode == 0

    def daemon_reload(self) -> None:
        self._run("daemon-reload")

    def enable(self, unit: str) -> None:
        self._run("enable", unit)


class LoopbackHealthChecker:
    """Wait for an exact-bundle response from a local runtime endpoint."""

    def wait_healthy(self, bundle_id: str, configuration: HealthConfiguration) -> None:
        deadline = time.monotonic() + configuration.timeout_seconds
        while True:
            try:
                request = urllib.request.Request(configuration.url, method="GET")
                remaining = max(0.1, deadline - time.monotonic())
                with urllib.request.urlopen(  # noqa: S310
                    request, timeout=min(2.0, remaining)
                ) as response:
                    raw = response.read(65_537)
                document: object = json.loads(raw) if len(raw) <= 65_536 else None
                if (
                    isinstance(document, dict)
                    and document.get("status") == "healthy"
                    and document.get("bundle_id") == bundle_id
                ):
                    return
            except (OSError, ValueError, urllib.error.URLError):
                pass
            if time.monotonic() >= deadline:
                raise AgentError(
                    "agent.health.timeout",
                    "Runtime did not report healthy for the exact active bundle.",
                )
            time.sleep(configuration.interval_seconds)


def verify_bundle(
    bundle_root: str | Path,
    *,
    trusted_keys: str | Path | None = None,
    require_signature: bool = False,
) -> VerifiedBundle:
    """Validate bundle layout, content address, inventory, and secret boundary."""

    root = Path(bundle_root).resolve()
    if not root.is_dir():
        raise AgentError("agent.bundle.not_found", "Bundle directory does not exist.")
    regular_files = _regular_bundle_files(root)
    required = {
        "checksums.txt",
        "config/agent.json",
        "config/target-profile.yaml",
        "manifest.json",
        "scripts/start-runtime",
    }
    missing = sorted(required - regular_files.keys())
    if missing:
        raise AgentError("agent.bundle.layout_invalid", "Bundle is missing required files.")
    if os.name != "nt" and not (root / "scripts" / "start-runtime").stat().st_mode & 0o111:
        raise AgentError(
            "agent.bundle.runtime_not_executable", "Runtime start entrypoint is not executable."
        )

    manifest = _read_json(root / "manifest.json", "agent.bundle.manifest_invalid")
    if manifest.get("schema_version") != "0.1.0":
        raise AgentError("agent.bundle.manifest_invalid", "Manifest version is unsupported.")
    manifest_bytes = regular_files["manifest.json"]
    canonical_manifest = _canonical_bytes(manifest)
    if manifest_bytes not in {canonical_manifest, canonical_manifest + b"\n"}:
        raise AgentError("agent.bundle.manifest_noncanonical", "Manifest JSON is not canonical.")
    bundle_id = manifest.get("bundle_id")
    if not isinstance(bundle_id, str) or _SHA256.fullmatch(bundle_id) is None:
        raise AgentError("agent.bundle.manifest_invalid", "Manifest bundle ID is invalid.")
    hash_input = dict(manifest)
    del hash_input["bundle_id"]
    if _sha256(_canonical_bytes(hash_input)) != bundle_id:
        raise AgentError(
            "agent.bundle.id_mismatch", "Manifest content does not match its bundle ID."
        )

    checksums = _read_checksums(root / "checksums.txt")
    expected_checksum_paths = set(regular_files) - {"checksums.txt"}
    if set(checksums) != expected_checksum_paths:
        raise AgentError(
            "agent.bundle.checksum_inventory",
            "Checksum inventory must cover every regular bundle file exactly once.",
        )
    for relative, digest in checksums.items():
        if _sha256(regular_files[relative]) != digest:
            raise AgentError(
                "agent.bundle.checksum_mismatch", f"Checksum mismatch for '{relative}'."
            )

    inventory = manifest.get("files")
    if not isinstance(inventory, list):
        raise AgentError("agent.bundle.manifest_invalid", "Manifest file inventory is invalid.")
    seen: set[str] = set()
    for entry in inventory:
        if not isinstance(entry, dict):
            raise AgentError("agent.bundle.manifest_invalid", "Manifest file entry is invalid.")
        relative = _normalized_path(entry.get("path"))
        inventory_digest = entry.get("sha256")
        size = entry.get("size")
        if (
            relative in seen
            or relative not in regular_files
            or not isinstance(inventory_digest, str)
            or _SHA256.fullmatch(inventory_digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise AgentError(
                "agent.bundle.manifest_inventory", "Manifest file inventory is inconsistent."
            )
        seen.add(relative)
        content = regular_files[relative]
        if len(content) != size or _sha256(content) != inventory_digest:
            raise AgentError(
                "agent.bundle.manifest_file_mismatch",
                f"Manifest digest or size mismatch for '{relative}'.",
            )
    derived_files = _ASSEMBLY_DERIVED_FILES if "signature.json" in regular_files else set()
    required_manifest_paths = (
        set(regular_files) - {"checksums.txt", "manifest.json"} - derived_files
    )
    if not required_manifest_paths <= seen:
        raise AgentError(
            "agent.bundle.manifest_inventory",
            "Manifest inventory must bind every bundle content file.",
        )

    _reject_bundled_secrets(regular_files)
    _verify_signature(
        regular_files,
        bundle_id,
        Path(trusted_keys) if trusted_keys is not None else None,
        require_signature=require_signature,
    )
    target_profile = _read_yaml(root / "config" / "target-profile.yaml")
    agent_config = _read_json(root / "config" / "agent.json", "agent.bundle.config_invalid")
    systemd_unit, health = _agent_configuration(agent_config)
    secret_references = _secret_references(root, regular_files)
    return VerifiedBundle(
        root=root,
        bundle_id=bundle_id,
        manifest=manifest,
        target_profile=target_profile,
        systemd_unit=systemd_unit,
        health=health,
        secret_references=secret_references,
    )


def _verify_signature(
    regular_files: Mapping[str, bytes],
    bundle_id: str,
    trusted_keys: Path | None,
    *,
    require_signature: bool,
) -> None:
    raw = regular_files.get("signature.json")
    if raw is None:
        if require_signature:
            raise AgentError("agent.signature.missing", "Bundle signature is required.")
        return
    if trusted_keys is None:
        if not require_signature:
            return
        raise AgentError(
            "agent.signature.trust_unavailable", "Trusted public keys are unavailable."
        )
    try:
        document: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        document = None
    if not isinstance(document, dict) or set(document) != {
        "algorithm",
        "bundle_id",
        "key_id",
        "schema_version",
        "signature",
    }:
        raise AgentError("agent.signature.invalid", "Bundle signature document is invalid.")
    key_id = document.get("key_id")
    encoded = document.get("signature")
    if (
        document.get("schema_version") != "0.1.0"
        or document.get("algorithm") != "Ed25519"
        or document.get("bundle_id") != bundle_id
        or not isinstance(key_id, str)
        or _SHA256.fullmatch(key_id) is None
        or not isinstance(encoded, str)
    ):
        raise AgentError("agent.signature.invalid", "Bundle signature metadata is invalid.")
    try:
        signature = base64.b64decode(encoded, validate=True)
        public = (trusted_keys / f"{key_id}.pub").read_bytes()
        verifier = Ed25519PublicKey.from_public_bytes(public)
        signed_files = {
            relative: content
            for relative, content in regular_files.items()
            if relative not in {"checksums.txt", "signature.json"}
        }
        verifier.verify(signature, signature_payload(bundle_id, signed_files))
    except (OSError, ValueError, InvalidSignature):
        raise AgentError(
            "agent.signature.invalid", "Bundle signature is not trusted or is invalid."
        ) from None


def preflight_target(bundle: VerifiedBundle, target_facts_path: str | Path) -> None:
    """Fail before activation unless locally asserted target facts satisfy the bundle."""

    facts = _read_json(Path(target_facts_path), "agent.target.facts_invalid")
    if facts.get("schema_version") != "0.1.0":
        raise AgentError("agent.target.facts_invalid", "Target facts version is unsupported.")
    profile = bundle.target_profile
    if profile.get("schema_version") != "0.1.0":
        raise AgentError("agent.target.profile_invalid", "Target profile version is unsupported.")
    identity = profile.get("profile")
    platform = profile.get("platform")
    facts_platform = facts.get("platform")
    if not isinstance(identity, dict) or not isinstance(platform, dict):
        raise AgentError("agent.target.profile_invalid", "Target profile structure is invalid.")
    if not isinstance(facts_platform, dict):
        raise AgentError("agent.target.facts_invalid", "Target platform facts are invalid.")
    comparisons = {
        "profile ID": (identity.get("id"), facts.get("profile_id")),
        "architecture": (platform.get("arch"), facts_platform.get("arch")),
        "operating system": (platform.get("os"), facts_platform.get("os")),
        "ROS distribution": (
            platform.get("ros_distribution"),
            facts_platform.get("ros_distribution"),
        ),
    }
    for label, (required, actual) in comparisons.items():
        if not isinstance(required, str) or required != actual:
            raise AgentError(
                "agent.target.incompatible", f"Target {label} does not match the bundle."
            )
    if bundle.manifest.get("target_profile") != identity.get("id"):
        raise AgentError(
            "agent.target.profile_mismatch", "Manifest and bundled target profile do not match."
        )
    modes = profile.get("modes")
    if not isinstance(modes, list) or bundle.manifest.get("execution_mode") not in modes:
        raise AgentError(
            "agent.target.mode_incompatible", "Bundle execution mode is not allowed by the target."
        )

    gpu = platform.get("gpu", {})
    facts_gpu = facts_platform.get("gpu", {})
    if isinstance(gpu, dict) and gpu.get("required") is True:
        if not isinstance(facts_gpu, dict) or facts_gpu.get("available") is not True:
            raise AgentError("agent.target.gpu_missing", "Required target GPU is unavailable.")
        vendor = gpu.get("vendor")
        if isinstance(vendor, str) and facts_gpu.get("vendor") != vendor:
            raise AgentError("agent.target.gpu_mismatch", "Target GPU vendor is incompatible.")

    available_packages = _string_set(facts.get("native_packages"), "target native packages")
    required_packages = _string_set(bundle.manifest.get("native_packages"), "bundle packages")
    if not required_packages <= available_packages:
        raise AgentError(
            "agent.target.packages_missing", "Required native runtime packages are unavailable."
        )
    available_prerequisites = _string_set(
        facts.get("external_prerequisites"), "target external prerequisites"
    )
    required_prerequisites = _string_set(
        bundle.manifest.get("external_prerequisites"), "bundle external prerequisites"
    )
    if not required_prerequisites <= available_prerequisites:
        raise AgentError(
            "agent.target.prerequisites_missing", "Required external prerequisites are unavailable."
        )
    _preflight_runtime_entrypoints(bundle.manifest, facts)


def _preflight_runtime_entrypoints(manifest: JsonObject, facts: JsonObject) -> None:
    """Require locally asserted executable availability for every frozen runtime role."""

    runtime = manifest.get("runtime")
    if runtime is None:
        return
    if not isinstance(runtime, dict) or not isinstance(runtime.get("executables"), dict):
        raise AgentError(
            "agent.bundle.entrypoints_invalid",
            "Bundle runtime executable declarations are invalid.",
        )
    configured = runtime["executables"]
    expected: set[str] = set()
    for value in configured.values():
        if not isinstance(value, dict):
            raise AgentError(
                "agent.bundle.entrypoints_invalid",
                "Bundle runtime executable declarations are invalid.",
            )
        package = value.get("package")
        executable = value.get("executable")
        if not isinstance(package, str) or not isinstance(executable, str):
            raise AgentError(
                "agent.bundle.entrypoints_invalid",
                "Bundle runtime executable declarations are invalid.",
            )
        expected.add(f"{package}:{executable}")
    available = _string_set(facts.get("runtime_entrypoints"), "target runtime entrypoints")
    if not expected <= available:
        raise AgentError(
            "agent.target.entrypoints_missing", "Required runtime entrypoints are unavailable."
        )


class BundleAgent:
    """Install, activate, verify, roll back, and report local bundle state."""

    def __init__(
        self,
        paths: AgentPaths | None = None,
        *,
        activation: ActivationStore | None = None,
        services: ServiceManager | None = None,
        health: HealthChecker | None = None,
    ) -> None:
        self.paths = paths or AgentPaths()
        self.activation = activation or AtomicSymlinkStore(self.paths)
        self.services = services or SystemdServiceManager()
        self.health = health or LoopbackHealthChecker()

    def install(self, bundle_root: str | Path) -> AgentStatus:
        with _exclusive_lock(self.paths.lock_file):
            return self._install(bundle_root)

    def _install(self, bundle_root: str | Path) -> AgentStatus:
        candidate = self._verify_signed_bundle(bundle_root)
        preflight_target(candidate, self.paths.target_facts)
        release = self._install_release(candidate)
        candidate = self._verify_signed_bundle(release)
        previous_id = self.activation.current_bundle_id()
        previous = self._verified_release(previous_id) if previous_id else None
        stopped_unit = previous.systemd_unit if previous is not None else candidate.systemd_unit

        self._prepare_environment(candidate)
        self.services.stop(stopped_unit)
        try:
            self.activation.activate(candidate.bundle_id)
            self.services.daemon_reload()
            self.services.start(candidate.systemd_unit)
            self.health.wait_healthy(candidate.bundle_id, candidate.health)
        except Exception as error:
            self._rollback_failed_activation(candidate, previous, error)
            if isinstance(error, AgentError):
                detail = error.message
            else:
                detail = "Runtime activation failed."
            raise AgentError(
                "agent.activation.rolled_back",
                f"Candidate activation failed and the previous release was restored: {detail}",
            ) from None

        try:
            self._record_event(
                "deployment.activated",
                candidate_bundle_id=candidate.bundle_id,
                active_bundle_id=candidate.bundle_id,
                previous_bundle_id=previous_id,
            )
            self._write_state("activated", active_bundle_id=candidate.bundle_id, error=None)
        except AgentError as error:
            self._rollback_failed_activation(candidate, previous, error)
            raise AgentError(
                "agent.activation.rolled_back",
                "Candidate activation could not be recorded and the previous release was restored.",
            ) from None
        return self.status()

    def prepare_active(self) -> AgentStatus:
        """Idempotently project the current link into boot environment.

        This deliberately does not take the mutation lock: systemd invokes it while a manual
        install holds that lock and waits for the target to start. The current link is already the
        atomic serialization point, and target ordering runs this guard before the runtime.
        """
        active_id = self.activation.current_bundle_id()
        if active_id is None:
            raise AgentError("agent.active.missing", "No valid active bundle is selected.")
        active = self._verified_release(active_id)
        preflight_target(active, self.paths.target_facts)
        self._prepare_environment(active)
        return self.status()

    def rollback(self) -> AgentStatus:
        with _exclusive_lock(self.paths.lock_file):
            return self._rollback()

    def _rollback(self) -> AgentStatus:
        state = self._read_state()
        previous_id = state.get("previous_bundle_id")
        active_id = self.activation.current_bundle_id()
        if not isinstance(previous_id, str) or previous_id == active_id:
            raise AgentError("agent.rollback.unavailable", "No previous release is available.")
        previous = self._verified_release(previous_id)
        preflight_target(previous, self.paths.target_facts)
        active = self._verified_release(active_id) if active_id else None
        self.services.stop(active.systemd_unit if active else previous.systemd_unit)
        try:
            self._prepare_environment(previous)
            self.activation.activate(previous.bundle_id)
            self.services.daemon_reload()
            self.services.start(previous.systemd_unit)
            self.health.wait_healthy(previous.bundle_id, previous.health)
        except Exception:
            try:
                self.services.stop(previous.systemd_unit)
            except AgentError:
                pass
            if active is not None:
                self._prepare_environment(active)
                self.activation.activate(active.bundle_id)
                self.services.daemon_reload()
                self.services.start(active.systemd_unit)
                self.health.wait_healthy(active.bundle_id, active.health)
            raise AgentError(
                "agent.rollback.failed", "Previous release was unhealthy; active release restored."
            ) from None
        self._record_event(
            "deployment.rolled_back",
            candidate_bundle_id=active_id,
            active_bundle_id=previous.bundle_id,
            previous_bundle_id=active_id,
        )
        self._write_state("rolled-back", active_bundle_id=previous.bundle_id, error=None)
        return self.status()

    def status(self) -> AgentStatus:
        active_id = self.activation.current_bundle_id()
        releases = (
            tuple(
                sorted(
                    path.name
                    for path in self.paths.releases.glob("*")
                    if path.is_dir() and _SHA256.fullmatch(path.name) is not None
                )
            )
            if self.paths.releases.is_dir()
            else ()
        )
        unit: str | None = None
        service_active = False
        if active_id is not None:
            try:
                unit = self._verified_release(active_id).systemd_unit
                service_active = self.services.is_active(unit)
            except AgentError:
                service_active = False
        state = self._read_state()
        return AgentStatus(
            active_bundle_id=active_id,
            release_ids=releases,
            service_unit=unit,
            service_active=service_active,
            last_result=state.get("last_result")
            if isinstance(state.get("last_result"), str)
            else None,
            last_error=state.get("last_error")
            if isinstance(state.get("last_error"), str)
            else None,
        )

    def _install_release(self, bundle: VerifiedBundle) -> Path:
        self.paths.releases.mkdir(parents=True, exist_ok=True)
        destination = self.paths.releases / bundle.bundle_id
        if destination.exists():
            existing = self._verify_signed_bundle(destination)
            if existing.bundle_id != bundle.bundle_id:
                raise AgentError("agent.release.conflict", "Existing release is inconsistent.")
            _make_release_read_only(destination)
            return destination
        staging = self.paths.releases / f".staging-{bundle.bundle_id}-{time.time_ns()}"
        try:
            shutil.copytree(bundle.root, staging, symlinks=False)
            staged = self._verify_signed_bundle(staging)
            if staged.bundle_id != bundle.bundle_id:
                raise AgentError(
                    "agent.release.copy_mismatch", "Staged release changed during copy."
                )
            os.replace(staging, destination)
            _fsync_directory(self.paths.releases)
            _make_release_read_only(destination)
        except AgentError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        except OSError:
            shutil.rmtree(staging, ignore_errors=True)
            raise AgentError(
                "agent.release.install_failed", "Could not install staged release."
            ) from None
        return destination

    def _rollback_failed_activation(
        self,
        candidate: VerifiedBundle,
        previous: VerifiedBundle | None,
        cause: Exception,
    ) -> None:
        try:
            self.services.stop(candidate.systemd_unit)
        except AgentError:
            pass
        rollback_error: str | None = None
        if previous is None:
            self.activation.clear()
            self.paths.runtime_environment.unlink(missing_ok=True)
            self.paths.secret_environment.unlink(missing_ok=True)
        else:
            try:
                self._prepare_environment(previous)
                self.activation.activate(previous.bundle_id)
                self.services.daemon_reload()
                self.services.start(previous.systemd_unit)
                self.health.wait_healthy(previous.bundle_id, previous.health)
            except Exception:
                rollback_error = "Previous release was reselected but did not verify healthy."
        cause_message = cause.message if isinstance(cause, AgentError) else "Activation failed."
        self._record_event(
            "deployment.rolled_back",
            candidate_bundle_id=candidate.bundle_id,
            active_bundle_id=previous.bundle_id if previous else None,
            previous_bundle_id=previous.bundle_id if previous else None,
            error=cause_message,
            rollback_error=rollback_error,
        )
        self._write_state(
            "rollback-failed" if rollback_error else "rolled-back",
            active_bundle_id=previous.bundle_id if previous else None,
            error=rollback_error or cause_message,
        )

    def _prepare_environment(self, bundle: VerifiedBundle) -> None:
        runtime = {
            "CELLFORGE_BUNDLE_ID": bundle.bundle_id,
            "CELLFORGE_BUNDLE_ROOT": str(bundle.root),
            "CELLFORGE_MANIFEST": str(bundle.root / "manifest.json"),
        }
        secrets: dict[str, str] = {}
        secret_root = self.paths.secret_store.resolve()
        for environment_name, reference in bundle.secret_references.items():
            relative_secret = PurePosixPath(reference)
            unresolved_secret = secret_root.joinpath(*relative_secret.parts)
            if _path_has_symlink(unresolved_secret, secret_root):
                raise AgentError("agent.secret.path_invalid", "Secret paths may not use symlinks.")
            secret_path = unresolved_secret.resolve()
            try:
                secret_path.relative_to(secret_root)
            except ValueError:
                raise AgentError(
                    "agent.secret.path_invalid", "Secret reference escapes local storage."
                ) from None
            if not secret_path.is_file():
                raise AgentError(
                    "agent.secret.unavailable", "A referenced local secret is unavailable."
                )
            try:
                value = secret_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                raise AgentError(
                    "agent.secret.unavailable", "A referenced local secret is unreadable."
                ) from None
            if not value or "\n" in value or "\r" in value or "\x00" in value:
                raise AgentError(
                    "agent.secret.invalid", "Local secrets must be nonempty single-line text."
                )
            secrets[environment_name] = value
        _write_environment(self.paths.runtime_environment, runtime)
        _write_environment(self.paths.secret_environment, secrets)

    def _verified_release(self, bundle_id: str | None) -> VerifiedBundle:
        if bundle_id is None or _SHA256.fullmatch(bundle_id) is None:
            raise AgentError("agent.release.invalid", "Release ID is invalid.")
        verified = self._verify_signed_bundle(self.paths.releases / bundle_id)
        if verified.bundle_id != bundle_id:
            raise AgentError("agent.release.invalid", "Release path and bundle ID differ.")
        return verified

    def _verify_signed_bundle(self, bundle_root: str | Path) -> VerifiedBundle:
        return verify_bundle(
            bundle_root,
            trusted_keys=self.paths.trusted_keys,
            require_signature=True,
        )

    def _write_state(self, result: str, *, active_bundle_id: str | None, error: str | None) -> None:
        previous = self._read_state().get("active_bundle_id")
        document = {
            "schema_version": "0.1.0",
            "active_bundle_id": active_bundle_id,
            "previous_bundle_id": previous if isinstance(previous, str) else None,
            "last_result": result,
            "last_error": error,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _atomic_write(self.paths.state_file, _canonical_bytes(document) + b"\n", mode=0o600)

    def _read_state(self) -> JsonObject:
        if not self.paths.state_file.is_file():
            return {}
        try:
            document: object = json.loads(self.paths.state_file.read_bytes())
        except (OSError, json.JSONDecodeError):
            return {}
        return document if isinstance(document, dict) else {}

    def _record_event(self, event_type: str, **payload: Any) -> None:
        self.paths.state_root.mkdir(parents=True, exist_ok=True)
        event = {
            "schema_version": "0.1.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            **payload,
        }
        try:
            with self.paths.event_journal.open("ab") as stream:
                stream.write(_canonical_bytes(event) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(self.paths.event_journal, 0o600)
        except OSError:
            raise AgentError(
                "agent.events.write_failed", "Could not persist deployment event."
            ) from None


def install_systemd_units(
    unit_directory: str | Path,
    services: ServiceManager,
    *,
    force: bool = False,
) -> tuple[Path, ...]:
    """Install packaged systemd templates explicitly, then reload and enable the runtime target."""

    from importlib.resources import files

    destination_root = Path(unit_directory).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    source_root = files("cellforge_bundle").joinpath("systemd")
    installed: list[Path] = []
    for name in (
        "cellforge-bundle-agent.service",
        "cellforge-runtime.service",
        "cellforge-runtime.target",
    ):
        content = source_root.joinpath(name).read_bytes()
        destination = destination_root / name
        if destination.exists() and destination.read_bytes() != content and not force:
            raise AgentError(
                "agent.systemd.unit_conflict", f"Existing systemd unit '{name}' differs."
            )
        _atomic_write(destination, content, mode=0o644)
        installed.append(destination)
    services.daemon_reload()
    services.enable("cellforge-runtime.target")
    return tuple(installed)


def _regular_bundle_files(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise AgentError("agent.bundle.symlink", "Bundle symlinks are not permitted.")
        if path.is_dir():
            continue
        if not path.is_file():
            raise AgentError("agent.bundle.file_type", "Bundle contains a non-regular file.")
        relative = path.relative_to(root).as_posix()
        _normalized_path(relative)
        try:
            files[relative] = path.read_bytes()
        except OSError:
            raise AgentError("agent.bundle.unreadable", "Bundle file is unreadable.") from None
    return files


def _read_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        raise AgentError("agent.bundle.checksums_invalid", "Checksum file is unreadable.") from None
    checksums: dict[str, str] = {}
    for line in lines:
        match = _CHECKSUM.fullmatch(line)
        if match is None:
            raise AgentError("agent.bundle.checksums_invalid", "Checksum line is malformed.")
        digest, raw_path = match.groups()
        relative = _normalized_path(raw_path)
        if relative == "checksums.txt" or relative in checksums:
            raise AgentError(
                "agent.bundle.checksums_invalid", "Checksum path is duplicated or reserved."
            )
        checksums[relative] = digest
    if list(checksums) != sorted(checksums):
        raise AgentError("agent.bundle.checksums_invalid", "Checksum entries must be sorted.")
    return checksums


def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AgentError("agent.bundle.path_invalid", "Bundle path is invalid.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise AgentError("agent.bundle.path_invalid", "Bundle path is not normalized and relative.")
    return path.as_posix()


def _reject_bundled_secrets(files: Mapping[str, bytes]) -> None:
    forbidden_names = {".env", "credentials", "secrets"}
    for relative, content in files.items():
        path = PurePosixPath(relative)
        if relative != "config/secret-references.json" and (
            any(part.lower() in forbidden_names for part in path.parts)
            or path.suffix.lower() in {".key", ".p12", ".pfx"}
        ):
            raise AgentError("agent.secret.bundled", "Secret-bearing bundle paths are forbidden.")
        if _PRIVATE_KEY_MARKER in content:
            raise AgentError(
                "agent.secret.bundled", "Private key material is forbidden in bundles."
            )
        if (
            path.suffix.lower() not in {".json", ".yaml", ".yml"}
            or relative == "config/secret-references.json"
        ):
            continue
        try:
            document: object = (
                json.loads(content) if path.suffix.lower() == ".json" else yaml.safe_load(content)
            )
        except (json.JSONDecodeError, UnicodeError, yaml.YAMLError):
            continue
        if _contains_secret_value(document):
            raise AgentError("agent.secret.bundled", "Secret values are forbidden in bundle data.")


def _contains_secret_value(value: object) -> bool:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            is_reference = key.endswith("_ref") or key.endswith("_reference")
            if not is_reference and any(marker in key for marker in _SENSITIVE_KEYS):
                if child not in (None, "", [], {}):
                    return True
            if _contains_secret_value(child):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_value(child) for child in value)
    return False


def _secret_references(root: Path, files: Mapping[str, bytes]) -> Mapping[str, str]:
    relative = "config/secret-references.json"
    if relative not in files:
        return {}
    document = _read_json(root / relative, "agent.secret.references_invalid")
    if document.get("schema_version") != "0.1.0" or set(document) != {
        "schema_version",
        "environment",
    }:
        raise AgentError("agent.secret.references_invalid", "Secret reference document is invalid.")
    environment = document.get("environment")
    if not isinstance(environment, dict):
        raise AgentError("agent.secret.references_invalid", "Secret environment map is invalid.")
    references: dict[str, str] = {}
    for key, value in sorted(environment.items()):
        if (
            not isinstance(key, str)
            or _ENVIRONMENT_NAME.fullmatch(key) is None
            or not isinstance(value, str)
            or _SECRET_REFERENCE.fullmatch(value) is None
            or PurePosixPath(value).as_posix() != value
            or ".." in PurePosixPath(value).parts
        ):
            raise AgentError(
                "agent.secret.references_invalid", "Secret reference entry is invalid."
            )
        references[key] = value
    return references


def _agent_configuration(document: JsonObject) -> tuple[str, HealthConfiguration]:
    if document.get("schema_version") != "0.1.0":
        raise AgentError(
            "agent.bundle.config_invalid", "Agent configuration version is unsupported."
        )
    unit = document.get("systemd_unit")
    health = document.get("health")
    if (
        not isinstance(unit, str)
        or _SYSTEMD_UNIT.fullmatch(unit) is None
        or unit != "cellforge-runtime.target"
        or not isinstance(health, dict)
    ):
        raise AgentError("agent.bundle.config_invalid", "Agent systemd configuration is invalid.")
    url = health.get("url")
    timeout = health.get("timeout_seconds")
    interval = health.get("interval_seconds")
    try:
        parsed_url = urllib.parse.urlsplit(url) if isinstance(url, str) else None
        health_port = parsed_url.port if parsed_url is not None else None
    except ValueError:
        parsed_url = None
        health_port = None
    if (
        not isinstance(url, str)
        or parsed_url is None
        or parsed_url.scheme != "http"
        or parsed_url.hostname not in {"127.0.0.1", "::1"}
        or health_port is None
        or parsed_url.username is not None
        or parsed_url.password is not None
        or not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 1 <= float(timeout) <= 300
        or not isinstance(interval, (int, float))
        or isinstance(interval, bool)
        or not 0.05 <= float(interval) <= 10
    ):
        raise AgentError("agent.bundle.config_invalid", "Agent health configuration is invalid.")
    return unit, HealthConfiguration(url, float(timeout), float(interval))


def _read_json(path: Path, code: str) -> JsonObject:
    try:
        document: object = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError):
        raise AgentError(code, "JSON document is missing or invalid.") from None
    if not isinstance(document, dict):
        raise AgentError(code, "JSON document must be an object.")
    return document


def _read_yaml(path: Path) -> JsonObject:
    try:
        document: object = yaml.safe_load(path.read_bytes())
    except (OSError, UnicodeError, yaml.YAMLError):
        raise AgentError(
            "agent.target.profile_invalid", "Target profile is missing or invalid."
        ) from None
    if not isinstance(document, dict):
        raise AgentError("agent.target.profile_invalid", "Target profile must be an object.")
    return document


def _string_set(value: object, label: str) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise AgentError("agent.target.facts_invalid", f"Invalid {label} inventory.")
    return set(value)


def _write_environment(path: Path, values: Mapping[str, str]) -> None:
    lines = [f'{key}="{_escape_environment(value)}"' for key, value in sorted(values.items())]
    content = ("\n".join(lines) + ("\n" if lines else "")).encode()
    _atomic_write(path, content, mode=0o600)


def _escape_environment(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _atomic_write(path: Path, content: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{time.time_ns()}"
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise AgentError(
            "agent.state.write_failed", "Could not atomically write local state."
        ) from None


def _make_release_read_only(root: Path) -> None:
    if os.name == "nt":
        return
    try:
        for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            path.chmod(path.stat().st_mode & ~0o222)
        root.chmod(root.stat().st_mode & ~0o222)
    except OSError:
        raise AgentError(
            "agent.release.permissions_failed", "Could not make release read-only."
        ) from None


def _path_has_symlink(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = path.open("a+b")
    except OSError:
        raise AgentError("agent.lock.unavailable", "Could not open the activation lock.") from None
    try:
        if os.name == "nt":
            msvcrt: Any = importlib.import_module("msvcrt")
            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise AgentError(
                    "agent.busy", "Another bundle-agent operation is active."
                ) from None
        else:
            fcntl: Any = importlib.import_module("fcntl")
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise AgentError(
                    "agent.busy", "Another bundle-agent operation is active."
                ) from None
        yield
    finally:
        if os.name == "nt":
            msvcrt = importlib.import_module("msvcrt")
            try:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            fcntl = importlib.import_module("fcntl")
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        stream.close()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
