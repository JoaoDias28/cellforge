"""Verification of strict safety boundaries and absence of hardware actuation endpoints."""

from __future__ import annotations

from cellforge_platform import create_platform_app


def test_platform_service_has_zero_hardware_actuation_or_safety_control_endpoints() -> None:
    app = create_platform_app()

    forbidden_terms = {
        "joint",
        "jog",
        "motor",
        "actuator",
        "estop",
        "e_stop",
        "safety_override",
        "bypass_safety",
        "laser_fire",
        "pneumatic_actuate",
        "hardware_command",
        "direct_io_write",
    }

    routes = [r for r in app.routes if hasattr(r, "path")]
    assert len(routes) > 0, "Platform application should have registered routes."

    for route in routes:
        path_lower = str(getattr(route, "path", "")).lower()
        name_lower = str(getattr(route, "name", "")).lower()

        for term in forbidden_terms:
            assert term not in path_lower, (
                f"Forbidden term '{term}' found in platform endpoint path: {path_lower}"
            )
            assert term not in name_lower, (
                f"Forbidden term '{term}' found in platform endpoint name: {name_lower}"
            )
