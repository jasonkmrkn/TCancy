import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit, auth, csrf, limits, profiles, security
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import AlumniRegisterIn, AlumniRegisterWithProfileIn, LoginIn, RegisterIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

log = logging.getLogger("tcancy.auth")


def user_out(user: User) -> dict:
    return {"id": str(user.id), "username": user.username, "role": user.role, "status": user.status}

def _refresh_failed(status_code: int, detail: str) -> JSONResponse:
    failed = JSONResponse({"detail": detail}, status_code=status_code)
    auth.clear_auth_cookies(failed)
    return failed

def _register(db: Session, request: Request, body: AlumniRegisterIn, role: str, status: str, profile=None) -> dict:
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise HTTPException(status_code=409, detail="USERNAME_TAKEN")
    if role == "applicant":
        # Early rejection, before the costly password hash.
        profiles.check_skills(db, profile.skill_ids)
        profiles.check_unique(db, profile)
    user = User(
        username=body.username,
        password_hash=security.hash_password(body.password),
        role=role,
        status=status,
    )

    db.add(user)
    try:
        db.flush()
        if role == "applicant":
            profiles.create_applicant(db, user, profile)
        else:
            profiles.create_alumni(db, user, profile)
        audit.record(
            db, actor_id=user.id, actor_role=role, action="auth.register",
            target_type="user", target_id=user.id, **audit.client(request),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        code = profiles.conflict_code(exc)
        if code is None:
            raise
        raise HTTPException(status_code=409, detail=code) from None
    except Exception:
        db.rollback()
        raise
    db.refresh(user)
    return user_out(user)


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    limits.register(request)
    return _register(db, request, body, "applicant", "active", body.profile)


@router.post("/register/alumni", status_code=201)
def register_alumni(body: AlumniRegisterWithProfileIn, request: Request, db: Session = Depends(get_db)):
    limits.register(request)
    return _register(db, request, body, "alumni", "pending", body.profile)

def _login_failed(db: Session, request: Request, user: User | None, suspended: bool = False) -> None:
    audit.record(
        db, actor_id=None, actor_role=None, action="auth.login_failed",
        target_type="user" if user is not None else None, target_id=user.id if user is not None else None,
        details=audit.details(known_user=int(user is not None), suspended=int(suspended)), **audit.client(request),
    )
    db.commit()


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    limits.login(request, body.username)  
    user = db.scalar(select(User).where(User.username == body.username))
    stored_hash = user.password_hash if user is not None else security.DUMMY_HASH
    password_ok = security.verify_password(stored_hash, body.password)
    if user is None or not password_ok:
        _login_failed(db, request, user)
        raise HTTPException(status_code=401, detail="invalid username or password")
    if user.status == "suspended":
        _login_failed(db, request, user, suspended=True)
        raise HTTPException(status_code=403, detail="ACCOUNT_SUSPENDED")
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(body.password)
    audit.record(
        db, actor_id=user.id, actor_role=user.role, action="auth.login",
        target_type="user", target_id=user.id, **audit.client(request),
    )
    access_token, refresh_token = auth.start_session(db, user)
    auth.set_auth_cookies(response, access_token, refresh_token, csrf.new_csrf_token())
    return user_out(user)

def _audit_reuse(db: Session, request: Request, reuse: auth.RefreshTokenReused) -> None:
    with audit.quietly(db, "auth.refresh_reuse"):
        owner = db.get(User, reuse.user_id)
        audit.record(
            db, actor_id=reuse.user_id, actor_role=owner.role if owner is not None else None,
            action="auth.refresh_reuse", target_type="refresh_family", target_id=reuse.family_id,
            details=audit.details(revoked_tokens=reuse.revoked), **audit.client(request),
        )
        db.commit()

@router.post("/refresh")
def refresh(
    request: Request,
    refresh_token: str | None = Cookie(default=None, alias=auth.REFRESH_COOKIE),
    csrf_token: str | None = Cookie(default=None, alias=auth.CSRF_COOKIE),
    db: Session = Depends(get_db),
):
    try:
        _user, access_token, new_refresh_token = auth.rotate_refresh_token(db, refresh_token)
    except auth.SuspendedAccount:
        return _refresh_failed(403, "ACCOUNT_SUSPENDED")
    except auth.RefreshTokenReused as reuse:
        _audit_reuse(db, request, reuse)
        return _refresh_failed(401, "invalid refresh token")
    except auth.InvalidRefreshToken:
        return _refresh_failed(401, "invalid refresh token")
    ok = JSONResponse({"ok": True})
    auth.set_auth_cookies(ok, access_token, new_refresh_token, csrf_token or csrf.new_csrf_token())
    return ok

@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=auth.REFRESH_COOKIE),

    db: Session = Depends(get_db),
):
    user_id = auth.end_session(db, refresh_token)
    if user_id is not None:
        with audit.quietly(db, "auth.logout"):  # the session is already ended: a failure here changes nothing
            owner = db.get(User, user_id)
            audit.record(
                db, actor_id=user_id, actor_role=owner.role if owner is not None else None,
                action="auth.logout", target_type="user", target_id=user_id, **audit.client(request),
            )
            db.commit()

    auth.clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)
