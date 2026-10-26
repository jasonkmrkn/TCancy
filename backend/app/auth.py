import logging
import uuid
from datetime import datetime, timezone

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import config, tokens
from app.models import RefreshToken, User

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
# The refresh cookie is only sent to the auth endpoints, never to the rest of the API.
REFRESH_COOKIE_PATH = "/api/v1/auth"

log = logging.getLogger("tcancy.auth")


class InvalidRefreshToken(Exception):
    """Missing, unknown, expired or replayed refresh token. The caller must log in again."""

class SuspendedAccount(Exception):
    """The refresh token is fine but the account has been suspended since."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def set_auth_cookies(response: Response, access_token: str, refresh_token: str, csrf_token: str ) -> None:
    common = dict(httponly=True, secure=config.COOKIE_SECURE, samesite="lax")
    response.set_cookie(
        ACCESS_COOKIE, access_token, max_age=config.ACCESS_TOKEN_MINUTES * 60, path="/", **common
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=config.REFRESH_TOKEN_DAYS * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        **common,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=config.REFRESH_TOKEN_DAYS * 24 * 3600,
        path="/",
        httponly=False,
        secure=config.COOKIE_SECURE,
        samesite="lax",
    )


def clear_auth_cookies(response: Response) -> None:
    common = dict(httponly=True, secure=config.COOKIE_SECURE, samesite="lax")
    response.delete_cookie(ACCESS_COOKIE, path="/", **common)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, **common)
    response.delete_cookie(CSRF_COOKIE, path="/", httponly=False, secure=config.COOKIE_SECURE, samesite="lax")


def _new_refresh_row(user_id: uuid.UUID, family_id: uuid.UUID, now: datetime):
    raw = tokens.new_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        token_hash=tokens.hash_refresh_token(raw),
        expires_at=tokens.refresh_expiry(now),
    )
    return row, raw


def _revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def start_session(db: Session, user: User) -> tuple[str, str]:
    now = _now()
    access = tokens.create_access_token(user.id, now)  # first: a bad secret leaves no rows
    row, refresh = _new_refresh_row(user.id, uuid.uuid4(), now)
    db.add(row)
    user.last_login_at = now
    db.commit()
    return access, refresh


def _replayed(db: Session, row: RefreshToken, now: datetime) -> InvalidRefreshToken:
    _revoke_family(db, row.family_id, now)
    db.commit()
    log.warning("refresh token reuse: revoked family %s of user %s", row.family_id, row.user_id)
    return InvalidRefreshToken()


def rotate_refresh_token(db: Session, raw_token: str | None) -> tuple[User, str, str]:
    if not raw_token:
        raise InvalidRefreshToken()
    now = _now()
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == tokens.hash_refresh_token(raw_token))
    )
    if row is None:
        raise InvalidRefreshToken()
    if row.revoked_at is not None:
        raise _replayed(db, row, now)
    if row.expires_at <= now:
        raise InvalidRefreshToken()
    user = db.get(User, row.user_id)
    if user is None:
        raise InvalidRefreshToken()
    if user.status == "suspended":
        _revoke_family(db, row.family_id, now)
        db.commit()
        raise SuspendedAccount()

    spent = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    ).rowcount
    if spent != 1:
        raise _replayed(db, row, now)

    access = tokens.create_access_token(user.id, now)
    next_row, next_raw = _new_refresh_row(user.id, row.family_id, now)
    db.add(next_row)
    db.commit()
    return user, access, next_raw


def end_session(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == tokens.hash_refresh_token(raw_token))
    )
    if row is not None:
        _revoke_family(db, row.family_id, _now())
        db.commit()