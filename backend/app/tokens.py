"""Access tokens (signed JWT) and refresh-token helpers.

Pure functions: nothing here touches the database. An access token only proves who
the caller is for a few minutes; the user row is still loaded from the database on
every request, so a suspension or role change applies immediately. Refresh tokens are
opaque random strings, and only their SHA-256 hash is ever stored.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app import config

ALGORITHM = "HS256"
ACCESS_TYPE = "access"
MIN_SECRET_BYTES = 32
REQUIRED_CLAIMS = ["exp", "iat", "sub", "jti", "typ"]


def check_secret() -> None:
    """Raise unless SESSION_SECRET is set to at least 32 bytes. Meant to run at startup."""
    if len(config.SESSION_SECRET.encode()) < MIN_SECRET_BYTES:
        raise RuntimeError(
            "SESSION_SECRET must be set to at least 32 bytes, e.g. `openssl rand -hex 32`"
        )


def _utc(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def create_access_token(user_id: uuid.UUID, now: datetime | None = None) -> str:
    """Sign an access token. `now` exists so tests can mint an already-expired token."""
    check_secret()
    issued = _utc(now)
    claims = {
        "sub": str(user_id),
        "iat": issued,
        "exp": issued + timedelta(minutes=config.ACCESS_TOKEN_MINUTES),
        "jti": uuid.uuid4().hex,
        "typ": ACCESS_TYPE,
    }
    return jwt.encode(claims, config.SESSION_SECRET, algorithm=ALGORITHM)


def verify_access_token(token: str | None) -> uuid.UUID | None:
    """The user id inside a valid access token, or None for anything wrong with it.

    A misconfigured secret raises instead of returning None: that is a server fault
    and must not look like "not logged in".
    """
    if not token:
        return None
    check_secret()
    try:
        claims = jwt.decode(
            token,
            config.SESSION_SECRET,
            algorithms=[ALGORITHM],  # pinned: rejects "none" and any other algorithm
            options={"require": REQUIRED_CLAIMS},
        )
        if claims["typ"] != ACCESS_TYPE:
            return None
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None


def new_refresh_token() -> str:
    """A fresh opaque refresh token (256 bits). Give this to the client, never store it."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """What gets stored and looked up. SHA-256 is enough because the input is random."""
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_expiry(now: datetime | None = None) -> datetime:
    return _utc(now) + timedelta(days=config.REFRESH_TOKEN_DAYS)