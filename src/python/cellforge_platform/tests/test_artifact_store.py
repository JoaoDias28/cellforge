"""Tests for content-addressed artifact storage backends."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from cellforge_platform.storage import (
    BlobNotFoundError,
    DigestMismatchError,
    FilesystemArtifactStore,
    S3ArtifactStore,
)


def test_filesystem_artifact_store_lifecycle(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)

    data = b"CellForge binary artifact bundle payload"
    expected_digest = hashlib.sha256(data).hexdigest()

    # Put blob
    digest = store.put(data)
    assert digest == expected_digest
    assert store.exists(digest)
    assert store.size(digest) == len(data)

    # Get blob and verify integrity
    retrieved = store.get(digest)
    assert retrieved == data

    # Idempotent put with expected digest
    digest2 = store.put(data, expected_digest=expected_digest)
    assert digest2 == digest

    # Put with mismatched expected digest fails
    with pytest.raises(DigestMismatchError):
        store.put(data, expected_digest="0" * 64)

    # Get non-existent blob
    with pytest.raises(BlobNotFoundError):
        store.get("f" * 64)

    # Corrupt file on disk and verify detection on get
    blob_file = tmp_path / "blobs" / digest[:2] / digest
    assert blob_file.is_file()
    blob_file.write_bytes(b"corrupted content")
    with pytest.raises(DigestMismatchError):
        store.get(digest)

    # Delete
    assert store.delete(digest) is True
    assert store.exists(digest) is False


def test_s3_artifact_store_lifecycle() -> None:
    store = S3ArtifactStore(bucket_name="test-bucket")

    data = b"S3 mock payload test data 12345"
    expected_digest = hashlib.sha256(data).hexdigest()

    # Put blob
    digest = store.put(data)
    assert digest == expected_digest
    assert store.exists(digest)
    assert store.size(digest) == len(data)

    # Get blob
    retrieved = store.get(digest)
    assert retrieved == data

    # Mismatched expected digest
    with pytest.raises(DigestMismatchError):
        store.put(data, expected_digest="1" * 64)

    # Non-existent
    with pytest.raises(BlobNotFoundError):
        store.get("a" * 64)

    # Delete
    assert store.delete(digest) is True
    assert store.exists(digest) is False
