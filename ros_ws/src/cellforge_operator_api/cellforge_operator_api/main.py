"""Production entry point for the loopback operator API and ROS bridge."""

from __future__ import annotations

import ipaddress
import os
import threading
from pathlib import Path

import rclpy
import uvicorn
from rclpy.executors import MultiThreadedExecutor

from cellforge_operator_api.api import create_app
from cellforge_operator_api.core import (
    OperatorError,
    OperatorService,
    RecoveryCatalog,
    SqliteAuditStore,
    TokenAuthorizer,
)
from cellforge_operator_api.runtime import RosRuntimePort


def main(args: list[str] | None = None) -> None:
    bundle_root = Path(_required_environment("CELLFORGE_BUNDLE_ROOT")).resolve()
    bundle_id = _required_environment("CELLFORGE_BUNDLE_ID")
    auth_path = Path(os.environ.get("CELLFORGE_OPERATOR_AUTH", "/etc/cellforge/operator-auth.json"))
    catalog_path = Path(
        os.environ.get(
            "CELLFORGE_RECOVERY_CATALOG", str(bundle_root / "config/operator-recovery.json")
        )
    ).resolve()
    try:
        catalog_path.relative_to(bundle_root)
    except ValueError:
        raise OperatorError(
            "operator.recovery.catalog_invalid",
            "Recovery catalog must be inside the active immutable bundle.",
        ) from None
    audit_path = Path(
        os.environ.get("CELLFORGE_OPERATOR_AUDIT", "/var/lib/cellforge/operator-audit.db")
    )
    trace_path = Path(os.environ.get("CELLFORGE_TRACE_DATABASE", "/var/lib/cellforge/traces.db"))
    host = os.environ.get("CELLFORGE_OPERATOR_HOST", "127.0.0.1")
    if not ipaddress.ip_address(host).is_loopback:
        raise RuntimeError("CELLFORGE_OPERATOR_HOST must be a numeric loopback address")
    port = int(os.environ.get("CELLFORGE_OPERATOR_PORT", "9080"))
    if not 1 <= port <= 65535:
        raise RuntimeError("CELLFORGE_OPERATOR_PORT is outside the valid range")

    authorizer = TokenAuthorizer.from_file(auth_path)
    catalog = RecoveryCatalog.from_file(catalog_path)
    audit = SqliteAuditStore(audit_path)
    rclpy.init(args=args)
    runtime = RosRuntimePort(catalog=catalog, trace_database=trace_path)
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(runtime)
    spin_thread = threading.Thread(target=executor.spin, name="operator-ros", daemon=True)
    spin_thread.start()
    service = OperatorService(authorizer, catalog, audit, runtime)
    try:
        uvicorn.run(
            create_app(service, bundle_id=bundle_id), host=host, port=port, access_log=False
        )
    finally:
        executor.shutdown()
        runtime.destroy_node()
        audit.close()
        rclpy.shutdown()
        spin_thread.join(timeout=5.0)


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value
