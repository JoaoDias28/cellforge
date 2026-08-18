"""Content-addressed artifact storage interface and exceptions."""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable


class ArtifactStoreError(Exception):
    """Base exception for artifact storage failures."""


class BlobNotFoundError(ArtifactStoreError):
    """Raised when the requested content-addressed blob does not exist."""


class DigestMismatchError(ArtifactStoreError):
    """Raised when uploaded or downloaded blob content does not match its expected digest."""


@runtime_checkable
class ArtifactStore(Protocol):
    """Content-addressed artifact store protocol."""

    def put(
        self,
        data: bytes,
        *,
        expected_digest: str | None = None,
        media_type: str = "application/octet-stream",
    ) -> str:
        """Store binary blob and return its canonical SHA-256 hex digest."""
        ...

    def get(self, digest: str) -> bytes:
        """Retrieve binary blob by its SHA-256 digest, verifying integrity."""
        ...

    def exists(self, digest: str) -> bool:
        """Check whether a blob exists for the given SHA-256 digest."""
        ...

    def size(self, digest: str) -> int:
        """Return size in bytes for the given SHA-256 digest."""
        ...

    def delete(self, digest: str) -> bool:
        """Delete blob if allowed; returns True if removed, False if not found."""
        ...


def canonical_sha256(data: bytes) -> str:
    """Compute lowercase 64-character SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()
