"""OIDC JWT token verification and production dev-auth guard."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Sequence
from typing import Any

from cellforge_platform.auth.models import (
    ANONYMOUS_AUTH,
    AuthContext,
    CellForgeRole,
)
from cellforge_platform.config import PlatformSettings


class AuthError(Exception):
    """Authentication or authorization failure."""

    def __init__(self, code: str, message: str, status_code: int = 401) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"{code}: {message}")


class OidcTokenVerifier:
    """Verifies JWT tokens against OIDC issuer configuration and enforces dev-auth guards."""

    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings

    def verify_request_auth(
        self,
        *,
        authorization_header: str | None = None,
        dev_user_header: str | None = None,
        dev_role_header: str | None = None,
    ) -> AuthContext:
        # Check production dev-auth guard first
        is_production = self.settings.environment.lower() == "production"

        if dev_user_header is not None or dev_role_header is not None:
            if is_production:
                raise AuthError(
                    "auth.production_dev_auth_prohibited",
                    "Development authentication headers (X-CellForge-Dev-*) are "
                    "strictly prohibited in production.",
                    status_code=401,
                )
            if self.settings.allow_dev_auth:
                return self._build_dev_auth(dev_user_header, dev_role_header)

        # Standard Bearer token authentication
        if authorization_header is not None and authorization_header.startswith("Bearer "):
            token = authorization_header[7:].strip()
            return self.verify_token(token)

        # If no credentials provided, return anonymous auth
        return ANONYMOUS_AUTH

    def _build_dev_auth(self, user_header: str | None, role_header: str | None) -> AuthContext:
        user_id = user_header.strip() if user_header else "dev-engineer"
        role_names = [
            r.strip() for r in (role_header or "automation_engineer").split(",") if r.strip()
        ]
        roles: set[CellForgeRole] = set()
        for name in role_names:
            try:
                roles.add(CellForgeRole(name.lower()))
            except ValueError:
                pass
        if not roles:
            roles.add(CellForgeRole.VIEWER)

        return AuthContext(
            user_id=user_id,
            roles=frozenset(roles),
            email=f"{user_id}@dev.local",
            is_authenticated=True,
            token_claims={"sub": user_id, "roles": [r.value for r in roles], "iss": "dev-auth"},
        )

    def verify_token(self, token: str) -> AuthContext:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthError("auth.invalid_token", "JWT token must contain 3 parts.")

        header_b64, payload_b64, signature_b64 = parts
        try:
            header_json = self._b64_decode(header_b64)
            payload_json = self._b64_decode(payload_b64)
            header = json.loads(header_json)
            payload = json.loads(payload_json)
        except Exception as error:
            raise AuthError(
                "auth.invalid_token_payload", f"Failed to parse JWT payload: {error}"
            ) from error

        alg = header.get("alg", "HS256")
        if alg == "HS256":
            expected_sig = hmac.new(
                self.settings.jwt_secret.encode("utf-8"),
                f"{header_b64}.{payload_b64}".encode(),
                hashlib.sha256,
            ).digest()
            actual_sig = self._b64_decode_raw(signature_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                raise AuthError("auth.invalid_signature", "JWT signature verification failed.")
        elif alg == "none":
            if self.settings.environment == "production":
                raise AuthError(
                    "auth.unsigned_token_prohibited",
                    "Unsigned tokens are not allowed in production.",
                )
        # Expiration check
        exp = payload.get("exp")
        if exp is not None and isinstance(exp, (int, float)):
            if time.time() > exp:
                raise AuthError("auth.token_expired", "JWT token has expired.")

        # Issuer and audience validation
        iss = payload.get("iss")
        if iss is not None and self.settings.oidc_issuer and iss != self.settings.oidc_issuer:
            if self.settings.environment == "production":
                raise AuthError(
                    "auth.invalid_issuer",
                    f"JWT issuer '{iss}' != expected '{self.settings.oidc_issuer}'.",
                )

        aud = payload.get("aud")
        if aud is not None and self.settings.oidc_audience and aud != self.settings.oidc_audience:
            if self.settings.environment == "production":
                raise AuthError(
                    "auth.invalid_audience",
                    f"JWT audience '{aud}' != expected '{self.settings.oidc_audience}'.",
                )

        user_id = str(payload.get("sub", "unknown"))
        email = payload.get("email")

        # Map roles from claims
        raw_roles = payload.get("roles") or payload.get("groups") or []
        if isinstance(raw_roles, str):
            raw_roles = [r.strip() for r in raw_roles.split(",")]

        roles: set[CellForgeRole] = set()
        for r in raw_roles:
            try:
                roles.add(CellForgeRole(str(r).lower()))
            except ValueError:
                pass

        if not roles:
            roles.add(CellForgeRole.VIEWER)

        return AuthContext(
            user_id=user_id,
            roles=frozenset(roles),
            email=str(email) if email else None,
            is_authenticated=True,
            token_claims=payload,
        )

    def create_token(
        self,
        user_id: str,
        roles: Sequence[CellForgeRole | str],
        *,
        expires_in_seconds: int = 3600,
        email: str | None = None,
    ) -> str:
        """Create a signed HS256 token for testing and client authentication."""
        header = {"alg": "HS256", "typ": "JWT"}
        now = int(time.time())
        role_values = [r.value if isinstance(r, CellForgeRole) else str(r) for r in roles]
        payload: dict[str, Any] = {
            "sub": user_id,
            "roles": role_values,
            "iss": self.settings.oidc_issuer,
            "aud": self.settings.oidc_audience,
            "iat": now,
            "exp": now + expires_in_seconds,
        }
        if email:
            payload["email"] = email

        header_b64 = self._b64_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = self._b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        sig = hmac.new(
            self.settings.jwt_secret.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256,
        ).digest()
        sig_b64 = self._b64_encode(sig)
        return f"{header_b64}.{payload_b64}.{sig_b64}"

    @staticmethod
    def _b64_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64_decode(s: str) -> str:
        padded = s + "=" * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")

    @staticmethod
    def _b64_decode_raw(s: str) -> bytes:
        padded = s + "=" * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))
