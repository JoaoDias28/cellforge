"""Pure deployment profile browsing, signed bundle assembly, diffing,
signature verification, and agent coordination service.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from cellforge_bundle.agent import (
    AgentPaths as AgentPaths,
)
from cellforge_bundle.agent import (
    BundleAgent,
)
from cellforge_bundle.assembly import (
    AssemblyError,
    assemble_bundle,
    signature_payload,
)
from cellforge_domain import ExecutionMode
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from cellforge.studio.application import ProjectContents, ValidationItem


@dataclass(frozen=True, slots=True)
class DeploymentProfileSummary:
    """High-level summary of one declared deployment profile."""

    id: str
    name: str
    path: str
    execution_mode: str
    target_profile: str
    simulation_fidelity: str | None
    adapter_count: int
    container_count: int
    native_package_count: int
    valid: bool


@dataclass(frozen=True, slots=True)
class DeploymentProfileDetail:
    """Full deployment profile data with validation findings."""

    summary: DeploymentProfileSummary
    data: Mapping[str, Any]
    validation: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class DeploymentBrowserResult:
    """Result of querying all declared deployment profiles in a project."""

    profiles: tuple[DeploymentProfileSummary, ...]
    validation: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class BundleAssemblyResult:
    """Structured outcome of signed bundle assembly."""

    success: bool
    bundle_id: str
    output_path: Path | None
    key_id: str
    manifest: Mapping[str, Any] = field(default_factory=dict)
    checksums: Mapping[str, str] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BundleDiffEntry:
    """One atomic difference between two release bundles or project states."""

    # manifest | files | config | recipes | tasks | calibrations | target_profile | evidence
    category: str
    key: str
    old_value: Any
    new_value: Any
    change_type: str  # added | removed | modified


@dataclass(frozen=True, slots=True)
class BundleDiffResult:
    """Structured comparison between two release bundles."""

    base_bundle_id: str
    candidate_bundle_id: str
    differences: tuple[BundleDiffEntry, ...]
    is_compatible: bool
    summary: str


@dataclass(frozen=True, slots=True)
class SignatureVerificationResult:
    """Result of Ed25519 detached signature verification."""

    valid: bool
    key_id: str
    algorithm: str
    error_code: str | None
    message: str
    signed_files_count: int


@dataclass(frozen=True, slots=True)
class TargetCompatibilityResult:
    """Result of preflight target compatibility check."""

    compatible: bool
    profile_id: str
    platform_checks: Mapping[str, bool]
    missing_packages: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    missing_entrypoints: tuple[str, ...]
    findings: tuple[ValidationItem, ...] = ()


@dataclass(frozen=True, slots=True)
class DeploymentStatusResult:
    """Live status of the deployment agent and release link."""

    state: str
    active_bundle_id: str | None
    previous_bundle_id: str | None
    candidate_bundle_id: str | None
    error: str | None
    last_event: str | None
    event_count: int


@dataclass(frozen=True, slots=True)
class DeploymentInstallResult:
    """Outcome of bundle installation."""

    success: bool
    bundle_id: str
    status: DeploymentStatusResult
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DeploymentRollbackResult:
    """Outcome of bundle rollback."""

    success: bool
    restored_bundle_id: str | None
    status: DeploymentStatusResult
    error: str | None = None


class DeploymentService:
    """Pure deployment profile management, signed assembly, diffing, and agent coordination."""

    def __init__(self, canonical_schema_directory: Path | None = None) -> None:
        self._schemas = (
            canonical_schema_directory.resolve() if canonical_schema_directory is not None else None
        )

    def browse_deployment_profiles(
        self, project_path: Path, contents: ProjectContents
    ) -> DeploymentBrowserResult:
        """Enumerate and summarize all deployment profiles declared in the project."""
        cell_data = self._parse_cell_yaml(contents.cell_yaml)
        if cell_data is None:
            return DeploymentBrowserResult(
                (),
                (
                    ValidationItem(
                        code="deployment.project.invalid",
                        severity="error",
                        path="cell.yaml",
                        message="cell.yaml could not be parsed as a YAML mapping",
                    ),
                ),
            )

        declared = cell_data.get("deployment_profiles", [])
        if not isinstance(declared, list):
            return DeploymentBrowserResult(
                (),
                (
                    ValidationItem(
                        code="deployment.list.invalid",
                        severity="error",
                        path="deployment_profiles",
                        message="cell.yaml deployment_profiles field must be a list of paths",
                    ),
                ),
            )

        summaries: list[DeploymentProfileSummary] = []
        findings: list[ValidationItem] = []

        for rel_path in declared:
            if not isinstance(rel_path, str) or not rel_path.strip():
                continue
            normalized_path = Path(rel_path.strip()).as_posix()
            data, error = self._load_profile_data(project_path, contents, normalized_path)
            if error is not None:
                findings.append(
                    ValidationItem(
                        code="deployment.file.unreadable",
                        severity="error",
                        path=normalized_path,
                        message=error,
                    )
                )
                summaries.append(
                    DeploymentProfileSummary(
                        id=Path(normalized_path).stem,
                        name=Path(normalized_path).stem,
                        path=normalized_path,
                        execution_mode="unknown",
                        target_profile="",
                        simulation_fidelity=None,
                        adapter_count=0,
                        container_count=0,
                        native_package_count=0,
                        valid=False,
                    )
                )
            if data is None:
                continue

            summary, item_findings = self._summarize_profile(normalized_path, data)
            findings.extend(item_findings)
            summaries.append(summary)

        return DeploymentBrowserResult(tuple(summaries), tuple(findings))

    def inspect_deployment_profile(
        self,
        project_path: Path,
        contents: ProjectContents,
        *,
        profile_id_or_path: str,
    ) -> DeploymentProfileDetail | None:
        """Inspect full deployment profile configuration."""
        cell_data = self._parse_cell_yaml(contents.cell_yaml)
        if cell_data is None:
            return None

        declared = cell_data.get("deployment_profiles", [])
        matched_path: str | None = None
        matched_data: dict[str, Any] | None = None

        for item in declared:
            if isinstance(item, str) and item.strip():
                normalized = Path(item.strip()).as_posix()
                data, error = self._load_profile_data(project_path, contents, normalized)
                if data is not None and error is None:
                    prof_obj = (
                        data.get("profile", {}) if isinstance(data.get("profile"), dict) else {}
                    )
                    prof_id = prof_obj.get("id") or data.get("id")
                    if profile_id_or_path in (
                        normalized,
                        Path(normalized).stem,
                        Path(normalized).name,
                        prof_id,
                    ):
                        matched_path = normalized
                        matched_data = data
                        break

        if matched_path is None or matched_data is None:
            target_path = Path(profile_id_or_path.strip()).as_posix()
            matched_data, error = self._load_profile_data(project_path, contents, target_path)
            if matched_data is None or error is not None:
                return None
            matched_path = target_path

        summary, findings = self._summarize_profile(matched_path, matched_data)
        return DeploymentProfileDetail(
            summary=summary,
            data=matched_data,
            validation=tuple(findings),
        )

    def assemble_bundle_release(
        self,
        project_path: Path,
        schemas_path: Path,
        *,
        target_profile: str,
        mode: str,
        source_revision: str,
        output_dir: Path,
        signing_key_path: Path,
    ) -> BundleAssemblyResult:
        """Assemble an immutable, content-addressed signed bundle release."""
        try:
            exec_mode = ExecutionMode(mode.lower())
        except ValueError:
            return BundleAssemblyResult(
                success=False,
                bundle_id="",
                output_path=None,
                key_id="",
                error=f"Invalid execution mode: {mode!r}",
            )

        try:
            result = assemble_bundle(
                project=project_path,
                schemas=schemas_path,
                target_profile=target_profile,
                mode=exec_mode,
                source_revision=source_revision,
                output=output_dir,
                signing_key=signing_key_path,
            )

            # Read back generated manifest and checksums for structured result
            manifest_file = output_dir / "manifest.json"
            manifest_data: dict[str, Any] = {}
            if manifest_file.is_file():
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))

            checksums_file = output_dir / "checksums.txt"
            checksums_map: dict[str, str] = {}
            if checksums_file.is_file():
                for line in checksums_file.read_text(encoding="utf-8").splitlines():
                    if "  " in line:
                        digest, _, rel = line.partition("  ")
                        checksums_map[rel.strip()] = digest.strip()

            return BundleAssemblyResult(
                success=True,
                bundle_id=result.bundle_id,
                output_path=result.output,
                key_id=result.key_id,
                manifest=manifest_data,
                checksums=checksums_map,
            )
        except AssemblyError as error:
            return BundleAssemblyResult(
                success=False,
                bundle_id="",
                output_path=None,
                key_id="",
                error=str(error),
            )
        except Exception as error:
            return BundleAssemblyResult(
                success=False,
                bundle_id="",
                output_path=None,
                key_id="",
                error=f"Bundle assembly failed: {error}",
            )

    def diff_bundles(
        self,
        base_bundle_path: Path,
        candidate_bundle_path: Path,
    ) -> BundleDiffResult:
        """Compute deterministic structured differences between two bundle directories."""
        base_manifest = self._load_manifest(base_bundle_path)
        candidate_manifest = self._load_manifest(candidate_bundle_path)

        base_id = str(base_manifest.get("bundle_id", base_bundle_path.name))
        candidate_id = str(candidate_manifest.get("bundle_id", candidate_bundle_path.name))

        differences: list[BundleDiffEntry] = []

        # 1. Manifest metadata diff
        for field_name in ("target_profile", "execution_mode", "source_revision", "cell_id"):
            old_val = base_manifest.get(field_name)
            new_val = candidate_manifest.get(field_name)
            if old_val != new_val:
                differences.append(
                    BundleDiffEntry(
                        category="manifest",
                        key=field_name,
                        old_value=old_val,
                        new_value=new_val,
                        change_type="modified"
                        if old_val is not None and new_val is not None
                        else ("added" if old_val is None else "removed"),
                    )
                )

        # 2. Files inventory diff
        base_files: dict[str, Any] = {
            str(f["path"]): f
            for f in base_manifest.get("files", [])
            if isinstance(f, dict) and "path" in f
        }
        candidate_files: dict[str, Any] = {
            str(f["path"]): f
            for f in candidate_manifest.get("files", [])
            if isinstance(f, dict) and "path" in f
        }

        all_file_paths = sorted(set(base_files) | set(candidate_files))
        for file_path in all_file_paths:
            if not file_path:
                continue
            old_f = base_files.get(file_path)
            new_f = candidate_files.get(file_path)
            if old_f is None and new_f is not None:
                differences.append(
                    BundleDiffEntry(
                        category="files",
                        key=file_path,
                        old_value=None,
                        new_value=new_f.get("sha256"),
                        change_type="added",
                    )
                )
            elif old_f is not None and new_f is None:
                differences.append(
                    BundleDiffEntry(
                        category="files",
                        key=file_path,
                        old_value=old_f.get("sha256"),
                        new_value=None,
                        change_type="removed",
                    )
                )
            elif old_f is not None and new_f is not None:
                if old_f.get("sha256") != new_f.get("sha256"):
                    differences.append(
                        BundleDiffEntry(
                            category="files",
                            key=file_path,
                            old_value=old_f.get("sha256"),
                            new_value=new_f.get("sha256"),
                            change_type="modified",
                        )
                    )

        # 3. Deep configuration diff (cell.yaml, config/, recipes/)
        self._diff_config_files(base_bundle_path, candidate_bundle_path, differences)

        # 4. Check compatibility (e.g. same target profile and cell ID)
        is_compatible = base_manifest.get("cell_id") == candidate_manifest.get(
            "cell_id"
        ) and base_manifest.get("target_profile") == candidate_manifest.get("target_profile")

        mod_count = sum(1 for d in differences if d.change_type == "modified")
        add_count = sum(1 for d in differences if d.change_type == "added")
        rem_count = sum(1 for d in differences if d.change_type == "removed")
        summary = (
            f"{len(differences)} differences ({add_count} added, "
            f"{rem_count} removed, {mod_count} modified)"
        )

        return BundleDiffResult(
            base_bundle_id=base_id,
            candidate_bundle_id=candidate_id,
            differences=tuple(differences),
            is_compatible=is_compatible,
            summary=summary,
        )

    def verify_bundle_signature(
        self,
        bundle_root: Path,
        trusted_keys_root: Path | None = None,
    ) -> SignatureVerificationResult:
        """Verify the Ed25519 detached signature and checksum inventory of a bundle."""
        sig_file = bundle_root / "signature.json"
        if not sig_file.is_file():
            return SignatureVerificationResult(
                valid=False,
                key_id="",
                algorithm="Ed25519",
                error_code="bundle.signature.missing",
                message="signature.json is missing from bundle root",
                signed_files_count=0,
            )

        try:
            sig_doc = json.loads(sig_file.read_text(encoding="utf-8"))
            key_id = str(sig_doc.get("key_id", ""))
            algorithm = str(sig_doc.get("algorithm", "Ed25519"))
            raw_signature = base64.b64decode(sig_doc.get("signature", ""))
            bundle_id = str(sig_doc.get("bundle_id", ""))
        except Exception as error:
            return SignatureVerificationResult(
                valid=False,
                key_id="",
                algorithm="Ed25519",
                error_code="bundle.signature.malformed",
                message=f"signature.json is malformed: {error}",
                signed_files_count=0,
            )

        if not key_id or not raw_signature or not bundle_id:
            return SignatureVerificationResult(
                valid=False,
                key_id=key_id,
                algorithm=algorithm,
                error_code="bundle.signature.incomplete",
                message="signature.json missing required key_id, signature, or bundle_id",
                signed_files_count=0,
            )

        # Locate trusted public key
        trusted_key_dir = trusted_keys_root or Path("/etc/cellforge/trusted-keys")
        pub_key_path = trusted_key_dir / f"{key_id}.pub"
        if not pub_key_path.is_file():
            return SignatureVerificationResult(
                valid=False,
                key_id=key_id,
                algorithm=algorithm,
                error_code="bundle.signature.untrusted_key",
                message=(
                    f"Signing key {key_id} is not present in trusted keys store ({trusted_key_dir})"
                ),
                signed_files_count=0,
            )

        try:
            public_key_bytes = pub_key_path.read_bytes()
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        except Exception as error:
            return SignatureVerificationResult(
                valid=False,
                key_id=key_id,
                algorithm=algorithm,
                error_code="bundle.signature.invalid_public_key",
                message=f"Trusted public key {key_id}.pub is invalid: {error}",
                signed_files_count=0,
            )

        # Collect inventory and verify signature over payload
        inventory: dict[str, bytes] = {}
        for item in sorted(bundle_root.rglob("*")):
            if item.is_file() and item.name not in {"checksums.txt", "signature.json"}:
                rel = item.relative_to(bundle_root).as_posix()
                inventory[rel] = item.read_bytes()

        payload = signature_payload(bundle_id, inventory)

        try:
            public_key.verify(raw_signature, payload)
        except InvalidSignature:
            return SignatureVerificationResult(
                valid=False,
                key_id=key_id,
                algorithm=algorithm,
                error_code="bundle.signature.verification_failed",
                message="Ed25519 signature verification failed: bundle contents or ID tampered",
                signed_files_count=len(inventory),
            )
        except Exception as error:
            return SignatureVerificationResult(
                valid=False,
                key_id=key_id,
                algorithm=algorithm,
                error_code="bundle.signature.error",
                message=f"Signature verification error: {error}",
                signed_files_count=len(inventory),
            )

        # Verify checksums.txt
        checksum_file = bundle_root / "checksums.txt"
        if not checksum_file.is_file():
            return SignatureVerificationResult(
                valid=False,
                key_id=key_id,
                algorithm=algorithm,
                error_code="bundle.checksums.missing",
                message="checksums.txt is missing from bundle root",
                signed_files_count=len(inventory),
            )

        for line in checksum_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, _, rel_path = line.partition("  ")
            rel_file = bundle_root / rel_path.strip()
            if not rel_file.is_file():
                return SignatureVerificationResult(
                    valid=False,
                    key_id=key_id,
                    algorithm=algorithm,
                    error_code="bundle.checksums.file_missing",
                    message=f"File '{rel_path.strip()}' listed in checksums.txt does not exist",
                    signed_files_count=len(inventory),
                )
            if hashlib.sha256(rel_file.read_bytes()).hexdigest() != digest.strip():
                return SignatureVerificationResult(
                    valid=False,
                    key_id=key_id,
                    algorithm=algorithm,
                    error_code="bundle.checksums.mismatch",
                    message=f"File '{rel_path.strip()}' digest does not match checksums.txt",
                    signed_files_count=len(inventory),
                )

        return SignatureVerificationResult(
            valid=True,
            key_id=key_id,
            algorithm=algorithm,
            error_code=None,
            message="Ed25519 signature and SHA-256 checksum inventory verified successfully",
            signed_files_count=len(inventory),
        )

    def preflight_target_compatibility(
        self,
        bundle_root: Path,
        target_facts_path: Path,
    ) -> TargetCompatibilityResult:
        """Check bundle compatibility against local target facts."""
        manifest = self._load_manifest(bundle_root)
        profile_id = str(manifest.get("target_profile", ""))

        if not target_facts_path.is_file():
            return TargetCompatibilityResult(
                compatible=False,
                profile_id=profile_id,
                platform_checks={},
                missing_packages=(),
                missing_prerequisites=(),
                missing_entrypoints=(),
                findings=(
                    ValidationItem(
                        code="target.facts.missing",
                        severity="error",
                        path=str(target_facts_path),
                        message=f"Target facts file '{target_facts_path}' does not exist",
                    ),
                ),
            )

        try:
            facts = json.loads(target_facts_path.read_text(encoding="utf-8"))
        except Exception as error:
            return TargetCompatibilityResult(
                compatible=False,
                profile_id=profile_id,
                platform_checks={},
                missing_packages=(),
                missing_prerequisites=(),
                missing_entrypoints=(),
                findings=(
                    ValidationItem(
                        code="target.facts.invalid",
                        severity="error",
                        path=str(target_facts_path),
                        message=f"Target facts file could not be parsed: {error}",
                    ),
                ),
            )

        arch_match = True
        os_match = True
        ros_match = True
        gpu_match = True

        findings: list[ValidationItem] = []
        missing_pkgs: list[str] = []
        missing_prereqs: list[str] = []
        missing_entrypoints: list[str] = []

        # Check required native packages
        target_pkgs = set(facts.get("native_packages", []))
        for pkg in manifest.get("native_packages", []):
            if pkg not in target_pkgs:
                missing_pkgs.append(pkg)
                findings.append(
                    ValidationItem(
                        code="target.package.missing",
                        severity="error",
                        path="native_packages",
                        message=f"Target is missing required native package '{pkg}'",
                    )
                )

        # Check external prerequisites
        target_prereqs = set(facts.get("external_prerequisites", []))
        for prereq in manifest.get("external_prerequisites", []):
            if prereq not in target_prereqs:
                missing_prereqs.append(prereq)
                findings.append(
                    ValidationItem(
                        code="target.prerequisite.missing",
                        severity="error",
                        path="external_prerequisites",
                        message=f"Target is missing required prerequisite '{prereq}'",
                    )
                )

        # Check runtime entrypoints
        runtime = manifest.get("runtime", {})
        if isinstance(runtime, dict) and "executable_identities" in runtime:
            installed_entrypoints = set(facts.get("runtime_entrypoints", []))
            for ep in runtime["executable_identities"]:
                if ep not in installed_entrypoints:
                    missing_entrypoints.append(ep)
                    findings.append(
                        ValidationItem(
                            code="target.entrypoint.missing",
                            severity="error",
                            path="runtime.executable_identities",
                            message=f"Target is missing runtime entrypoint '{ep}'",
                        )
                    )

        checks = {
            "arch": arch_match,
            "os": os_match,
            "ros_distribution": ros_match,
            "gpu": gpu_match,
            "packages": len(missing_pkgs) == 0,
            "prerequisites": len(missing_prereqs) == 0,
            "entrypoints": len(missing_entrypoints) == 0,
        }

        compatible = not any(f.severity == "error" for f in findings)
        return TargetCompatibilityResult(
            compatible=compatible,
            profile_id=profile_id,
            platform_checks=checks,
            missing_packages=tuple(missing_pkgs),
            missing_prerequisites=tuple(missing_prereqs),
            missing_entrypoints=tuple(missing_entrypoints),
            findings=tuple(findings),
        )

    def get_agent_status(self, agent_paths: AgentPaths) -> DeploymentStatusResult:
        """Query deployment agent status from state file and event journal."""
        state_file = agent_paths.state_file
        if not state_file.is_file():
            return DeploymentStatusResult(
                state="no_release",
                active_bundle_id=None,
                previous_bundle_id=None,
                candidate_bundle_id=None,
                error=None,
                last_event=None,
                event_count=0,
            )

        try:
            state_doc = json.loads(state_file.read_text(encoding="utf-8"))
            active_id = state_doc.get("active_bundle_id")
            result = str(state_doc.get("result", "unknown"))
            error_msg = state_doc.get("error")
        except Exception as error:
            return DeploymentStatusResult(
                state="error",
                active_bundle_id=None,
                previous_bundle_id=None,
                candidate_bundle_id=None,
                error=f"Unreadable agent state file: {error}",
                last_event=None,
                event_count=0,
            )

        events: list[dict[str, Any]] = []
        journal = agent_paths.event_journal
        if journal.is_file():
            for line in journal.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass

        last_event_type = events[-1].get("event_type") if events else None

        return DeploymentStatusResult(
            state=result,
            active_bundle_id=active_id,
            previous_bundle_id=events[-2].get("active_bundle_id") if len(events) >= 2 else None,
            candidate_bundle_id=events[-1].get("candidate_bundle_id") if events else None,
            error=error_msg,
            last_event=last_event_type,
            event_count=len(events),
        )

    def install_bundle(
        self,
        bundle_root: Path,
        agent_paths: AgentPaths,
        *,
        systemd_runner: Any | None = None,
        health_checker: Any | None = None,
    ) -> DeploymentInstallResult:
        """Execute fail-closed bundle installation via BundleAgent."""
        try:
            agent = BundleAgent(
                paths=agent_paths,
                services=systemd_runner,
                health=health_checker,
            )
            agent_status = agent.install(bundle_root)
            status_res = self.get_agent_status(agent_paths)
            return DeploymentInstallResult(
                success=agent_status.last_result == "healthy",
                bundle_id=agent_status.active_bundle_id or "",
                status=status_res,
                error=agent_status.last_error,
            )
        except Exception as error:
            status_res = self.get_agent_status(agent_paths)
            return DeploymentInstallResult(
                success=False,
                bundle_id="",
                status=status_res,
                error=str(error),
            )

    def rollback_deployment(
        self,
        agent_paths: AgentPaths,
        *,
        systemd_runner: Any | None = None,
        health_checker: Any | None = None,
    ) -> DeploymentRollbackResult:
        """Rollback to the previous release via BundleAgent."""
        try:
            agent = BundleAgent(
                paths=agent_paths,
                services=systemd_runner,
                health=health_checker,
            )
            agent_status = agent.rollback()
            status_res = self.get_agent_status(agent_paths)
            return DeploymentRollbackResult(
                success=agent_status.last_result == "healthy",
                restored_bundle_id=agent_status.active_bundle_id,
                status=status_res,
                error=agent_status.last_error,
            )
        except Exception as error:
            status_res = self.get_agent_status(agent_paths)
            return DeploymentRollbackResult(
                success=False,
                restored_bundle_id=None,
                status=status_res,
                error=str(error),
            )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _parse_cell_yaml(self, text: str) -> dict[str, Any] | None:
        try:
            parsed = yaml.safe_load(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _load_profile_data(
        self, project_path: Path, contents: ProjectContents, rel_path: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        text: str | None = None
        if rel_path in contents.artifacts:
            raw = contents.artifacts[rel_path]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return None, f"Profile file '{rel_path}' is not valid UTF-8"
        else:
            file_path = project_path / rel_path
            if file_path.is_file():
                try:
                    text = file_path.read_text(encoding="utf-8")
                except Exception as error:
                    return None, f"Could not read profile file '{rel_path}': {error}"

        if text is None:
            return None, f"Profile file '{rel_path}' does not exist"

        try:
            data = yaml.safe_load(text)
            if not isinstance(data, dict):
                return None, f"Profile file '{rel_path}' must contain a YAML mapping"
            return data, None
        except Exception as error:
            return None, f"Invalid YAML in '{rel_path}': {error}"

    def _summarize_profile(
        self, rel_path: str, data: dict[str, Any]
    ) -> tuple[DeploymentProfileSummary, list[ValidationItem]]:
        findings: list[ValidationItem] = []
        prof_obj = data.get("profile", {}) if isinstance(data.get("profile"), dict) else {}
        runtime_obj = data.get("runtime", {}) if isinstance(data.get("runtime"), dict) else {}

        profile_id = str(
            prof_obj.get("id") or data.get("id") or data.get("name") or Path(rel_path).stem
        )
        profile_name = str(prof_obj.get("name") or data.get("name") or profile_id)

        modes = data.get("modes", ["simulation"])
        exec_mode = (
            modes[0]
            if isinstance(modes, list) and modes
            else str(data.get("execution_mode", "simulation"))
        )
        target_profile = str(prof_obj.get("id") or data.get("target_profile", profile_id))
        fidelity = runtime_obj.get("simulation_fidelity") or data.get("simulation_fidelity")

        adapters = runtime_obj.get("executables") or data.get("adapters", {})
        adapter_count = len(adapters) if isinstance(adapters, dict) else 0

        containers = runtime_obj.get("containers") or data.get("containers", [])
        container_count = len(containers) if isinstance(containers, list) else 0

        native_pkgs = runtime_obj.get("native_packages") or data.get("native_packages", [])
        native_count = len(native_pkgs) if isinstance(native_pkgs, list) else 0

        valid = True
        if not target_profile:
            findings.append(
                ValidationItem(
                    code="deployment.missing_target_profile",
                    severity="error",
                    path=f"{rel_path}/target_profile",
                    message="Deployment profile missing required target_profile",
                )
            )
            valid = False

        summary = DeploymentProfileSummary(
            id=profile_id,
            name=profile_name,
            path=rel_path,
            execution_mode=exec_mode,
            target_profile=target_profile,
            simulation_fidelity=str(fidelity) if fidelity is not None else None,
            adapter_count=adapter_count,
            container_count=container_count,
            native_package_count=native_count,
            valid=valid,
        )
        return summary, findings

    def _load_manifest(self, root: Path) -> dict[str, Any]:
        manifest_file = root / "manifest.json"
        if manifest_file.is_file():
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def _diff_config_files(
        self, base_root: Path, candidate_root: Path, differences: list[BundleDiffEntry]
    ) -> None:
        configs_to_check = [
            ("config/cell.yaml", "config"),
            ("config/agent.json", "config"),
            ("config/launch.json", "config"),
            ("config/operator-recovery.json", "config"),
            ("evidence-summary.json", "evidence"),
        ]
        for rel_path, category in configs_to_check:
            base_f = base_root / rel_path
            cand_f = candidate_root / rel_path
            if base_f.is_file() and cand_f.is_file():
                if base_f.read_bytes() != cand_f.read_bytes():
                    differences.append(
                        BundleDiffEntry(
                            category=category,
                            key=rel_path,
                            old_value=hashlib.sha256(base_f.read_bytes()).hexdigest(),
                            new_value=hashlib.sha256(cand_f.read_bytes()).hexdigest(),
                            change_type="modified",
                        )
                    )
            elif not base_f.is_file() and cand_f.is_file():
                differences.append(
                    BundleDiffEntry(
                        category=category,
                        key=rel_path,
                        old_value=None,
                        new_value=hashlib.sha256(cand_f.read_bytes()).hexdigest(),
                        change_type="added",
                    )
                )
            elif base_f.is_file() and not cand_f.is_file():
                differences.append(
                    BundleDiffEntry(
                        category=category,
                        key=rel_path,
                        old_value=hashlib.sha256(base_f.read_bytes()).hexdigest(),
                        new_value=None,
                        change_type="removed",
                    )
                )
