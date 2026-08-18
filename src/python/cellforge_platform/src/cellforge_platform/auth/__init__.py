"""Authentication package exports."""

from cellforge_platform.auth.dependencies import (
    get_current_auth,
    get_token_verifier,
    require_authenticated,
    require_role,
)
from cellforge_platform.auth.models import (
    ANONYMOUS_AUTH,
    AuthContext,
    CellForgeRole,
)
from cellforge_platform.auth.signing import PlatformSigner, PlatformVerifier
from cellforge_platform.auth.verifier import AuthError, OidcTokenVerifier

__all__ = [
    "ANONYMOUS_AUTH",
    "AuthContext",
    "AuthError",
    "CellForgeRole",
    "OidcTokenVerifier",
    "PlatformSigner",
    "PlatformVerifier",
    "get_current_auth",
    "get_token_verifier",
    "require_authenticated",
    "require_role",
]
