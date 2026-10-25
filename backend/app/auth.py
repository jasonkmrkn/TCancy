import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Session as SessionRow
from app.models import User

COOKIE_NAME = "access_token"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def create_session(db: Session, user: User) -> str:
    token = new_token()
    db.add(SessionRow(token=token, user_id=user.id))
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return token


def delete_session(db: Session, token: str | None) -> None:
    if not token:
        return
    row = db.scalar(select(SessionRow).where(SessionRow.token == token))
    if row is not None:
        db.delete(row)
        db.commit()


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    return db.scalar(
        select(User).join(SessionRow, SessionRow.user_id == User.id).where(SessionRow.token == token)
    )
