from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security, storage
from app.models import Document, User


def password_matches(user: User, password: str) -> bool:
    return security.verify_password(user.password_hash, password)

def delete_account(db: Session, user: User) -> None:
    """Delete the user. Profiles, sessions and other owned rows go away through
    the ON DELETE CASCADE foreign keys on users.id. Files on disk are removed too."""
    keys = list(db.scalars(select(Document.storage_key).where(Document.owner_id == user.id)))
    db.delete(user)
    db.commit()
    for key in keys:
        storage.delete(key)
