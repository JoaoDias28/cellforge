"""Filesystem content-addressed artifact store implementation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from cellforge_platform.storage.base import (
    ArtifactStore,
    BlobNotFoundError,
    DigestMismatchError,
    canonical_sha256,
)


class FilesystemArtifactStore(ArtifactStore):
    """Stores immutable content-addressed binary artifacts on the local filesystem."""

    def __init__(self, root_directory: str | Path) -> None:
        self.root = Path(root_directory).resolve()
        self.blobs_dir = self.root / "blobs"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)

    def _blob_path(self, digest: str) -> Path:
        clean = digest.lower().strip()
        if len(clean) != 64:
            raise ValueError(f"Invalid SHA-256 digest format: {digest}")
        prefix = clean[:2]
        return self.blobs_dir / prefix / clean

    def put(
        self,
        data: bytes,
        *,
        expected_digest: str | None = None,
        media_type: str = "application/octet-stream",
    ) -> str:
        digest = canonical_sha256(data)
        if expected_digest is not None:
            clean_expected = expected_digest.lower().strip()
            if clean_expected != digest:
                raise DigestMismatchError(
                    f"Computed digest {digest} does not match expected {clean_expected}"
                )

        target = self._blob_path(digest)
        if target.is_file():
            # Blob already exists immutably
            return digest

        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to temp file then atomic replace
        with tempfile.NamedTemporaryFile(dir=str(target.parent), delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        try:
            os.replace(tmp_path, target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        return digest

    def get(self, digest: str) -> bytes:
        target = self._blob_path(digest)
        if not target.is_file():
            raise BlobNotFoundError(f"Artifact blob {digest} not found")
        data = target.read_bytes()
        actual_digest = canonical_sha256(data)
        if actual_digest != digest.lower().strip():
            raise DigestMismatchError(
                f"Artifact blob corrupted: content digest {actual_digest} != {digest}"
            )
        return data

    def exists(self, digest: str) -> bool:
        try:
            return self._blob_path(digest).is_file()
        except ValueError:
            return False

    def size(self, digest: str) -> int:
        target = self._blob_path(digest)
        if not target.is_file():
            raise BlobNotFoundError(f"Artifact blob {digest} not found")
        return target.stat().st_size

    def delete(self, digest: str) -> bool:
        target = self._blob_path(digest)
        if target.is_file():
            target.unlink()
            return True
        return False
