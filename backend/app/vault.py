"""Field vault: sensitive per-user fields stored encrypted in `encrypted_fields`.

Each field is encrypted with its own key (app.crypto, item "<field>:<user_id>"). With
ENCRYPTION_POLICY=assignment every write keeps three copies (aes, des, rc4); with production
only aes. Reads always use the aes copy. Copies left over from an earlier policy stay as they are.

Every copy carries an integrity tag (app.integrity), checked on read when INTEGRITY_MODE is not
off. This is the only module that imports app.integrity; documents reaches it through the
*_file wrappers at the end.

Transaction rule: these functions only flush; the caller commits.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, crypto, integrity
from app.models import EncryptedField

ALGORITHMS = ("aes", "des", "rc4")
_ENCRYPT = {"aes": crypto.aes_encrypt, "des": crypto.des_encrypt, "rc4": crypto.rc4_encrypt}


def _item(field: str, user_id: uuid.UUID) -> str:
    return "%s:%s" % (field, user_id)


def _algorithms() -> tuple[str, ...]:
    return ALGORITHMS if config.ENCRYPTION_POLICY == "assignment" else ("aes",)


def _decrypt(row: EncryptedField) -> str:
    item = _item(row.field_name, row.user_id)
    ciphertext = bytes(row.ciphertext)
    if integrity.enabled():
        ok, _ = integrity.verify([ciphertext], [row.tag] if row.tag else [], "aes", item, row.salt, row.nonce)
        if not ok:
            integrity.fail("field %s of user %s" % (row.field_name, row.user_id))
    # errors="replace": under log-only a tampered value still comes back instead of crashing.
    return crypto.aes_decrypt(ciphertext, row.salt, row.nonce, item, 0).decode(errors="replace")


def store_field(db: Session, user_id: uuid.UUID, field: str, value: str) -> None:
    """Create or replace one field of a user. All copies are written, or none."""
    item = _item(field, user_id)
    data = value.encode()
    copies = {}
    # Encrypt every copy before touching the database, so a crypto failure writes nothing.
    for alg in _algorithms():
        salt, nonce = crypto.new_params(alg, item)
        ciphertext = _ENCRYPT[alg](data, salt, nonce, item, 0)
        copies[alg] = (salt, nonce, ciphertext, integrity.tag(alg, item, salt, nonce, 0, True, ciphertext))
    rows = {
        r.algorithm: r
        for r in db.scalars(
            select(EncryptedField).where(
                EncryptedField.user_id == user_id,
                EncryptedField.field_name == field,
                EncryptedField.algorithm.in_(copies),
            )
        )
    }
    # A savepoint, so a failed flush leaves no half-written copies and the caller's transaction intact.
    with db.begin_nested():
        for alg, (salt, nonce, ciphertext, tag) in copies.items():
            row = rows.get(alg)
            if row is None:
                row = EncryptedField(user_id=user_id, field_name=field, algorithm=alg)
                db.add(row)
            row.salt, row.nonce, row.ciphertext, row.tag = salt, nonce, ciphertext, tag


def load_field(db: Session, user_id: uuid.UUID, field: str) -> str | None:
    """The stored value, or None when the field was never stored."""
    row = db.scalar(
        select(EncryptedField).where(
            EncryptedField.user_id == user_id,
            EncryptedField.field_name == field,
            EncryptedField.algorithm == "aes",
        )
    )
    return None if row is None else _decrypt(row)


def load_fields(db: Session, user_ids: list[uuid.UUID], field: str) -> dict:
    """Batch load for lists. Returns {user_id: value}; missing users are absent."""
    rows = db.scalars(
        select(EncryptedField).where(
            EncryptedField.user_id.in_(user_ids),
            EncryptedField.field_name == field,
            EncryptedField.algorithm == "aes",
        )
    )
    return {row.user_id: _decrypt(row) for row in rows}


# Integrity for documents and benchmarks, which may not import app.integrity themselves.

def integrity_enabled() -> bool:
    return integrity.enabled()


def tag_file_chunk(alg: str, item: str, salt: bytes, nonce: bytes | None, index: int, last: bool, ciphertext: bytes) -> bytes:
    return integrity.tag(alg, item, salt, nonce, index, last, ciphertext)


def verify_file(chunks, tags: list[bytes], alg: str, item: str, salt: bytes, nonce: bytes | None, what: str) -> float:
    """Check a whole copy; returns the time spent on HMAC work in ms (for benchmarks)."""
    ok, ms = integrity.verify(chunks, tags, alg, item, salt, nonce)
    if not ok:
        integrity.fail(what)
    return ms
