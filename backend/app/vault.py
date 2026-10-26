# STUB-AXEL
"""Field vault: sensitive per-user fields stored in `encrypted_fields`.

Interface-stub stage: values are kept as plain text bytes with algorithm="stub",
a zero salt and no nonce, so nothing here can be mistaken for real encryption.
The real implementation replaces this module.

Transaction rule: these functions only flush; the caller commits.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EncryptedField

STUB_ALGORITHM = "stub"
_ZERO_SALT = bytes(16)


def _row(db: Session, user_id: uuid.UUID, field: str) -> EncryptedField | None:
    return db.scalar(
        select(EncryptedField).where(
            EncryptedField.user_id == user_id,
            EncryptedField.field_name == field,
            EncryptedField.algorithm == STUB_ALGORITHM,
        )
    )


# STUB-AXEL
def store_field(db: Session, user_id: uuid.UUID, field: str, value: str) -> None:
    """Frozen interface: create or replace one field of a user."""
    row = _row(db, user_id, field)
    data = value.encode()
    if row is None:
        db.add(
            EncryptedField(
                user_id=user_id,
                field_name=field,
                algorithm=STUB_ALGORITHM,
                salt=_ZERO_SALT,
                nonce=None,
                ciphertext=data,
            )
        )
    else:
        row.ciphertext = data
    db.flush()


# STUB-AXEL
def load_field(db: Session, user_id: uuid.UUID, field: str) -> str | None:
    """Frozen interface: the stored value, or None when the field was never stored."""
    row = _row(db, user_id, field)
    return None if row is None else bytes(row.ciphertext).decode()


# STUB-AXEL
def load_fields(db: Session, user_ids: list[uuid.UUID], field: str) -> dict:
    """Frozen interface: batch load for lists. Returns {user_id: value}; missing users are absent."""
    rows = db.execute(
        select(EncryptedField.user_id, EncryptedField.ciphertext).where(
            EncryptedField.user_id.in_(user_ids),
            EncryptedField.field_name == field,
            EncryptedField.algorithm == STUB_ALGORITHM,
        )
    )
    return {uid: bytes(ct).decode() for uid, ct in rows}