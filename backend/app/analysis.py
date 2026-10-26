"""Ciphertext analysis of one document: what each stored copy looks like next to the plaintext.

Shows the first bytes, the byte entropy of the first MiB and how many preview bytes changed.
Keys and salts never leave the server; only the nonce is shown, as it is not secret.
"""
import math
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import documents, storage
from app.models import DocumentCopy, User

ENTROPY_BYTES = 1024 * 1024

# Shown with every copy and benchmark result, in this order.
CIPHERS = {
    "aes": {"name": "AES-256", "mode": "CTR", "kind": "block cipher", "key_bits": 256, "block_bits": 128},
    # 64 is the key length; DES uses 56 of those bits.
    "des": {"name": "DES", "mode": "CTR", "kind": "block cipher", "key_bits": 64, "block_bits": 64},
    "rc4": {"name": "RC4", "mode": "none (stream cipher)", "kind": "stream cipher", "key_bits": 128, "block_bits": None},
}


def _entropy(data: bytes) -> float:
    """Shannon entropy in bits per byte (0 for empty data, 8 at most)."""
    if not data:
        return 0.0
    n = len(data)
    return -sum(c / n * math.log2(c / n) for c in Counter(data).values())


def _head(pieces, limit: int) -> bytes:
    """The first `limit` bytes of an iterator of byte pieces; stops reading once it has them."""
    buf = bytearray()
    for piece in pieces:
        buf += piece
        if len(buf) >= limit:
            break
    return bytes(buf[:limit])


def copies_of(db: Session, doc_id) -> list[DocumentCopy]:
    """The document's copies in CIPHERS order (only aes under the production policy)."""
    rows = {c.algorithm: c for c in db.scalars(select(DocumentCopy).where(DocumentCopy.document_id == doc_id))}
    return [rows[alg] for alg in CIPHERS if alg in rows]


def ciphertext_view(db: Session, user: User, doc_id: str, preview_bytes: int) -> dict:
    doc = documents.get_owned(db, user, doc_id)
    plain = _head(documents.stream(db, doc.id), ENTROPY_BYTES)
    preview = plain[:preview_bytes]
    copies = []
    for copy in copies_of(db, doc.id):
        try:
            head = _head(storage.read(copy.storage_key), ENTROPY_BYTES)
        except storage.StorageError:
            raise HTTPException(status_code=500, detail="STORAGE_ERROR")
        cipher_preview = head[:preview_bytes]
        copies.append({
            "algorithm": copy.algorithm,
            **CIPHERS[copy.algorithm],
            "plaintext_size": doc.size_bytes,
            "ciphertext_size": copy.ciphertext_size,
            "nonce_hex": copy.nonce.hex() if copy.nonce else None,
            "preview_hex": cipher_preview.hex(),
            "bytes_changed": sum(a != b for a, b in zip(preview, cipher_preview)),
            "entropy_bits_per_byte": round(_entropy(head), 4),
        })
    return {
        "document": {"id": str(doc.id), "type": doc.type, "ext": doc.ext, "size": doc.size_bytes},
        "plaintext_preview_hex": preview.hex(),
        "plaintext_entropy_bits_per_byte": round(_entropy(plain), 4),
        "preview_bytes": len(preview),
        "copies": copies,
    }
