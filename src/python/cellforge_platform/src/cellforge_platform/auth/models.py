"""Authentication and role-based authorization models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CellForgeRole(StrEnum):
    """Standard RBAC roles defined in SYSTEM_SPEC."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    MAINTAINER = "maintainer"
    PROCESS_ENGINEER = "process_engineer"
    AUTOMATION_ENGINEER = "automation_engineer"
    ADMINISTRATOR = "administrator"


# Role hierarchy / implied capabilities
ROLE_HIERARCHY: dict[CellForgeRole, set[CellForgeRole]] = {
    CellForgeRole.VIEWER: {CellForgeRole.VIEWER},
    CellForgeRole.OPERATOR: {CellForgeRole.OPERATOR, CellForgeRole.VIEWER},
    CellForgeRole.MAINTAINER: {
        CellForgeRole.MAINTAINER,
        CellForgeRole.OPERATOR,
        CellForgeRole.VIEWER,
    },
    CellForgeRole.PROCESS_ENGINEER: {
        CellForgeRole.PROCESS_ENGINEER,
        CellForgeRole.OPERATOR,
        CellForgeRole.VIEWER,
    },
    CellForgeRole.AUTOMATION_ENGINEER: {
        CellForgeRole.AUTOMATION_ENGINEER,
        CellForgeRole.PROCESS_ENGINEER,
        CellForgeRole.MAINTAINER,
        CellForgeRole.OPERATOR,
        CellForgeRole.VIEWER,
    },
    CellForgeRole.ADMINISTRATOR: {
        CellForgeRole.ADMINISTRATOR,
        CellForgeRole.AUTOMATION_ENGINEER,
        CellForgeRole.PROCESS_ENGINEER,
        CellForgeRole.MAINTAINER,
        CellForgeRole.OPERATOR,
        CellForgeRole.VIEWER,
    },
}


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Authenticated user context and assigned roles."""

    user_id: str
    roles: frozenset[CellForgeRole]
    email: str | None = None
    is_authenticated: bool = True
    token_claims: dict[str, Any] = field(default_factory=dict)

    def has_role(self, *required_roles: CellForgeRole | str) -> bool:
        """Check if user holds any of the required roles (considering hierarchy)."""
        effective_roles: set[CellForgeRole] = set()
        for r in self.roles:
            effective_roles.update(ROLE_HIERARCHY.get(r, {r}))

        for req in required_roles:
            role_enum = CellForgeRole(req) if isinstance(req, str) else req
            if role_enum in effective_roles:
                return True
        return False


ANONYMOUS_AUTH = AuthContext(
    user_id="anonymous",
    roles=frozenset(),
    is_authenticated=False,
)
