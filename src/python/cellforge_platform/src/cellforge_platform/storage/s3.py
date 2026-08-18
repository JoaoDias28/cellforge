"""S3-compatible content-addressed artifact store implementation."""

from __future__ import annotations

from typing import Any

from cellforge_platform.storage.base import (
    ArtifactStore,
    BlobNotFoundError,
    DigestMismatchError,
    canonical_sha256,
)


class S3ArtifactStore(ArtifactStore):
    """Stores content-addressed artifacts in an S3-compatible bucket."""

    def __init__(
        self,
        bucket_name: str,
        *,
        s3_client: Any | None = None,
        prefix: str = "artifacts/sha256",
    ) -> None:
        self.bucket = bucket_name
        self.prefix = prefix.strip("/")
        self._client = s3_client
        # In-memory dictionary fallback if client is None for unit testing S3 adapter logic
        self._memory_store: dict[str, bytes] = {}

    def _key(self, digest: str) -> str:
        clean = digest.lower().strip()
        if len(clean) != 64:
            raise ValueError(f"Invalid SHA-256 digest format: {digest}")
        return f"{self.prefix}/{clean[:2]}/{clean}"

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

        key = self._key(digest)
        if self._client is not None:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=media_type,
            )
        else:
            self._memory_store[key] = data

        return digest

    def get(self, digest: str) -> bytes:
        key = self._key(digest)
        if self._client is not None:
            try:
                resp = self._client.get_object(Bucket=self.bucket, Key=key)
                data: bytes = bytes(resp["Body"].read())
            except Exception as error:
                raise BlobNotFoundError(
                    f"Artifact blob {digest} not found in S3: {error}"
                ) from error
        else:
            if key not in self._memory_store:
                raise BlobNotFoundError(f"Artifact blob {digest} not found")
            data = self._memory_store[key]

        actual_digest = canonical_sha256(data)
        if actual_digest != digest.lower().strip():
            raise DigestMismatchError(
                f"S3 artifact corrupted: content digest {actual_digest} != {digest}"
            )
        return data

    def exists(self, digest: str) -> bool:
        try:
            key = self._key(digest)
        except ValueError:
            return False

        if self._client is not None:
            try:
                self._client.head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False
        else:
            return key in self._memory_store

    def size(self, digest: str) -> int:
        key = self._key(digest)
        if self._client is not None:
            try:
                resp = self._client.head_object(Bucket=self.bucket, Key=key)
                return int(resp.get("ContentLength", 0))
            except Exception as error:
                raise BlobNotFoundError(f"Artifact blob {digest} not found: {error}") from error
        else:
            if key not in self._memory_store:
                raise BlobNotFoundError(f"Artifact blob {digest} not found")
            return len(self._memory_store[key])

    def delete(self, digest: str) -> bool:
        key = self._key(digest)
        if self._client is not None:
            try:
                self._client.delete_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False
        else:
            if key in self._memory_store:
                del self._memory_store[key]
                return True
            return False
