"""Platform service configuration and environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PlatformSettings:
    """Settings governing database, artifact storage, auth, and environment mode."""

    environment: str = "development"  # "development" | "staging" | "production"
    service_name: str = "cellforge-platform"
    service_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = ":memory:"  # ":memory:", sqlite:///path/to/db.sqlite, or postgresql://...

    # Artifact storage
    storage_backend: str = "filesystem"  # "filesystem" | "s3"
    storage_root: Path = Path("var/platform_artifacts")
    s3_bucket: str = "cellforge-artifacts"
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # OIDC & Auth
    oidc_issuer: str = "https://auth.cellforge.internal"
    oidc_audience: str = "cellforge-platform"
    oidc_public_key_pem: str | None = None
    jwt_secret: str = "dev-jwt-secret-not-for-production-use-0123456789"
    allow_dev_auth: bool = True  # strictly prohibited when environment == "production"

    # Schemas
    schema_directory: Path | None = None

    @classmethod
    def from_env(cls, **overrides: object) -> PlatformSettings:
        env = os.environ.get("CELLFORGE_ENV", "development").strip().lower()
        db_url = os.environ.get("CELLFORGE_DATABASE_URL", ":memory:")
        storage_type = os.environ.get("CELLFORGE_STORAGE_BACKEND", "filesystem")
        storage_path = Path(os.environ.get("CELLFORGE_STORAGE_ROOT", "var/platform_artifacts"))
        s3_bucket = os.environ.get("CELLFORGE_S3_BUCKET", "cellforge-artifacts")
        s3_endpoint = os.environ.get("CELLFORGE_S3_ENDPOINT")
        s3_region = os.environ.get("CELLFORGE_S3_REGION", "us-east-1")
        issuer = os.environ.get("CELLFORGE_OIDC_ISSUER", "https://auth.cellforge.internal")
        audience = os.environ.get("CELLFORGE_OIDC_AUDIENCE", "cellforge-platform")
        allow_dev = (
            os.environ.get("CELLFORGE_ALLOW_DEV_AUTH", "true").lower() in {"1", "true", "yes"}
            if env != "production"
            else False
        )

        values: dict[str, object] = {
            "environment": env,
            "database_url": db_url,
            "storage_backend": storage_type,
            "storage_root": storage_path,
            "s3_bucket": s3_bucket,
            "s3_endpoint_url": s3_endpoint,
            "s3_region": s3_region,
            "oidc_issuer": issuer,
            "oidc_audience": audience,
            "allow_dev_auth": allow_dev,
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]
