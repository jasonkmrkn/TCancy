"""Blind index helpers: HMAC-SHA256 with BLIND_INDEX_KEY, used for equality lookups on encrypted fields.

The index is stored in a separate UNIQUE column so uniqueness can be enforced without storing
the plaintext value. The kind ("email" or "nik") is part of the hashed message, so the same
text under two kinds never produces the same index.
"""
import hashlib
import hmac

from app import config

_KINDS = ("email", "nik")
_KEY_ERROR = "BLIND_INDEX_KEY must be 64 hex characters"


def _key() -> bytes:
    try:
        key = bytes.fromhex(config.BLIND_INDEX_KEY)
    except ValueError:
        raise RuntimeError(_KEY_ERROR) from None
    if len(key) != 32:
        raise RuntimeError(_KEY_ERROR)
    return key


def _normalize(kind: str, value: str) -> str:
    if kind == "email":
        return value.strip().lower()
    return value


def compute(kind: str, value: str) -> bytes:
    """Return the 32-byte blind index of value for kind ("email" or "nik")."""
    if kind not in _KINDS:
        raise ValueError("kind must be 'email' or 'nik'")
    message = f"{kind}:{_normalize(kind, value)}".encode("utf-8")
    return hmac.new(_key(), message, hashlib.sha256).digest()