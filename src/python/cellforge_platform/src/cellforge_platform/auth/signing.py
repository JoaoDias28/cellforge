"""Cryptographic signing and verification for platform evidence snapshots and approvals."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json_bytes(data: dict[str, Any] | list[Any]) -> bytes:
    """Produce deterministic UTF-8 bytes for cryptographic signatures."""
    return json.dumps(
        data,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class PlatformSigner:
    """Signs snapshots and approvals with an Ed25519 private key."""

    def __init__(self, private_key: Ed25519PrivateKey, key_id: str | None = None) -> None:
        self.private_key = private_key
        if key_id is not None:
            self.key_id = key_id
        else:
            public_raw = private_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            self.key_id = hashlib.sha256(public_raw).hexdigest()

    @classmethod
    def generate(cls, key_id: str | None = None) -> PlatformSigner:
        return cls(Ed25519PrivateKey.generate(), key_id=key_id)

    @classmethod
    def from_pem_bytes(cls, pem_bytes: bytes, key_id: str | None = None) -> PlatformSigner:
        candidate = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(candidate, Ed25519PrivateKey):
            raise ValueError("Private key must be an Ed25519 key.")
        return cls(candidate, key_id=key_id)

    @classmethod
    def from_pem_file(cls, path: str | Path, key_id: str | None = None) -> PlatformSigner:
        return cls.from_pem_bytes(Path(path).read_bytes(), key_id=key_id)

    def public_key_raw_b64(self) -> str:
        raw = self.private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return base64.b64encode(raw).decode("ascii")

    def public_key_pem(self) -> str:
        pem = self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode("utf-8")

    def sign_bytes(self, payload: bytes) -> str:
        signature = self.private_key.sign(payload)
        return base64.b64encode(signature).decode("ascii")

    def sign_document(self, document: dict[str, Any]) -> str:
        """Sign a dictionary payload after canonical serialization."""
        payload_bytes = canonical_json_bytes(document)
        return self.sign_bytes(payload_bytes)


class PlatformVerifier:
    """Verifies Ed25519 detached signatures on evidence snapshots and records."""

    def __init__(self, public_keys: dict[str, Ed25519PublicKey | str | bytes]) -> None:
        self._keys: dict[str, Ed25519PublicKey] = {}
        for key_id, val in public_keys.items():
            self._keys[key_id] = self._coerce_public_key(val)

    @staticmethod
    def _coerce_public_key(val: Ed25519PublicKey | str | bytes) -> Ed25519PublicKey:
        if isinstance(val, Ed25519PublicKey):
            return val
        if isinstance(val, str):
            val_bytes = val.strip().encode("utf-8")
            if b"-----BEGIN PUBLIC KEY-----" in val_bytes:
                key = serialization.load_pem_public_key(val_bytes)
                if not isinstance(key, Ed25519PublicKey):
                    raise ValueError("PEM key must be an Ed25519 public key.")
                return key
            try:
                raw_bytes = base64.b64decode(val.strip())
                return Ed25519PublicKey.from_public_bytes(raw_bytes)
            except Exception:
                pass
            if len(val.strip()) == 64:
                try:
                    raw_bytes = bytes.fromhex(val.strip())
                    return Ed25519PublicKey.from_public_bytes(raw_bytes)
                except Exception:
                    pass
        elif isinstance(val, bytes):
            if b"-----BEGIN PUBLIC KEY-----" in val:
                key = serialization.load_pem_public_key(val)
                if not isinstance(key, Ed25519PublicKey):
                    raise ValueError("PEM key must be an Ed25519 public key.")
                return key
            if len(val) == 32:
                return Ed25519PublicKey.from_public_bytes(val)
        raise ValueError(f"Could not parse Ed25519 public key from value: {val!r}")

    def verify_bytes(self, payload: bytes, signature_b64: str, key_id: str) -> bool:
        verifier = self._keys.get(key_id)
        if verifier is None:
            return False
        try:
            sig_bytes = base64.b64decode(signature_b64)
            verifier.verify(sig_bytes, payload)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    def verify_document(self, document: dict[str, Any], signature_b64: str, key_id: str) -> bool:
        """Verify canonical document against signature."""
        doc_copy = dict(document)
        doc_copy.pop("signature", None)
        payload = canonical_json_bytes(doc_copy)
        return self.verify_bytes(payload, signature_b64, key_id)
