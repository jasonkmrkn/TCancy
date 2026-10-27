"""Integrity tags: HMAC-SHA256 over each ciphertext chunk (encrypt-then-MAC).

The MAC key is derived from MASTER_KEY with its own context ("mac:<alg>:<item>") and the
copy's salt, so it never equals an encryption key and is bound to the item, the algorithm and
the salt. Each tag also covers the chunk index, whether it is the last chunk, and the nonce,
so chunks cannot be modified, moved, swapped, dropped or appended unnoticed.

INTEGRITY_MODE is read on every call: off checks nothing, log-only logs a failure and lets the
data through, enforce answers 500 INTEGRITY_ERROR. Tags are written in every mode.

Only app.vault imports this module.
"""
import hashlib
import hmac
import logging
import time

from fastapi import HTTPException

from app import config, crypto

log = logging.getLogger("tcancy.integrity")


def enabled() -> bool:
    return config.INTEGRITY_MODE != "off"


def tag(alg: str, item: str, salt: bytes, nonce: bytes | None, index: int, last: bool, ciphertext: bytes) -> bytes:
    key = crypto.derive_key(salt, "mac:%s:%s" % (alg, item), 32)
    nonce = nonce or b""
    msg = index.to_bytes(8, "big") + bytes([last]) + bytes([len(nonce)]) + nonce + ciphertext
    return hmac.new(key, msg, hashlib.sha256).digest()


def verify(chunks, tags: list[bytes], alg: str, item: str, salt: bytes, nonce: bytes | None) -> tuple[bool, float]:
    """Check ciphertext `chunks` (CHUNK_SIZE pieces, in order) against `tags`, one per index.

    Returns (ok, integrity_ms), where integrity_ms counts only the HMAC work, not the reads.
    A missing, extra or reordered chunk fails, as does a missing tag.
    """
    ok = True
    spent = 0.0
    count = 0
    it = iter(chunks)
    current = next(it, None)
    while current is not None:
        following = next(it, None)
        start = time.perf_counter()
        expected = tag(alg, item, salt, nonce, count, following is None, current)
        ok &= count < len(tags) and hmac.compare_digest(expected, tags[count])
        spent += time.perf_counter() - start
        count += 1
        current = following
    ok &= count == len(tags)
    return ok, spent * 1000


def fail(what: str) -> None:
    """Act on a failed check. `what` names the record (ids, field name), never its contents."""
    if config.INTEGRITY_MODE == "enforce":
        raise HTTPException(status_code=500, detail="INTEGRITY_ERROR")
    if config.INTEGRITY_MODE == "log-only":
        log.warning("integrity check failed: %s", what)
