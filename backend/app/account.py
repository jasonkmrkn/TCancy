from sqlalchemy.orm import Session

from app import documents, proof_purge, security
from app.models import User


def password_matches(user: User, password: str) -> bool:
    return security.verify_password(user.password_hash, password)

def delete_account(db: Session, user: User) -> None:
    """Delete the user. Profiles, sessions and other owned rows go away through
    the ON DELETE CASCADE foreign keys on users.id. Files on disk are removed too."""
    documents.purge_user_files(db, user.id)
    proof_keys = proof_purge.keys_for_user(db, user.id)  # A2 proofs and packages
    db.delete(user)
    db.commit()
    proof_purge.delete_files(proof_keys)  # after the commit, so a rollback loses no file
