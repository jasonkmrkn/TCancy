from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app import tokens
from app.auth import ACCESS_COOKIE
from app.db import get_db
from app.models import User


def get_current_user(
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    user_id = tokens.verify_access_token(access_token)
    user = db.get(User, user_id) if user_id is not None else None
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
