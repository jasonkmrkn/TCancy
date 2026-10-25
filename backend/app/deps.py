from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, user_for_token
from app.db import get_db
from app.models import User


def get_current_user(
    access_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    user = user_for_token(db, access_token)
    if user is None:
        raise HTTPException(status_code=401, detail="not logged in")
    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="ACCOUNT_SUSPENDED")
    return user


def require_role(*roles: str, allow_pending: bool = False):
    """Dependency: logged in, role in `roles`, and active (pending only if allow_pending)."""

    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="forbidden")
        if user.status == "pending" and not allow_pending:
            raise HTTPException(status_code=403, detail="ACCOUNT_PENDING")
        return user

    return dep
