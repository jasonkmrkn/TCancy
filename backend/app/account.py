from sqlalchemy.orm import Session

from app import documents, security
from app.models import User


def password_matches(user: User, password: str) -> bool:
    return security.verify_password(user.password_hash, password)

def delete_account(db: Session, user: User) -> None:
    """Delete the user. Profiles, sessions and other owned rows go away through
    the ON DELETE CASCADE foreign keys on users.id. Files on disk are removed too."""
    documents.purge_user_files(db, user.id)
    db.delete(user)
    db.commit()
