import hmac
import secrets

from fastapi import HTTPException, Request

from app import auth

CSRF_HEADER = "X-CSRF-Token"

# Methods that must not change state; everything else is checked.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

EXEMPT = frozenset({
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/register/alumni"),
    ("POST", "/api/v1/auth/login"),
})


def new_csrf_token() -> str:
    """A fresh random token (256 bits). Set it as a cookie; never store it server-side."""
    return secrets.token_urlsafe(32)


def verify_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    route = request.scope.get("route")
    if route is not None and (request.method, route.path) in EXEMPT:
        return
    if not (request.cookies.get(auth.ACCESS_COOKIE) or request.cookies.get(auth.REFRESH_COOKIE)):
        return 
    cookie = request.cookies.get(auth.CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not hmac.compare_digest(cookie.encode(), header.encode()):
        raise HTTPException(status_code=403, detail="CSRF_FAILED")