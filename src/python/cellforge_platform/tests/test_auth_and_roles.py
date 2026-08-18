"""Tests for OIDC JWT token verification, RBAC roles, and dev-auth protection."""

from __future__ import annotations

import pytest
from cellforge_platform.auth import (
    AuthContext,
    AuthError,
    CellForgeRole,
    OidcTokenVerifier,
)
from cellforge_platform.config import PlatformSettings


def test_role_hierarchy() -> None:
    admin = AuthContext(user_id="admin", roles=frozenset({CellForgeRole.ADMINISTRATOR}))
    assert admin.has_role(CellForgeRole.ADMINISTRATOR)
    assert admin.has_role(CellForgeRole.AUTOMATION_ENGINEER)
    assert admin.has_role(CellForgeRole.PROCESS_ENGINEER)
    assert admin.has_role(CellForgeRole.MAINTAINER)
    assert admin.has_role(CellForgeRole.OPERATOR)
    assert admin.has_role(CellForgeRole.VIEWER)

    operator = AuthContext(user_id="op", roles=frozenset({CellForgeRole.OPERATOR}))
    assert operator.has_role(CellForgeRole.OPERATOR)
    assert operator.has_role(CellForgeRole.VIEWER)
    assert not operator.has_role(CellForgeRole.ADMINISTRATOR)
    assert not operator.has_role(CellForgeRole.AUTOMATION_ENGINEER)


def test_oidc_jwt_lifecycle_and_validation() -> None:
    settings = PlatformSettings(
        environment="development",
        oidc_issuer="https://auth.cellforge.internal",
        oidc_audience="cellforge-platform",
        jwt_secret="super-secret-test-key-32-chars-long!",
    )
    verifier = OidcTokenVerifier(settings)

    # Valid token
    token = verifier.create_token(
        "eng1", [CellForgeRole.AUTOMATION_ENGINEER], email="eng1@example.com"
    )
    auth = verifier.verify_token(token)
    assert auth.is_authenticated
    assert auth.user_id == "eng1"
    assert auth.email == "eng1@example.com"
    assert CellForgeRole.AUTOMATION_ENGINEER in auth.roles

    # Expired token
    expired_token = verifier.create_token("eng1", [CellForgeRole.VIEWER], expires_in_seconds=-10)
    with pytest.raises(AuthError) as exc_info:
        verifier.verify_token(expired_token)
    assert exc_info.value.code == "auth.token_expired"

    # Bad signature
    tampered_token = token[:-5] + "abcde"
    with pytest.raises(AuthError) as exc_info:
        verifier.verify_token(tampered_token)
    assert exc_info.value.code == "auth.invalid_signature"


def test_dev_auth_allowed_in_development_prohibited_in_production() -> None:
    dev_settings = PlatformSettings(
        environment="development",
        allow_dev_auth=True,
    )
    dev_verifier = OidcTokenVerifier(dev_settings)

    auth = dev_verifier.verify_request_auth(
        dev_user_header="dev-user",
        dev_role_header="administrator",
    )
    assert auth.is_authenticated
    assert auth.user_id == "dev-user"
    assert CellForgeRole.ADMINISTRATOR in auth.roles

    # Production environment
    prod_settings = PlatformSettings(
        environment="production",
        allow_dev_auth=False,
    )
    prod_verifier = OidcTokenVerifier(prod_settings)

    # Dev headers in production MUST raise 401 AuthError
    with pytest.raises(AuthError) as exc_info:
        prod_verifier.verify_request_auth(
            dev_user_header="attacker",
            dev_role_header="administrator",
        )
    assert exc_info.value.code == "auth.production_dev_auth_prohibited"
    assert exc_info.value.status_code == 401
