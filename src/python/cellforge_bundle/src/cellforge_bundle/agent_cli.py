"""Local command-line interface for the CellForge bundle agent."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from cellforge_bundle.agent import (
    AgentError,
    AgentPaths,
    BundleAgent,
    SystemdServiceManager,
    install_systemd_units,
    preflight_target,
    verify_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cellforge-bundle-agent")
    parser.add_argument("--install-root", type=Path, default=Path("/opt/cellforge"))
    parser.add_argument("--state-root", type=Path, default=Path("/var/lib/cellforge"))
    parser.add_argument("--secret-store", type=Path, default=Path("/etc/cellforge/secrets"))
    parser.add_argument("--target-facts", type=Path, default=Path("/etc/cellforge/target.json"))
    parser.add_argument("--trusted-keys", type=Path, default=Path("/etc/cellforge/trusted-keys"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="verify, install, and activate a bundle")
    install.add_argument("bundle", type=Path)
    subparsers.add_parser(
        "prepare-active", help="verify active release and refresh local environment"
    )
    subparsers.add_parser("rollback", help="activate the previous known-good release")
    status = subparsers.add_parser("status", help="show local release and runtime status")
    status.add_argument("--json", action="store_true", dest="json_output")
    verify = subparsers.add_parser("verify", help="verify a bundle and target compatibility")
    verify.add_argument("bundle", type=Path)
    systemd = subparsers.add_parser("install-systemd", help="install packaged systemd units")
    systemd.add_argument("--unit-directory", type=Path, default=Path("/etc/systemd/system"))
    systemd.add_argument("--force", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(arguments)
    paths = AgentPaths(
        install_root=options.install_root,
        state_root=options.state_root,
        secret_store=options.secret_store,
        target_facts=options.target_facts,
        trusted_keys=options.trusted_keys,
    )
    try:
        if options.command == "install-systemd":
            installed = install_systemd_units(
                options.unit_directory, SystemdServiceManager(), force=options.force
            )
            for path in installed:
                print(path)
            return 0
        if options.command == "verify":
            bundle = verify_bundle(
                options.bundle, trusted_keys=options.trusted_keys, require_signature=True
            )
            preflight_target(bundle, paths.target_facts)
            print(f"verified bundle {bundle.bundle_id}")
            return 0

        agent = BundleAgent(paths)
        if options.command == "install":
            status = agent.install(options.bundle)
        elif options.command == "prepare-active":
            status = agent.prepare_active()
        elif options.command == "rollback":
            status = agent.rollback()
        elif options.command == "status":
            status = agent.status()
        else:  # pragma: no cover - argparse makes this unreachable
            parser.error("unknown command")
        document = status.to_document()
        if getattr(options, "json_output", False):
            print(json.dumps(document, sort_keys=True))
        else:
            print(f"active_bundle_id: {status.active_bundle_id or '-'}")
            print(f"service_unit: {status.service_unit or '-'}")
            print(f"service_active: {str(status.service_active).lower()}")
            print(f"last_result: {status.last_result or '-'}")
            print(f"last_error: {status.last_error or '-'}")
            print(f"releases: {len(status.release_ids)}")
        return 0
    except AgentError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
