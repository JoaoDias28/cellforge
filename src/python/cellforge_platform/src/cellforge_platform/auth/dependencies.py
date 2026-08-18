"""FastAPI authentication and RBAC dependency helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from cellforge_platform.auth.models import AuthContext, CellForgeRole
from cellforge_platform.auth.verifier import AuthError, OidcTokenVerifier
from cellforge_platform.config import PlatformSettings


def get_token_verifier(request: Request) -> OidcTokenVerifier:
    settings: PlatformSettings = getattr(request.app.state, "settings", PlatformSettings())
    return OidcTokenVerifier(settings)


async def get_current_auth(
    authorization: str | None = Header(None),
    x_cellforge_dev_user: str | None = Header(None),
    x_cellforge_dev_role: str | None = Header(None),
    verifier: OidcTokenVerifier = Depends(get_token_verifier),
) -> AuthContext:
    try:
        return verifier.verify_request_auth(
            authorization_header=authorization,
            dev_user_header=x_cellforge_dev_user,
            dev_role_header=x_cellforge_dev_role,
        )
    except AuthError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error


async def require_authenticated(
    auth: AuthContext = Depends(get_current_auth),
) -> AuthContext:
    if not auth.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail={"code": "auth.unauthenticated", "message": "Authentication required."},
        )
    return auth


def require_role(*required_roles: CellForgeRole | str) -> Callable[..., Any]:
    """Dependency factory checking that authenticated user holds one of the required roles."""

    async def _role_checker(auth: AuthContext = Depends(require_authenticated)) -> AuthContext:
        if not auth.has_role(*required_roles):
            req_str = ", ".join(
                r.value if isinstance(r, CellForgeRole) else str(r) for r in required_roles
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "auth.forbidden",
                    "message": f"Operation requires one of the following roles: [{req_str}].",
                },
            )
        return auth

    return _role_checker
