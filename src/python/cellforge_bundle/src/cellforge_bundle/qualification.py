"""Executable software-release qualification and integrity-protected evidence."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

QUALIFICATION_DISCLAIMERS: dict[str, str] = {
    "functional_safety": (
        "Simulation and runtime software status are standard-control engineering data only. "
        "Functional safety remains independently enforced and validated by external rated hardware."
    ),
    "laser_process_simulation": (
        "Laser simulation validates sequencing, protocol handshakes, and timing only. "
        "Physical laser beam/material interaction and mark quality qualification remain required."
    ),
    "hardware_qualification": (
        "Physical hardware adapters, electrical I/O, on-cell commissioning, and production "
        "acceptance testing are deferred to Task 034."
    ),
}

_REQUIRED_CATEGORY_VALUES = {
    "nominal",
    "fault",
    "cancel",
    "timeout",
    "restart",
    "corrupt_bundle",
    "offline_platform",
    "stale_device",
    "uncertain_process",
}
_L2_REPORT_KIND = "cellforge.isaac_l2_seed_report"
_L2_BACKEND = "Isaac Sim 6 OpenUSD/PhysX"
_L2_FAULT_CODES = {
    "simulation.pen.dropped",
    "fixture.sensor.seating_failed",
    "motion.plan.collision",
}


class QualificationCategory(StrEnum):
    """Categories of qualification scenarios mandated by Task 033."""

    NOMINAL = "nominal"
    FAULT = "fault"
    CANCEL = "cancel"
    TIMEOUT = "timeout"
    RESTART = "restart"
    CORRUPT_BUNDLE = "corrupt_bundle"
    OFFLINE_PLATFORM = "offline_platform"
    STALE_DEVICE = "stale_device"
    UNCERTAIN_PROCESS = "uncertain_process"


@dataclass(frozen=True, slots=True)
class ScenarioQualificationResult:
    """Outcome of one scenario derived from an observed runner or probe artifact."""

    scenario_id: str
    category: QualificationCategory
    requested_fidelity: str
    achieved_fidelity: str
    seed: int
    duration_seconds: float
    trace_event_count: int
    final_status: str
    passed: bool
    failure_reasons: tuple[str, ...] = ()
    trace_events_summary: tuple[str, ...] = ()
    observed: bool = False
    available: bool = True
    command: str = ""
    artifact_path: str | None = None
    artifact_sha256: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "category": self.category.value,
            "requested_fidelity": self.requested_fidelity,
            "achieved_fidelity": self.achieved_fidelity,
            "seed": self.seed,
            "duration_seconds": self.duration_seconds,
            "trace_event_count": self.trace_event_count,
            "final_status": self.final_status,
            "passed": self.passed,
            "failure_reasons": list(self.failure_reasons),
            "trace_events_summary": list(self.trace_events_summary),
            "observed": self.observed,
            "available": self.available,
            "command": self.command,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class ParityVerificationResult:
    """Static and dynamic parity evidence for the canonical tree and recipe."""

    tree_path: str
    recipe_path: str
    tree_valid: bool
    recipe_valid: bool
    has_simulator_branches: bool
    forbidden_branch_nodes: tuple[str, ...]
    l0_event_count: int
    l2_event_count: int
    events_equivalent: bool
    passed: bool
    details: str
    dynamic_observed: bool = False
    l2_available: bool = False
    l2_validation: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tree_path": self.tree_path,
            "recipe_path": self.recipe_path,
            "tree_valid": self.tree_valid,
            "recipe_valid": self.recipe_valid,
            "has_simulator_branches": self.has_simulator_branches,
            "forbidden_branch_nodes": list(self.forbidden_branch_nodes),
            "l0_event_count": self.l0_event_count,
            "l2_event_count": self.l2_event_count,
            "events_equivalent": self.events_equivalent,
            "passed": self.passed,
            "details": self.details,
            "dynamic_observed": self.dynamic_observed,
            "l2_available": self.l2_available,
            "l2_validation": dict(self.l2_validation),
        }


@dataclass(frozen=True, slots=True)
class PlatformQualificationResult:
    """Result of observed platform migrations, approvals, evidence, and synchronization."""

    migrations_passed: bool
    schema_version: int
    dual_role_approval_verified: bool
    self_approval_rejected: bool
    evidence_records_verified: bool
    offline_buffering_verified: bool
    idempotent_sync_verified: bool
    passed: bool
    observed: bool = False
    command: str = ""
    artifact_path: str | None = None
    artifact_sha256: str | None = None
    failure_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "migrations_passed": self.migrations_passed,
            "schema_version": self.schema_version,
            "dual_role_approval_verified": self.dual_role_approval_verified,
            "self_approval_rejected": self.self_approval_rejected,
            "evidence_records_verified": self.evidence_records_verified,
            "offline_buffering_verified": self.offline_buffering_verified,
            "idempotent_sync_verified": self.idempotent_sync_verified,
            "passed": self.passed,
            "observed": self.observed,
            "command": self.command,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass(frozen=True, slots=True)
class SoftwareReleaseQualificationReport:
    """Cryptographically verifiable release qualification report document."""

    report_id: str
    timestamp: str
    suite_version: str
    qualifier_identity: str
    git_revision: str
    git_tree_sha: str
    git_clean: bool
    cell_id: str
    cell_name: str
    cell_yaml_sha256: str
    scene_sha256: str
    components: tuple[dict[str, Any], ...]
    recipe: dict[str, Any]
    bundles: dict[str, Any]
    scenarios: tuple[ScenarioQualificationResult, ...]
    parity: ParityVerificationResult
    platform: PlatformQualificationResult
    limitations: dict[str, str]
    overall_passed: bool
    schema_version: str = "0.1.0"
    signature: str | None = None
    key_id: str | None = None
    qualification_command: str = ""
    evidence: tuple[dict[str, Any], ...] = ()
    l2: dict[str, Any] = field(default_factory=dict)
    integrity_sha256: str | None = None

    def canonical_dict(self) -> dict[str, Any]:
        """Produce the canonical serializable dictionary excluding the signature."""
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "suite_version": self.suite_version,
            "qualifier_identity": self.qualifier_identity,
            "git_revision": self.git_revision,
            "git_tree_sha": self.git_tree_sha,
            "git_clean": self.git_clean,
            "cell_id": self.cell_id,
            "cell_name": self.cell_name,
            "cell_yaml_sha256": self.cell_yaml_sha256,
            "scene_sha256": self.scene_sha256,
            "components": list(self.components),
            "recipe": dict(self.recipe),
            "bundles": dict(self.bundles),
            "scenarios": [s.as_dict() for s in self.scenarios],
            "parity": self.parity.as_dict(),
            "platform": self.platform.as_dict(),
            "limitations": dict(self.limitations),
            "overall_passed": self.overall_passed,
            "qualification_command": self.qualification_command,
            "evidence": [dict(item) for item in self.evidence],
            "l2": dict(self.l2),
            "integrity_sha256": self.integrity_sha256,
        }

    def _integrity_json(self) -> str:
        data = self.canonical_dict()
        data["integrity_sha256"] = None
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def as_dict(self) -> dict[str, Any]:
        data = self.canonical_dict()
        data["signature"] = self.signature
        data["key_id"] = self.key_id
        return data

    def canonical_json(self) -> str:
        """Produce canonical deterministic JSON for signature computation."""
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SoftwareReleaseQualificationReport:
        """Parse current or Task 033-shaped JSON with additive-field defaults."""

        def _tuple_strings(value: Any) -> tuple[str, ...]:
            return (
                tuple(item for item in value if isinstance(item, str))
                if isinstance(value, list)
                else ()
            )

        def _scenario(value: Any) -> ScenarioQualificationResult:
            if not isinstance(value, dict):
                raise ValueError("scenario evidence must be an object")
            return ScenarioQualificationResult(
                scenario_id=str(value.get("scenario_id", "")),
                category=QualificationCategory(str(value.get("category", "fault"))),
                requested_fidelity=str(value.get("requested_fidelity", "")),
                achieved_fidelity=str(value.get("achieved_fidelity", "")),
                seed=int(value.get("seed", 0)),
                duration_seconds=float(value.get("duration_seconds", 0.0)),
                trace_event_count=int(value.get("trace_event_count", 0)),
                final_status=str(value.get("final_status", "")),
                passed=bool(value.get("passed", False)),
                failure_reasons=_tuple_strings(value.get("failure_reasons", [])),
                trace_events_summary=_tuple_strings(value.get("trace_events_summary", [])),
                observed=bool(value.get("observed", False)),
                available=bool(value.get("available", True)),
                command=str(value.get("command", "")),
                artifact_path=(
                    str(value["artifact_path"]) if value.get("artifact_path") is not None else None
                ),
                artifact_sha256=(
                    str(value["artifact_sha256"])
                    if value.get("artifact_sha256") is not None
                    else None
                ),
                evidence=dict(value.get("evidence", {}))
                if isinstance(value.get("evidence", {}), dict)
                else {},
            )

        parity_raw = data.get("parity", {})
        if not isinstance(parity_raw, dict):
            raise ValueError("parity evidence must be an object")
        parity = ParityVerificationResult(
            tree_path=str(parity_raw.get("tree_path", "")),
            recipe_path=str(parity_raw.get("recipe_path", "")),
            tree_valid=bool(parity_raw.get("tree_valid", False)),
            recipe_valid=bool(parity_raw.get("recipe_valid", False)),
            has_simulator_branches=bool(parity_raw.get("has_simulator_branches", False)),
            forbidden_branch_nodes=_tuple_strings(parity_raw.get("forbidden_branch_nodes", [])),
            l0_event_count=int(parity_raw.get("l0_event_count", 0)),
            l2_event_count=int(parity_raw.get("l2_event_count", 0)),
            events_equivalent=bool(parity_raw.get("events_equivalent", False)),
            passed=bool(parity_raw.get("passed", False)),
            details=str(parity_raw.get("details", "")),
            dynamic_observed=bool(parity_raw.get("dynamic_observed", False)),
            l2_available=bool(parity_raw.get("l2_available", False)),
            l2_validation=dict(parity_raw.get("l2_validation", {}))
            if isinstance(parity_raw.get("l2_validation", {}), dict)
            else {},
        )
        platform_raw = data.get("platform", {})
        if not isinstance(platform_raw, dict):
            raise ValueError("platform evidence must be an object")
        platform = PlatformQualificationResult(
            migrations_passed=bool(platform_raw.get("migrations_passed", False)),
            schema_version=int(platform_raw.get("schema_version", 0)),
            dual_role_approval_verified=bool(
                platform_raw.get("dual_role_approval_verified", False)
            ),
            self_approval_rejected=bool(platform_raw.get("self_approval_rejected", False)),
            evidence_records_verified=bool(platform_raw.get("evidence_records_verified", False)),
            offline_buffering_verified=bool(platform_raw.get("offline_buffering_verified", False)),
            idempotent_sync_verified=bool(platform_raw.get("idempotent_sync_verified", False)),
            passed=bool(platform_raw.get("passed", False)),
            observed=bool(platform_raw.get("observed", False)),
            command=str(platform_raw.get("command", "")),
            artifact_path=(
                str(platform_raw["artifact_path"])
                if platform_raw.get("artifact_path") is not None
                else None
            ),
            artifact_sha256=(
                str(platform_raw["artifact_sha256"])
                if platform_raw.get("artifact_sha256") is not None
                else None
            ),
            failure_reasons=_tuple_strings(platform_raw.get("failure_reasons", [])),
        )
        scenarios_raw = data.get("scenarios", [])
        if not isinstance(scenarios_raw, list):
            raise ValueError("scenarios must be a list")
        evidence_raw = data.get("evidence", [])
        evidence = (
            tuple(dict(item) for item in evidence_raw if isinstance(item, dict))
            if isinstance(evidence_raw, list)
            else ()
        )
        return cls(
            report_id=str(data.get("report_id", "")),
            timestamp=str(data.get("timestamp", "")),
            suite_version=str(data.get("suite_version", "")),
            qualifier_identity=str(data.get("qualifier_identity", "")),
            git_revision=str(data.get("git_revision", "")),
            git_tree_sha=str(data.get("git_tree_sha", "")),
            git_clean=bool(data.get("git_clean", False)),
            cell_id=str(data.get("cell_id", "")),
            cell_name=str(data.get("cell_name", "")),
            cell_yaml_sha256=str(data.get("cell_yaml_sha256", "")),
            scene_sha256=str(data.get("scene_sha256", "")),
            components=tuple(
                dict(item) for item in data.get("components", []) if isinstance(item, dict)
            ),
            recipe=dict(data.get("recipe", {})) if isinstance(data.get("recipe", {}), dict) else {},
            bundles=dict(data.get("bundles", {}))
            if isinstance(data.get("bundles", {}), dict)
            else {},
            scenarios=tuple(_scenario(item) for item in scenarios_raw),
            parity=parity,
            platform=platform,
            limitations=dict(data.get("limitations", {}))
            if isinstance(data.get("limitations", {}), dict)
            else {},
            overall_passed=bool(data.get("overall_passed", False)),
            schema_version=str(data.get("schema_version", "0.1.0")),
            signature=str(data["signature"]) if data.get("signature") is not None else None,
            key_id=str(data["key_id"]) if data.get("key_id") is not None else None,
            qualification_command=str(data.get("qualification_command", "")),
            evidence=evidence,
            l2=dict(data.get("l2", {})) if isinstance(data.get("l2", {}), dict) else {},
            integrity_sha256=(
                str(data["integrity_sha256"]) if data.get("integrity_sha256") is not None else None
            ),
        )


def verify_tree_and_recipe_parity(project_path: Path) -> ParityVerificationResult:
    """Verify that the canonical tree and recipe contain zero simulator branches.

    This function is intentionally static. Dynamic event counts are filled only by
    :func:`run_software_release_qualification` after the L0 artifact and an optional real L2
    artifact have been observed.
    """

    tree_path = project_path / "behavior_tree.xml"
    recipe_path = project_path / "recipe.yaml"
    tree_valid = tree_path.is_file()
    recipe_valid = recipe_path.is_file()
    forbidden_found: list[str] = []
    has_simulator_branches = False

    if tree_valid:
        try:
            tree = ElementTree.parse(tree_path)
        except ElementTree.ParseError as error:
            tree_valid = False
            forbidden_found.append(f"tree.parse:{error}")
        else:
            root = tree.getroot()
            forbidden_tags = {
                "IfSim",
                "IfL0",
                "IfL1",
                "IfL2",
                "IfL3",
                "IfHardware",
                "IsSimulation",
                "IsHardware",
                "SimBranch",
                "HardwareBranch",
                "SimulationOnly",
            }
            for elem in root.iter():
                if elem.tag in forbidden_tags:
                    forbidden_found.append(f"<{elem.tag}>")
                for attr_k, attr_v in elem.attrib.items():
                    if "sim" in attr_k.lower() or "sim" in str(attr_v).lower():
                        if attr_k not in {"execution_mode"}:
                            forbidden_found.append(f"{elem.tag}[{attr_k}='{attr_v}']")

    if recipe_valid:
        try:
            recipe_data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            recipe_valid = False
            forbidden_found.append(f"recipe.parse:{error}")
        else:
            if isinstance(recipe_data, dict):

                def _check_recipe_item(item: Any, prefix: str = "recipe") -> None:
                    nonlocal has_simulator_branches
                    if isinstance(item, dict):
                        for key, value in item.items():
                            if "sim" in str(key).lower() or "hardware" in str(key).lower():
                                forbidden_found.append(f"{prefix}.{key}")
                                has_simulator_branches = True
                            _check_recipe_item(value, f"{prefix}.{key}")
                    elif isinstance(item, list):
                        for index, value in enumerate(item):
                            _check_recipe_item(value, f"{prefix}[{index}]")

                _check_recipe_item(recipe_data)

    if forbidden_found:
        has_simulator_branches = True
    passed = tree_valid and recipe_valid and not has_simulator_branches
    details = (
        "Tree and recipe contain no simulator-specific workflow branches."
        if passed
        else (
            "Invalid canonical tree/recipe or simulator-specific branches detected: "
            f"{forbidden_found}"
        )
    )
    return ParityVerificationResult(
        tree_path=str(tree_path),
        recipe_path=str(recipe_path),
        tree_valid=tree_valid,
        recipe_valid=recipe_valid,
        has_simulator_branches=has_simulator_branches,
        forbidden_branch_nodes=tuple(forbidden_found),
        l0_event_count=0,
        l2_event_count=0,
        events_equivalent=False,
        passed=passed,
        details=details,
    )


def _legacy_canonical_dict(report: SoftwareReleaseQualificationReport) -> dict[str, Any]:
    """Return the Task 033 signing payload for old reports without evidence fields."""

    def _scenario(value: ScenarioQualificationResult) -> dict[str, Any]:
        return {
            "scenario_id": value.scenario_id,
            "category": value.category.value,
            "requested_fidelity": value.requested_fidelity,
            "achieved_fidelity": value.achieved_fidelity,
            "seed": value.seed,
            "duration_seconds": value.duration_seconds,
            "trace_event_count": value.trace_event_count,
            "final_status": value.final_status,
            "passed": value.passed,
            "failure_reasons": list(value.failure_reasons),
            "trace_events_summary": list(value.trace_events_summary),
        }

    def _parity(value: ParityVerificationResult) -> dict[str, Any]:
        return {
            "tree_path": value.tree_path,
            "recipe_path": value.recipe_path,
            "tree_valid": value.tree_valid,
            "recipe_valid": value.recipe_valid,
            "has_simulator_branches": value.has_simulator_branches,
            "forbidden_branch_nodes": list(value.forbidden_branch_nodes),
            "l0_event_count": value.l0_event_count,
            "l2_event_count": value.l2_event_count,
            "events_equivalent": value.events_equivalent,
            "passed": value.passed,
            "details": value.details,
        }

    def _platform(value: PlatformQualificationResult) -> dict[str, Any]:
        return {
            "migrations_passed": value.migrations_passed,
            "schema_version": value.schema_version,
            "dual_role_approval_verified": value.dual_role_approval_verified,
            "self_approval_rejected": value.self_approval_rejected,
            "evidence_records_verified": value.evidence_records_verified,
            "offline_buffering_verified": value.offline_buffering_verified,
            "idempotent_sync_verified": value.idempotent_sync_verified,
            "passed": value.passed,
        }

    return {
        "schema_version": report.schema_version,
        "report_id": report.report_id,
        "timestamp": report.timestamp,
        "suite_version": report.suite_version,
        "qualifier_identity": report.qualifier_identity,
        "git_revision": report.git_revision,
        "git_tree_sha": report.git_tree_sha,
        "git_clean": report.git_clean,
        "cell_id": report.cell_id,
        "cell_name": report.cell_name,
        "cell_yaml_sha256": report.cell_yaml_sha256,
        "scene_sha256": report.scene_sha256,
        "components": list(report.components),
        "recipe": dict(report.recipe),
        "bundles": dict(report.bundles),
        "scenarios": [_scenario(s) for s in report.scenarios],
        "parity": _parity(report.parity),
        "platform": _platform(report.platform),
        "limitations": dict(report.limitations),
        "overall_passed": report.overall_passed,
    }


def _ensure_integrity(
    report: SoftwareReleaseQualificationReport,
) -> SoftwareReleaseQualificationReport:
    digest = hashlib.sha256(report._integrity_json().encode("utf-8")).hexdigest()
    return replace(report, integrity_sha256=digest)


def verify_report_integrity(report: SoftwareReleaseQualificationReport) -> bool:
    """Verify the additive SHA-256 integrity seal, when present."""

    return (
        bool(report.integrity_sha256)
        and report.integrity_sha256
        == hashlib.sha256(report._integrity_json().encode("utf-8")).hexdigest()
    )


def sign_qualification_report(
    report: SoftwareReleaseQualificationReport,
    signer_private_key: Ed25519PrivateKey,
    key_id: str = "cellforge-release-qualification-key",
) -> SoftwareReleaseQualificationReport:
    """Cryptographically sign a qualification report using an Ed25519 private key."""

    report = _ensure_integrity(report)
    signature = signer_private_key.sign(report.canonical_json().encode("utf-8"))
    return replace(
        report,
        signature=base64.b64encode(signature).decode("ascii"),
        key_id=key_id,
    )


def verify_qualification_report(
    report: SoftwareReleaseQualificationReport,
    public_key: Ed25519PublicKey,
) -> bool:
    """Verify the report integrity seal and Ed25519 signature.

    Task 033-shaped reports are accepted through the legacy payload fallback when they have no
    additive evidence fields. New reports must verify their integrity seal first.
    """

    if not report.signature:
        return False
    try:
        signature = base64.b64decode(report.signature.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return False
    if report.integrity_sha256 is not None and not verify_report_integrity(report):
        return False
    try:
        public_key.verify(signature, report.canonical_json().encode("utf-8"))
        return True
    except Exception:
        pass
    if report.qualification_command or report.evidence or report.l2 or report.integrity_sha256:
        return False
    try:
        public_key.verify(
            signature,
            json.dumps(
                _legacy_canonical_dict(report), sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
        )
        return True
    except Exception:
        return False


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, document: object) -> tuple[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path), _sha256_file(path)


def _find_repository_root(project_path: Path) -> Path:
    candidates = [project_path.resolve(), *project_path.resolve().parents]
    candidates.extend([Path(__file__).resolve().parents[4], Path.cwd().resolve()])
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate
    return Path(__file__).resolve().parents[4]


def _get_git_info(repo_root: Path) -> tuple[str, str, bool]:
    """Inspect Git revision, tree SHA, and cleanliness without inventing fallback identities."""

    # Git accepts the worktree exception as a path value.  Use Git's portable
    # slash spelling on Windows as well as POSIX so the repository-scoped
    # exception is honored without changing global Git configuration.
    git_args = ["git", "-c", f"safe.directory={repo_root.as_posix()}"]
    try:
        revision = subprocess.check_output(
            [*git_args, "rev-parse", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
        tree = subprocess.check_output(
            [*git_args, "rev-parse", "HEAD^{tree}"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            [*git_args, "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if not revision or not tree:
            return "", "", False
        return revision, tree, not bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        return "", "", False


def _python_path(repo_root: Path) -> str:
    roots = [
        repo_root / "src/python/cellforge_domain/src",
        repo_root / "src/python/cellforge_bundle/src",
        repo_root / "src/python/cellforge_platform/src",
        repo_root / "ros_ws/src/cellforge_device_sdk",
        repo_root / "ros_ws/src/cellforge_mock_adapters",
        repo_root / "ros_ws/src/cellforge_state_trace",
        repo_root / "ros_ws/src/cellforge_job_gateway",
    ]
    existing = [str(path) for path in roots if path.is_dir()]
    current = os.environ.get("PYTHONPATH")
    if current:
        existing.append(current)
    return os.pathsep.join(existing)


def _run_observed_command(
    args: list[str],
    *,
    cwd: Path,
    artifact_path: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    started = time.monotonic()
    command = shlex.join(args)
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        returncode = 124
        stdout = _text_output(error.stdout)
        stderr = _text_output(error.stderr) + "\nqualification command timed out"
    except OSError as error:
        returncode = 127
        stdout = ""
        stderr = f"qualification command could not start: {error}"
    duration = round(time.monotonic() - started, 6)
    document = {
        "command": command,
        "cwd": str(cwd),
        "returncode": returncode,
        "duration_seconds": duration,
        "stdout": stdout,
        "stderr": stderr,
    }
    path, digest = _write_json(artifact_path, document)
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": returncode,
        "duration_seconds": duration,
        "stdout": stdout,
        "stderr": stderr,
        "artifact_path": path,
        "artifact_sha256": digest,
    }


def _text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _run_l0_evidence(
    project_path: Path,
    repo_root: Path,
    evidence_dir: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    # Use a fresh runner directory so a failed invocation can never be paired
    # with a report emitted by an earlier qualification run.
    report_dir = evidence_dir / f"l0-{uuid4().hex}"
    runner = repo_root / "ros_ws/src/cellforge_mock_adapters/cellforge_mock_adapters/headless.py"
    args = [
        sys.executable,
        str(runner),
        "--scenario-root",
        str(project_path / "scenarios"),
        "--tree",
        str(project_path / "behavior_tree.xml"),
        "--reports-dir",
        str(report_dir),
        "--golden-root",
        str(project_path / "golden_traces"),
    ]
    command_evidence = _run_observed_command(
        args,
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": _python_path(repo_root)},
        artifact_path=evidence_dir / "l0-command.json",
    )
    report_path = report_dir / "pen-headless-report.json"
    report_digest = _sha256_file(report_path) if report_path.is_file() else None
    command_evidence["runner_report_path"] = str(report_path)
    command_evidence["runner_report_sha256"] = report_digest
    if not report_path.is_file():
        return command_evidence, {}
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return command_evidence, {}
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
        return command_evidence, {}
    results: dict[str, dict[str, Any]] = {}
    for item in raw["results"]:
        if isinstance(item, dict) and isinstance(item.get("scenario_id"), str):
            results[item["scenario_id"]] = item
    command_evidence["scenario_count"] = raw.get("scenario_count")
    command_evidence["report_passed"] = raw.get("passed")
    return command_evidence, results


def _run_kitting_workflow_evidence(
    project_path: Path,
    repo_root: Path,
    evidence_dir: Path,
) -> dict[str, Any]:
    """Observe the reusable kitting L0 nominal and recovery paths.

    Task 036 remains the pen qualification authority. This additive gate records the Task 038
    workflow as a separate contract-mock observation so it cannot change the pen L2 claim.
    """

    demo_script = repo_root / "scripts" / "run_simulation_demo.py"
    scenarios = (("nominal", 3801), ("gripper_close_recovery", 3802))
    observed: list[dict[str, Any]] = []
    for scenario_name, seed in scenarios:
        output_dir = evidence_dir / f"kitting-{scenario_name}-{uuid4().hex}"
        command_evidence = _run_observed_command(
            [
                sys.executable,
                str(demo_script),
                "--backend",
                "l0",
                "--workflow",
                "kitting",
                "--scenario",
                scenario_name,
                "--seed",
                str(seed),
                "--project-root",
                str(project_path),
                "--output-dir",
                str(output_dir),
            ],
            cwd=repo_root,
            env={**os.environ, "PYTHONPATH": _python_path(repo_root)},
            artifact_path=evidence_dir / f"kitting-{scenario_name}-command.json",
        )
        report_path = output_dir / "report.json"
        report_sha256 = _sha256_file(report_path) if report_path.is_file() else None
        raw: dict[str, Any] = {}
        if report_path.is_file():
            try:
                decoded = json.loads(report_path.read_text(encoding="utf-8"))
                if isinstance(decoded, dict):
                    raw = decoded
            except (OSError, json.JSONDecodeError):
                raw = {}
        assertions = raw.get("assertions", {})
        fidelity = raw.get("fidelity", {})
        result = raw.get("result", {})
        passed = bool(
            command_evidence.get("returncode") == 0
            and isinstance(result, dict)
            and result.get("passed") is True
            and isinstance(fidelity, dict)
            and fidelity.get("requested") == "L0"
            and fidelity.get("achieved") == "L0"
            and fidelity.get("actual_physx_executed") is False
        )
        observed.append(
            {
                "scenario": scenario_name,
                "seed": seed,
                "status": "passed" if passed else "failed",
                "requested_fidelity": (
                    fidelity.get("requested") if isinstance(fidelity, dict) else None
                ),
                "achieved_fidelity": (
                    fidelity.get("achieved") if isinstance(fidelity, dict) else None
                ),
                "actual_physx_executed": (
                    fidelity.get("actual_physx_executed") if isinstance(fidelity, dict) else None
                ),
                "assertions_passed": (
                    assertions.get("passed") if isinstance(assertions, dict) else None
                ),
                "command": command_evidence.get("command"),
                "command_artifact_path": command_evidence.get("artifact_path"),
                "command_artifact_sha256": command_evidence.get("artifact_sha256"),
                "report_artifact_path": str(report_path),
                "report_artifact_sha256": report_sha256,
                "project_sha256": (
                    raw.get("project", {}).get("project_sha256")
                    if isinstance(raw.get("project"), dict)
                    else None
                ),
                "selected_adapters": raw.get("selected_adapters", []),
                "limitations": raw.get("limitations", {}),
            }
        )
    workflow_passed = all(item["status"] == "passed" for item in observed)
    return {
        "gate": "kitting_workflow_l0",
        "workflow": "kitting",
        "status": "passed" if workflow_passed else "failed",
        "project_path": str(project_path),
        "scenarios": observed,
        "limitations": (
            "L0 contract-mock evidence only; no kitting L1/L2 adapter was available. "
            "This gate does not alter the pen workflow's Task 027 L2 qualification."
        ),
    }


def _scenario_result_from_l0(
    raw: dict[str, Any] | None,
    *,
    expected_scenario_id: str,
    category: QualificationCategory,
    command_evidence: dict[str, Any],
) -> ScenarioQualificationResult:
    reasons: list[str] = []
    if raw is None:
        reasons.append("L0 runner did not emit this scenario artifact row.")
        return ScenarioQualificationResult(
            scenario_id=expected_scenario_id,
            category=category,
            requested_fidelity="L0",
            achieved_fidelity="",
            seed=0,
            duration_seconds=0.0,
            trace_event_count=0,
            final_status="UNAVAILABLE",
            passed=False,
            failure_reasons=tuple(reasons),
            observed=False,
            available=False,
            command=str(command_evidence.get("command", "")),
            artifact_path=command_evidence.get("runner_report_path"),
            artifact_sha256=command_evidence.get("runner_report_sha256"),
        )
    scenario_id = str(raw.get("scenario_id", ""))
    seed_value = raw.get("seed")
    seed = (
        int(seed_value) if isinstance(seed_value, int) and not isinstance(seed_value, bool) else 0
    )
    trace = raw.get("trace")
    trace_events = trace if isinstance(trace, list) else []
    summary = tuple(
        str(event.get("event_type"))
        for event in trace_events
        if isinstance(event, dict) and isinstance(event.get("event_type"), str)
    )
    if not isinstance(raw.get("passed"), bool):
        reasons.append("L0 runner row has no boolean passed field.")
    if not isinstance(raw.get("final_status"), str):
        reasons.append("L0 runner row has no final status.")
    if not isinstance(raw.get("fidelity"), str) or not str(raw.get("fidelity")).startswith("L0"):
        reasons.append("L0 runner row did not identify the L0 contract-mock backend.")
    raw_failures = raw.get("failures")
    if isinstance(raw_failures, list):
        reasons.extend(str(item) for item in raw_failures)
    else:
        reasons.append("L0 runner row has no failure list.")
    passed = raw.get("passed") is True and not reasons
    return ScenarioQualificationResult(
        scenario_id=scenario_id,
        category=category,
        requested_fidelity="L0",
        achieved_fidelity="L0" if not reasons else "",
        seed=seed,
        duration_seconds=0.0,
        trace_event_count=len(trace_events),
        final_status=str(raw.get("final_status", "UNAVAILABLE")),
        passed=passed,
        failure_reasons=tuple(reasons),
        trace_events_summary=summary,
        observed=True,
        available=True,
        command=str(command_evidence.get("command", "")),
        artifact_path=command_evidence.get("runner_report_path"),
        artifact_sha256=command_evidence.get("runner_report_sha256"),
        evidence={
            "backend": "L0 contract mock",
            "runner_report_sha256": command_evidence.get("runner_report_sha256"),
            "runner_duration_seconds": command_evidence.get("duration_seconds"),
        },
    )


def _run_platform_evidence(repo_root: Path, evidence_dir: Path) -> PlatformQualificationResult:
    script = repo_root / "scripts/verify_platform_approvals_result_sync.py"
    command_evidence = _run_observed_command(
        [sys.executable, str(script)],
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": _python_path(repo_root)},
        artifact_path=evidence_dir / "platform-command.json",
    )
    stdout = str(command_evidence.get("stdout", ""))
    markers = {
        "migrations_passed": "[OK] Reversible database migrations 3 & 4 verified.",
        "dual_role_approval_verified": (
            "[OK] Dual-role approval and creator self-approval rejection verified."
        ),
        "evidence_records_verified": (
            "[OK] Content-addressed evidence and cryptographic snapshot signature verified."
        ),
        "offline_buffering_verified": (
            "[OK] Zero duplicate records on replay and full acknowledgment verified."
        ),
        "idempotent_sync_verified": (
            "[OK] Zero duplicate records on replay and full acknowledgment verified."
        ),
    }
    checks = {name: marker in stdout for name, marker in markers.items()}
    failures = [name for name, passed in checks.items() if not passed]
    if command_evidence.get("returncode") != 0:
        failures.append(f"platform command returned {command_evidence.get('returncode')}")
    return PlatformQualificationResult(
        migrations_passed=checks["migrations_passed"],
        schema_version=4 if checks["migrations_passed"] else 0,
        dual_role_approval_verified=checks["dual_role_approval_verified"],
        self_approval_rejected=checks["dual_role_approval_verified"],
        evidence_records_verified=checks["evidence_records_verified"],
        offline_buffering_verified=checks["offline_buffering_verified"],
        idempotent_sync_verified=checks["idempotent_sync_verified"],
        passed=not failures,
        observed=command_evidence.get("returncode") is not None,
        command=str(command_evidence.get("command", "")),
        artifact_path=str(command_evidence.get("artifact_path", "")),
        artifact_sha256=str(command_evidence.get("artifact_sha256", "")),
        failure_reasons=tuple(failures),
    )


def _run_bundle_evidence(
    project_path: Path,
    schemas_path: Path,
    source_revision: str,
    evidence_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from cellforge_domain import ExecutionMode
    from cryptography.hazmat.primitives import serialization

    from cellforge_bundle.agent import verify_bundle
    from cellforge_bundle.assembly import assemble_bundle

    result: dict[str, Any] = {
        "passed": False,
        "observed": False,
        "fidelity": "L0",
        "target_profile": "pen-sim-amd64",
        "source_revision": source_revision,
    }
    if not source_revision:
        result["failure_reasons"] = [
            "Git revision was unavailable; bundle assembly was not attempted."
        ]
        return result, {}
    key = Ed25519PrivateKey.generate()
    key_path = evidence_dir / "bundle-signing-key.pem"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key_id = _sha256_bytes(public_bytes)
    trusted_dir = evidence_dir / "trusted-keys"
    trusted_dir.mkdir(parents=True, exist_ok=True)
    (trusted_dir / f"{key_id}.pub").write_bytes(public_bytes)
    # Keep each invocation isolated so a second qualification run cannot reuse
    # a previous bundle directory or accidentally report stale evidence.
    run_id = uuid4().hex
    bundle_path = evidence_dir / f"assembled-l0-bundle-{run_id}"
    probe_path = evidence_dir / "bundle-probe.json"
    failures: list[str] = []
    try:
        assembled = assemble_bundle(
            project_path,
            schemas_path,
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.SIMULATION,
            source_revision=source_revision,
            output=bundle_path,
            signing_key=key_path,
        )
        verified = verify_bundle(assembled.output, trusted_keys=trusted_dir, require_signature=True)
        tampered_path = evidence_dir / f"tampered-l0-bundle-{run_id}"
        shutil.copytree(assembled.output, tampered_path)
        launch_path = tampered_path / "config" / "launch.json"
        launch_path.write_bytes(launch_path.read_bytes() + b"\n")
        tamper_rejected = False
        try:
            verify_bundle(tampered_path, trusted_keys=trusted_dir, require_signature=True)
        except Exception:
            tamper_rejected = True
        if not tamper_rejected:
            failures.append("Tampered assembled bundle was not rejected by the agent verifier.")
        result.update(
            {
                "observed": True,
                "passed": not failures,
                "bundle_id": verified.bundle_id,
                "key_id": key_id,
                "tamper_rejected": tamper_rejected,
                "bundle_path": str(assembled.output),
                "manifest_sha256": _sha256_file(assembled.output / "manifest.json"),
                "checksums_sha256": _sha256_file(assembled.output / "checksums.txt"),
            }
        )
    except Exception as error:
        failures.append(f"bundle assembly or verification failed: {error}")
        result["observed"] = True
        result["passed"] = False
    result["failure_reasons"] = failures
    path, digest = _write_json(probe_path, result)
    evidence = {
        "gate": "bundle_agent",
        "status": "passed" if result["passed"] else "failed",
        "command": (
            "cellforge_bundle.assembly.assemble_bundle + cellforge_bundle.agent.verify_bundle"
        ),
        "artifact_path": path,
        "artifact_sha256": digest,
    }
    return result, evidence


def _run_restart_evidence(
    repo_root: Path, evidence_dir: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        _add_ros_python_paths(repo_root)
        from cellforge_device_sdk.contract import ContractScenario
        from cellforge_mock_adapters.devices import make_contract_factory
        from cellforge_mock_adapters.scenarios import DeviceKind

        adapter = make_contract_factory(DeviceKind.ROBOT)(ContractScenario.NOMINAL)
        adapter.mark_ready()
        reconciliation = asyncio.run(adapter.reconcile_after_restart())
        result: dict[str, Any] = {
            "observed": True,
            "passed": reconciliation.ready and reconciliation.outcome_certain,
            "state": reconciliation.state.value,
            "ready": reconciliation.ready,
            "outcome_certain": reconciliation.outcome_certain,
            "details": dict(reconciliation.details),
        }
    except Exception as error:
        result = {"observed": True, "passed": False, "failure_reasons": [str(error)]}
    path, digest = _write_json(evidence_dir / "restart-probe.json", result)
    evidence = {
        "gate": "restart",
        "status": "passed" if result.get("passed") else "failed",
        "command": "cellforge_device_sdk BaseDeviceAdapter.reconcile_after_restart",
        "artifact_path": path,
        "artifact_sha256": digest,
    }
    return result, evidence


def _run_stale_device_evidence(
    repo_root: Path, evidence_dir: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        _add_ros_python_paths(repo_root)
        from cellforge_state_trace.state_logic import (
            DeviceStateEntry,
            compute_top_level_cell_state,
            evaluate_required_devices,
        )

        entry = DeviceStateEntry(
            component_instance_id="laser-001",
            state="READY",
            ready=True,
            heartbeat_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        all_ready, any_stale = evaluate_required_devices({"laser-001": entry}, {"laser-001"})
        cell_state = compute_top_level_cell_state(
            all_required_ready=all_ready,
            safety_healthy=True,
            any_faulted=False,
            any_busy=False,
            any_required_stale=any_stale,
        )
        result = {
            "observed": True,
            "passed": entry.stale and not all_ready and any_stale and cell_state == "STARTING",
            "device_id": entry.component_instance_id,
            "stale": entry.stale,
            "all_required_ready": all_ready,
            "any_required_stale": any_stale,
            "cell_state": cell_state,
            "expected_job_status": "REJECTED",
        }
    except Exception as error:
        result = {"observed": True, "passed": False, "failure_reasons": [str(error)]}
    path, digest = _write_json(evidence_dir / "stale-device-probe.json", result)
    evidence = {
        "gate": "stale_device",
        "status": "passed" if result.get("passed") else "failed",
        "command": "cellforge_state_trace.state_logic.evaluate_required_devices",
        "artifact_path": path,
        "artifact_sha256": digest,
    }
    return result, evidence


def _add_ros_python_paths(repo_root: Path) -> None:
    for path in reversed(
        [
            repo_root / "ros_ws/src/cellforge_device_sdk",
            repo_root / "ros_ws/src/cellforge_mock_adapters",
            repo_root / "ros_ws/src/cellforge_state_trace",
        ]
    ):
        if path.is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))


def validate_task027_l2_report(
    report_path: Path | None,
    project_path: Path,
    *,
    expected_source_revision: str = "",
    expected_cell_id: str = "",
) -> dict[str, Any]:
    """Validate the external Task 027 actual-PhysX seed-report contract.

    The validator accepts only the supported Isaac Sim 6 seed-report format. It does not run a
    simulator and it never converts CPU/model output into L2. The canonical scene digest binds
    the external report to the current project; optional source/tree/recipe identities, when
    present in future Task 027 reports, are checked as well.
    """

    base: dict[str, Any] = {
        "status": "unavailable" if report_path is None else "failed",
        "available": False,
        "passed": False,
        "actual_physx_executed": False,
        "event_origin": None,
        "backend": None,
        "fidelity": "unavailable",
        "failure_reasons": [],
    }
    if report_path is None:
        base["failure_reasons"] = ["No external Task 027 actual-PhysX report was supplied."]
        return base
    path = report_path.resolve()
    base["report_path"] = str(path)
    if not path.is_file():
        base["failure_reasons"] = [f"Task 027 report does not exist: {path}"]
        return base
    base["available"] = True
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        base["failure_reasons"] = [f"Task 027 report is not valid JSON: {error}"]
        return base
    base["report_sha256"] = _sha256_file(path)
    if not isinstance(raw, dict):
        base["failure_reasons"] = ["Task 027 report root must be an object."]
        return base
    failures: list[str] = []
    if raw.get("schema_version") != "0.1.0":
        failures.append("Task 027 report schema_version must be 0.1.0.")
    if raw.get("kind") != _L2_REPORT_KIND:
        failures.append(f"Task 027 report kind must be {_L2_REPORT_KIND!r}.")
    version = raw.get("isaac_version")
    base["isaac_version"] = version
    if not isinstance(version, str) or not version.startswith("6."):
        failures.append("L2 evidence must identify a supported Isaac Sim 6 version.")
    gpu = raw.get("gpu")
    base["gpu"] = dict(gpu) if isinstance(gpu, dict) else {}
    if (
        not isinstance(gpu, dict)
        or gpu.get("is_cuda") is not True
        or not isinstance(gpu.get("name"), str)
    ):
        failures.append("L2 evidence must identify an NVIDIA CUDA GPU; CPU fallback is forbidden.")
    actual_physx = raw.get("actual_physx_executed")
    base["actual_physx_executed"] = actual_physx
    if actual_physx is not True:
        failures.append("Task 027 report does not prove actual PhysX execution.")
    event_origin = raw.get("event_origin")
    base["event_origin"] = event_origin
    if event_origin != "runtime/adapters":
        failures.append("L2 event origin must be runtime/adapters.")

    scene_path_raw = raw.get("scene")
    base["scene_path"] = scene_path_raw
    canonical_scene = project_path / "scene.usda"
    expected_scene_sha = _sha256_file(canonical_scene) if canonical_scene.is_file() else ""
    reported_scene_sha = raw.get("scene_sha256")
    base["scene_sha256"] = reported_scene_sha
    if not isinstance(reported_scene_sha, str) or reported_scene_sha != expected_scene_sha:
        failures.append("Task 027 scene_sha256 does not match the canonical project scene.")
    if not isinstance(scene_path_raw, str) or not scene_path_raw:
        failures.append("Task 027 report does not identify its source scene path.")
    elif (
        Path(scene_path_raw).is_file() and _sha256_file(Path(scene_path_raw)) != expected_scene_sha
    ):
        failures.append(
            "Task 027 report scene path resolves to content different from the canonical scene."
        )

    for identity_key, expected in (
        ("source_revision", expected_source_revision),
        ("git_revision", expected_source_revision),
        ("cell_id", expected_cell_id),
    ):
        if identity_key in raw and expected and raw.get(identity_key) != expected:
            failures.append(f"Task 027 report {identity_key} does not match the qualified source.")
    if "behavior_tree_sha256" in raw:
        tree_path = project_path / "behavior_tree.xml"
        if tree_path.is_file() and raw.get("behavior_tree_sha256") != _sha256_file(tree_path):
            failures.append("Task 027 behavior-tree digest does not match the canonical tree.")
    if "recipe_sha256" in raw:
        recipe_path = project_path / "recipe.yaml"
        if recipe_path.is_file() and raw.get("recipe_sha256") != _sha256_file(recipe_path):
            failures.append("Task 027 recipe digest does not match the canonical recipe.")

    summary = raw.get("summary")
    if not isinstance(summary, dict) or summary.get("passed") != 100 or summary.get("failed") != 0:
        failures.append("Task 027 report must record 100 passed and 0 failed seeded runs.")
    seed_range = raw.get("seed_range")
    if (
        not isinstance(seed_range, dict)
        or seed_range.get("first") != 0
        or seed_range.get("count") != 100
    ):
        failures.append("Task 027 report must cover seed range 0..99.")
    runs = raw.get("runs")
    if not isinstance(runs, list) or len(runs) != 100:
        failures.append("Task 027 report must contain exactly 100 seeded run records.")
        runs = []
    seeds: list[int] = []
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            failures.append(f"Task 027 run {index} is not an object.")
            continue
        seed = run.get("seed")
        if isinstance(seed, int) and not isinstance(seed, bool):
            seeds.append(seed)
        else:
            failures.append(f"Task 027 run {index} has no integer seed.")
        if run.get("actual_physx_executed") is not True:
            failures.append(f"Task 027 run {index} is not marked actual PhysX.")
        if run.get("achieved_fidelity") != "L2":
            failures.append(f"Task 027 run {index} is not labeled L2.")
        if run.get("backend") != _L2_BACKEND:
            failures.append(f"Task 027 run {index} does not identify the supported PhysX backend.")
        if run.get("event_origin") != "runtime/adapters":
            failures.append(f"Task 027 run {index} is not runtime/adapter evidence.")
        events = run.get("events")
        if not isinstance(events, list) or not events:
            failures.append(f"Task 027 run {index} has no observed runtime events.")
        elif not any(
            isinstance(event, dict) and event.get("origin") == "isaac_l2_adapter"
            for event in events
        ):
            failures.append(f"Task 027 run {index} has no Isaac adapter-originated event.")
    if sorted(seeds) != list(range(100)):
        failures.append("Task 027 seeded run identities are not the exact unique range 0..99.")
    replay = raw.get("replay_sha256")
    encoded_runs = json.dumps(runs, sort_keys=True, separators=(",", ":")).encode()
    if not isinstance(replay, str) or replay != _sha256_bytes(encoded_runs):
        failures.append("Task 027 replay_sha256 does not match the observed run records.")

    fault_scenarios = raw.get("fault_scenarios")
    observed_faults: set[str] = set()
    if not isinstance(fault_scenarios, list):
        failures.append("Task 027 report has no fault_scenarios list.")
        fault_scenarios = []
    for fault in fault_scenarios:
        if not isinstance(fault, dict):
            continue
        code = fault.get("result_code")
        if isinstance(code, str):
            observed_faults.add(code)
        if (
            fault.get("actual_physx_executed") is not True
            or fault.get("event_origin") != "runtime/adapters"
            or fault.get("achieved_fidelity") != "L2"
            or fault.get("backend") != _L2_BACKEND
        ):
            failures.append("Task 027 fault evidence is not actual runtime/adapter PhysX evidence.")
        if not isinstance(fault.get("events"), list) or not fault.get("events"):
            failures.append("Task 027 fault evidence has no observed events.")
    missing_faults = sorted(_L2_FAULT_CODES - observed_faults)
    if missing_faults:
        failures.append(f"Task 027 report is missing required PhysX faults: {missing_faults}.")
    base["seed_count"] = len(runs)
    base["fault_codes"] = sorted(observed_faults)
    base["replay_sha256"] = replay
    base["source_identity"] = {
        "canonical_scene_sha256": expected_scene_sha,
        "external_source_revision_present": "source_revision" in raw or "git_revision" in raw,
        "external_cell_id_present": "cell_id" in raw,
    }
    base["failure_reasons"] = failures
    base["status"] = "passed" if not failures else "failed"
    base["passed"] = not failures
    if base["passed"]:
        base["backend"] = _L2_BACKEND
        base["fidelity"] = "L2"
    return base


def _component_inventory(
    project_path: Path, cell_data: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    components: list[dict[str, Any]] = []
    for component in cell_data.get("components", []):
        if not isinstance(component, dict):
            continue
        component_id = component.get("component")
        manifest_path: Path | None = None
        for candidate in sorted((project_path / "components").glob("*/component.yaml")):
            try:
                manifest = yaml.safe_load(candidate.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if (
                isinstance(manifest, dict)
                and manifest.get("component", {}).get("id") == component_id
            ):
                manifest_path = candidate
                break
        manifest_data: dict[str, Any] = {}
        if manifest_path is not None:
            try:
                decoded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                if isinstance(decoded, dict):
                    manifest_data = decoded
            except (OSError, yaml.YAMLError):
                pass
        component_meta = manifest_data.get("component", {})
        support = manifest_data.get("support", {})
        components.append(
            {
                "id": component.get("id"),
                "alias": component.get("alias"),
                "component": component_id,
                "version": component.get("version"),
                "manifest_version": component_meta.get("version"),
                "support_level": support.get("level", "unavailable"),
                "simulation_level": support.get("simulation_level", "unavailable"),
                "manifest_sha256": _sha256_file(manifest_path) if manifest_path else None,
            }
        )
    return tuple(components)


def run_software_release_qualification(
    project_path: Path,
    schemas_path: Path,
    *,
    signing_key: Ed25519PrivateKey | None = None,
    key_id: str = "cellforge-release-qualification-key",
    l2_report_path: Path | None = None,
    evidence_dir: Path | None = None,
    repository_root: Path | None = None,
    qualification_command: str | None = None,
    kitting_project_path: Path | None = None,
) -> SoftwareReleaseQualificationReport:
    """Execute the qualification gates and build a truthful report from observed evidence."""

    project_path = project_path.resolve()
    schemas_path = schemas_path.resolve()
    repo_root = (repository_root or _find_repository_root(project_path)).resolve()
    evidence_root = (evidence_dir or repo_root / ".artifacts" / "task036").resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    rev, tree_sha, is_clean = _get_git_info(repo_root)

    cell_yaml_path = project_path / "cell.yaml"
    scene_path = project_path / "scene.usda"
    recipe_yaml_path = project_path / "recipe.yaml"
    cell_bytes = cell_yaml_path.read_bytes()
    scene_bytes = scene_path.read_bytes()
    recipe_bytes = recipe_yaml_path.read_bytes()
    cell_sha = _sha256_bytes(cell_bytes)
    scene_sha = _sha256_bytes(scene_bytes)
    recipe_sha = _sha256_bytes(recipe_bytes)
    cell_data_raw = yaml.safe_load(cell_bytes)
    recipe_data_raw = yaml.safe_load(recipe_bytes)
    cell_data = cell_data_raw if isinstance(cell_data_raw, dict) else {}
    recipe_data = recipe_data_raw if isinstance(recipe_data_raw, dict) else {}
    cell_section = cell_data.get("cell", {}) if isinstance(cell_data.get("cell", {}), dict) else {}
    recipe_section = (
        recipe_data.get("recipe", {}) if isinstance(recipe_data.get("recipe", {}), dict) else {}
    )
    cell_id = str(cell_section.get("id", ""))
    cell_name = str(cell_section.get("name", ""))

    parity_static = verify_tree_and_recipe_parity(project_path)
    l0_command, l0_rows = _run_l0_evidence(project_path, repo_root, evidence_root)
    category_by_id: dict[str, QualificationCategory] = {
        "pen-nominal": QualificationCategory.NOMINAL,
        "pen-no-pen": QualificationCategory.FAULT,
        "pen-pose-outside-limit": QualificationCategory.FAULT,
        "pen-fixture-not-seated": QualificationCategory.FAULT,
        "pen-laser-not-ready": QualificationCategory.FAULT,
        "pen-inspection-text-mismatch": QualificationCategory.FAULT,
        "pen-laser-timeout": QualificationCategory.TIMEOUT,
        "pen-operator-cancel": QualificationCategory.CANCEL,
        "pen-process-outcome-unknown": QualificationCategory.UNCERTAIN_PROCESS,
        "pen-safety-unhealthy": QualificationCategory.FAULT,
    }
    scenarios = [
        _scenario_result_from_l0(
            row,
            expected_scenario_id=scenario_id,
            category=category,
            command_evidence=l0_command,
        )
        for scenario_id, category in category_by_id.items()
        for row in [l0_rows.get(scenario_id)]
    ]

    bundle_result, bundle_evidence = _run_bundle_evidence(
        project_path, schemas_path, rev, evidence_root
    )
    restart_result, restart_evidence = _run_restart_evidence(repo_root, evidence_root)
    stale_result, stale_evidence = _run_stale_device_evidence(repo_root, evidence_root)
    platform_result = _run_platform_evidence(repo_root, evidence_root)
    kitting_evidence = (
        _run_kitting_workflow_evidence(kitting_project_path.resolve(), repo_root, evidence_root)
        if kitting_project_path is not None
        else None
    )

    def _probe_scenario(
        scenario_id: str,
        category: QualificationCategory,
        result: dict[str, Any],
        evidence: dict[str, Any],
        *,
        final_status: str,
        seed: int,
    ) -> ScenarioQualificationResult:
        passed = result.get("passed") is True
        reasons = tuple(str(item) for item in result.get("failure_reasons", []))
        if not passed and not reasons:
            reasons = (f"{category.value} probe did not satisfy its expected outcome.",)
        return ScenarioQualificationResult(
            scenario_id=scenario_id,
            category=category,
            requested_fidelity="L0",
            achieved_fidelity="L0" if passed else "",
            seed=seed,
            duration_seconds=float(result.get("duration_seconds", 0.0)),
            trace_event_count=int(result.get("trace_event_count", 0)),
            final_status=final_status if passed else "RECOVERABLE_FAULT",
            passed=passed,
            failure_reasons=reasons,
            trace_events_summary=tuple(str(item) for item in result.get("events", [])),
            observed=result.get("observed") is True,
            available=True,
            command=str(evidence.get("command", "")),
            artifact_path=evidence.get("artifact_path"),
            artifact_sha256=evidence.get("artifact_sha256"),
            evidence={"probe": evidence.get("gate")},
        )

    scenarios.extend(
        [
            _probe_scenario(
                "runtime-service-restart",
                QualificationCategory.RESTART,
                restart_result,
                restart_evidence,
                final_status="SUCCESS",
                seed=1005,
            ),
            _probe_scenario(
                "bundle-tampering-rejection",
                QualificationCategory.CORRUPT_BUNDLE,
                bundle_result,
                bundle_evidence,
                final_status="REJECTED",
                seed=0,
            ),
            _probe_scenario(
                "offline-runtime-buffering",
                QualificationCategory.OFFLINE_PLATFORM,
                {
                    "observed": platform_result.observed,
                    "passed": platform_result.offline_buffering_verified
                    and platform_result.idempotent_sync_verified,
                },
                {
                    "gate": "platform_offline_sync",
                    "command": platform_result.command,
                    "artifact_path": platform_result.artifact_path,
                    "artifact_sha256": platform_result.artifact_sha256,
                },
                final_status="SUCCESS",
                seed=1006,
            ),
            _probe_scenario(
                "pen-stale-device-unready",
                QualificationCategory.STALE_DEVICE,
                stale_result,
                stale_evidence,
                final_status="REJECTED",
                seed=1007,
            ),
        ]
    )

    l2 = validate_task027_l2_report(
        l2_report_path,
        project_path,
        expected_source_revision=rev,
        expected_cell_id=cell_id,
    )
    l2_nominal_events = 0
    if l2.get("passed") and isinstance(l2.get("report_path"), str):
        try:
            l2_raw = json.loads(Path(str(l2["report_path"])).read_text(encoding="utf-8"))
            runs = l2_raw.get("runs", []) if isinstance(l2_raw, dict) else []
            if isinstance(runs, list) and runs and isinstance(runs[0], dict):
                l2_nominal_events = len(runs[0].get("events", []))
        except (OSError, json.JSONDecodeError):
            l2_nominal_events = 0
    parity = replace(
        parity_static,
        l0_event_count=next(
            (
                scenario.trace_event_count
                for scenario in scenarios
                if scenario.scenario_id == "pen-nominal"
            ),
            0,
        ),
        l2_event_count=l2_nominal_events,
        events_equivalent=bool(parity_static.passed and l2.get("passed") and l2_nominal_events > 0),
        dynamic_observed=bool(l0_command.get("report_passed") is not None),
        l2_available=bool(l2.get("passed")),
        l2_validation=dict(l2),
        details=(
            parity_static.details
            + (
                " L0 runner evidence observed; Task 027 L2 evidence validated."
                if l2.get("passed")
                else " L2 remains unavailable or failed validation; no L2 result was synthesized."
            )
        ),
    )

    components = _component_inventory(project_path, cell_data)
    bundles = {
        "l0_sim": bundle_result,
        "l2_isaac": {
            "status": l2.get("status"),
            "report_path": l2.get("report_path"),
            "report_sha256": l2.get("report_sha256"),
            "actual_physx_executed": l2.get("actual_physx_executed"),
            "fidelity": "L2" if l2.get("passed") else "unavailable",
        },
    }
    if kitting_evidence is not None:
        bundles["kitting_l0"] = {
            "status": kitting_evidence["status"],
            "workflow": "kitting",
            "fidelity": "L0",
            "scenarios": [item["scenario"] for item in kitting_evidence["scenarios"]],
        }
    evidence_items: list[dict[str, Any]] = [
        {
            "gate": "source_provenance",
            "status": "passed" if rev and tree_sha and is_clean else "failed",
            "revision": rev,
            "tree_sha": tree_sha,
            "git_clean": is_clean,
        },
        {
            "gate": "l0_scenarios",
            "status": "passed"
            if l0_command.get("returncode") == 0 and l0_command.get("report_passed") is True
            else "failed",
            "command": l0_command.get("command"),
            "artifact_path": l0_command.get("runner_report_path"),
            "artifact_sha256": l0_command.get("runner_report_sha256"),
            "command_artifact_path": l0_command.get("artifact_path"),
            "command_artifact_sha256": l0_command.get("artifact_sha256"),
        },
        bundle_evidence,
        {
            "gate": "platform",
            "status": "passed" if platform_result.passed else "failed",
            "command": platform_result.command,
            "artifact_path": platform_result.artifact_path,
            "artifact_sha256": platform_result.artifact_sha256,
        },
        restart_evidence,
        stale_evidence,
        {
            "gate": "l2_physx",
            "status": l2.get("status"),
            "report_path": l2.get("report_path"),
            "report_sha256": l2.get("report_sha256"),
            "failure_reasons": l2.get("failure_reasons", []),
        },
    ]
    if kitting_evidence is not None:
        evidence_items.append(kitting_evidence)
    evidence = tuple(evidence_items)
    required_category_set = {scenario.category.value for scenario in scenarios}
    all_scenarios_observed = (
        required_category_set == _REQUIRED_CATEGORY_VALUES
        and l0_command.get("returncode") == 0
        and l0_command.get("report_passed") is True
        and all(item.observed and item.available and item.passed for item in scenarios)
    )
    provenance_passed = bool(rev and tree_sha and is_clean)
    overall_passed = bool(
        provenance_passed
        and parity.passed
        and parity.events_equivalent
        and platform_result.passed
        and bundle_result.get("passed") is True
        and all_scenarios_observed
        and l2.get("passed") is True
        and (kitting_evidence is None or kitting_evidence["status"] == "passed")
    )
    limitations = {
        **QUALIFICATION_DISCLAIMERS,
        "l2_availability": (
            "Task 027 actual Isaac Sim 6/OpenUSD/PhysX seed evidence was validated."
            if l2.get("passed")
            else (
                "No valid external Task 027 actual-PhysX report was supplied; "
                "L2 is unavailable and full qualification is false."
            )
        ),
    }
    if kitting_evidence is not None:
        limitations["kitting_workflow"] = str(kitting_evidence["limitations"])
    report = SoftwareReleaseQualificationReport(
        report_id=str(uuid4()),
        timestamp=datetime.now(UTC).isoformat(),
        suite_version="0.2.0",
        qualifier_identity="CellForge Executable Release Qualification Suite v0.2.0",
        git_revision=rev,
        git_tree_sha=tree_sha,
        git_clean=is_clean,
        cell_id=cell_id,
        cell_name=cell_name,
        cell_yaml_sha256=cell_sha,
        scene_sha256=scene_sha,
        components=components,
        recipe={
            "id": recipe_section.get("id"),
            "version": recipe_section.get("version"),
            "sha256": recipe_sha,
            "status": recipe_section.get("status"),
            "approval_evidence": recipe_data.get("approval", {}).get("evidence", [])
            if isinstance(recipe_data.get("approval", {}), dict)
            else [],
        },
        bundles=bundles,
        scenarios=tuple(scenarios),
        parity=parity,
        platform=platform_result,
        limitations=limitations,
        overall_passed=overall_passed,
        qualification_command=qualification_command
        or "python scripts/verify_software_release_qualification.py",
        evidence=evidence,
        l2=l2,
    )
    report = _ensure_integrity(report)
    if signing_key is not None:
        report = sign_qualification_report(report, signing_key, key_id=key_id)
    return report
