"""Server-side crypto for alumni verification proofs (owner: Axel).

Per grant the alumni's proof is sent to one admin under a fresh random key K (32 bytes):
  - access code: K wrapped for the admin with RSA-OAEP (SHA-256, MGF1 SHA-256) under the
    admin's RSA-3072 public key (SPKI DER), base64. Only the admin's browser can open it.
  - server copy: K wrapped with AES-256-GCM under a KEK, HKDF-SHA256 over the root key
    config.PROOF_KEKS[version] with a random 16-byte salt and the context
    "proof-kek:" + grant id. AAD = grant id || recipient key id || version (4 bytes BE).
  - package: the proof in chunks of config.PROOF_CHUNK_SIZE, each AES-256-GCM under K with
    nonce = pkg_nonce (8 random bytes) || index (4 bytes BE) and AAD = grant id || index ||
    last (1 byte); each chunk is ciphertext || 16-byte tag. Dropping, swapping or changing a
    chunk fails on decryption.

Separate from MASTER_KEY and app.crypto. Pure functions: no database, no storage, no logging.
Randomness only from secrets. No endpoints here; routers call into this module.
"""
import base64
import hashlib
import secrets
import uuid
from collections.abc import Iterable, Iterator

from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.PublicKey import RSA
from fastapi import HTTPException

from app import config

KEY_BYTES = 32
SALT_BYTES = 16
KEK_NONCE_BYTES = 12
PKG_NONCE_BYTES = 8
TAG_BYTES = 16
RSA_BITS = 3072
RSA_EXPONENT = 65537


def _check_k(k: bytes) -> None:
    if not isinstance(k, bytes) or len(k) != KEY_BYTES:
        raise ValueError("K must be %d bytes" % KEY_BYTES)


def new_share_key() -> bytes:
    """A fresh K for one grant."""
    return secrets.token_bytes(KEY_BYTES)


def check_public_key(spki: bytes) -> str:
    """The fingerprint (SHA-256, lowercase hex) of an RSA-3072 public key in SPKI DER.

    Anything else (PEM, PKCS#1, a private key, another size or exponent, another algorithm)
    answers 422 INVALID_PUBLIC_KEY.
    """
    try:
        key = RSA.import_key(spki)
        # Exporting again must give the same bytes: only plain SPKI DER is accepted.
        ok = (
            not key.has_private() and key.size_in_bits() == RSA_BITS
            and key.e == RSA_EXPONENT and key.export_key("DER") == spki
        )
    except (ValueError, IndexError, TypeError):
        ok = False
    if not ok:
        raise HTTPException(status_code=422, detail="INVALID_PUBLIC_KEY")
    return hashlib.sha256(spki).hexdigest()


def wrap_for_recipient(spki: bytes, k: bytes) -> str:
    """The access code: K under RSA-OAEP SHA-256 for the admin's key, base64 (512 characters)."""
    check_public_key(spki)
    _check_k(k)
    # hashAlgo must be set: pycryptodome defaults to SHA-1. MGF1 follows hashAlgo.
    cipher = PKCS1_OAEP.new(RSA.import_key(spki), hashAlgo=SHA256)
    return base64.b64encode(cipher.encrypt(k)).decode()


def _kek(version: int, salt: bytes, grant_id: uuid.UUID) -> bytes:
    root = config.PROOF_KEKS.get(version)
    if root is None:  # the root key was removed from the environment: the grant cannot be opened
        raise HTTPException(status_code=410, detail="GRANT_ENDED")
    return HKDF(root, KEY_BYTES, salt, SHA256, context=b"proof-kek:" + grant_id.bytes)


def _aad(grant_id: uuid.UUID, recipient_key_id: uuid.UUID, version: int) -> bytes:
    return grant_id.bytes + recipient_key_id.bytes + version.to_bytes(4, "big")


def wrap_kek(k: bytes, *, grant_id: uuid.UUID, recipient_key_id: uuid.UUID) -> dict:
    """K wrapped under the active KEK, as the ProofGrant columns of the same names.

    grant_id must be the id the grant row will get, so the caller creates it (uuid4) first.
    """
    _check_k(k)
    version = config.PROOF_KEK_VERSION
    if version not in config.PROOF_KEKS:
        raise RuntimeError("PROOF_KEK_V%d is not set" % version)
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(KEK_NONCE_BYTES)
    cipher = AES.new(_kek(version, salt, grant_id), AES.MODE_GCM, nonce=nonce)
    cipher.update(_aad(grant_id, recipient_key_id, version))
    ciphertext, tag = cipher.encrypt_and_digest(k)
    return {"kek_version": version, "kek_salt": salt, "kek_nonce": nonce, "k_wrapped": ciphertext + tag}


def unwrap_kek(grant) -> bytes:
    """K from a ProofGrant (or anything with its id, recipient_key_id and kek_* attributes).

    410 GRANT_ENDED when its KEK version is no longer configured; 500 INTEGRITY_ERROR when
    the wrapped key, its tag, nonce, salt, version or ids were changed.
    """
    version = grant.kek_version
    key = _kek(version, bytes(grant.kek_salt), grant.id)
    wrapped = bytes(grant.k_wrapped)
    try:
        if len(wrapped) != KEY_BYTES + TAG_BYTES:
            raise ValueError("wrong length")
        cipher = AES.new(key, AES.MODE_GCM, nonce=bytes(grant.kek_nonce))
        cipher.update(_aad(grant.id, grant.recipient_key_id, version))
        return cipher.decrypt_and_verify(wrapped[:-TAG_BYTES], wrapped[-TAG_BYTES:])
    except ValueError:
        raise HTTPException(status_code=500, detail="INTEGRITY_ERROR")


def _rechunk(pieces, size: int):
    """Regroup pieces of any size into chunks of `size`; only the last may be shorter."""
    buf = bytearray()
    for piece in pieces:
        buf += piece
        while len(buf) >= size:
            yield bytes(buf[:size])
            del buf[:size]
    if buf:
        yield bytes(buf)


def _seal(chunks, k: bytes, grant_id: uuid.UUID, pkg_nonce: bytes):
    it = iter(chunks)
    chunk = next(it, b"")  # empty input still gives one chunk, so a missing package is noticed
    index = 0
    while chunk is not None:
        following = next(it, None)  # one ahead, so the last chunk says it is the last
        position = index.to_bytes(4, "big")
        cipher = AES.new(k, AES.MODE_GCM, nonce=pkg_nonce + position)
        cipher.update(grant_id.bytes + position + bytes([following is None]))
        ciphertext, tag = cipher.encrypt_and_digest(chunk)
        yield ciphertext + tag
        chunk = following
        index += 1


def encrypt_package(
    chunks: Iterable[bytes], k: bytes, grant_id: uuid.UUID, *, chunk_size: int = config.PROOF_CHUNK_SIZE,
) -> tuple[bytes, Iterator[bytes]]:
    """(pkg_nonce, iterator of ciphertext || tag per chunk) for plaintext pieces of any size.

    The iterator encrypts lazily, one chunk at a time; the package size is the sum of its parts.
    """
    _check_k(k)
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    pkg_nonce = secrets.token_bytes(PKG_NONCE_BYTES)
    return pkg_nonce, _seal(_rechunk(chunks, chunk_size), k, grant_id, pkg_nonce)
