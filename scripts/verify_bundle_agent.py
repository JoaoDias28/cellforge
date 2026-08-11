"""Static Task 021 integration contract check."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    required_units = {
        "cellforge-bundle-agent.service",
        "cellforge-runtime.service",
        "cellforge-runtime.target",
    }
    unit_root = (
        root / "src" / "python" / "cellforge_bundle" / "src" / "cellforge_bundle" / "systemd"
    )
    actual_units = {path.name for path in unit_root.iterdir() if path.is_file()}
    if actual_units != required_units:
        print("systemd unit inventory does not match Task 021", file=sys.stderr)
        return 1
    runtime = (unit_root / "cellforge-runtime.service").read_text(encoding="utf-8")
    required_runtime_lines = {
        "EnvironmentFile=/var/lib/cellforge/runtime.env",
        "EnvironmentFile=-/var/lib/cellforge/secrets.env",
        "ExecStart=/opt/cellforge/current/scripts/start-runtime",
        "NoNewPrivileges=true",
        "PartOf=cellforge-runtime.target",
    }
    if not required_runtime_lines <= set(runtime.splitlines()):
        print("runtime systemd hardening/environment contract is incomplete", file=sys.stderr)
        return 1
    event_fields = (root / "ros_ws/src/cellforge_interfaces/msg/JobEvent.msg").read_text(
        encoding="utf-8"
    )
    if "string bundle_id" not in event_fields.splitlines():
        print("JobEvent does not expose bundle identity", file=sys.stderr)
        return 1
    print("Task 021 bundle-agent integration contract verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
