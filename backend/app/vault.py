"""Field vault: sensitive per-user fields stored encrypted in `encrypted_fields`.

Each field is encrypted with its own key (app.crypto, item "<field>:<user_id>"). With
ENCRYPTION_POLICY=assignment every write keeps three copies (aes, des, rc4); with production
only aes. Reads always use the aes copy. Copies left over from an earlier policy stay as they are.

Transaction rule: these functions only flush; the caller commits.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, crypto
from app.models import EncryptedField

ALGORITHMS = ("aes", "des", "rc4")
_ENCRYPT = {"aes": crypto.aes_encrypt, "des": crypto.des_encrypt, "rc4": crypto.rc4_encrypt}


def _item(field: str, user_id: uuid.UUID) -> str:
    return "%s:%s" % (field, user_id)


def _algorithms() -> tuple[str, ...]:
    return ALGORITHMS if config.ENCRYPTION_POLICY == "assignment" else ("aes",)


def _decrypt(row: EncryptedField) -> str:
    item = _item(row.field_name, row.user_id)
    return crypto.aes_decrypt(bytes(row.ciphertext), row.salt, row.nonce, item, 0).decode()


def store_field(db: Session, user_id: uuid.UUID, field: str, value: str) -> None:
    """Create or replace one field of a user. All copies are written, or none."""
    item = _item(field, user_id)
    data = value.encode()
    copies = {}
    # Encrypt every copy before touching the database, so a crypto failure writes nothing.
    for alg in _algorithms():
        salt, nonce = crypto.new_params(alg, item)
        copies[alg] = (salt, nonce, _ENCRYPT[alg](data, salt, nonce, item, 0))
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
        for alg, (salt, nonce, ciphertext) in copies.items():
            row = rows.get(alg)
            if row is None:
                row = EncryptedField(user_id=user_id, field_name=field, algorithm=alg)
                db.add(row)
            row.salt, row.nonce, row.ciphertext = salt, nonce, ciphertext


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
