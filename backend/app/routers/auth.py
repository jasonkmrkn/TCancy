from urllib import response

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth, profiles, security
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import AlumniRegisterIn, LoginIn, RegisterIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def user_out(user: User) -> dict:
    return {"id": str(user.id), "username": user.username, "role": user.role, "status": user.status}

def _refresh_failed(status_code: int, detail: str) -> JSONResponse:
    failed = JSONResponse({"detail": detail}, status_code=status_code)
    auth.clear_auth_cookies(failed)
    return failed

def _register(db: Session, body: AlumniRegisterIn, role: str, status: str, profile=None) -> dict:
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise HTTPException(status_code=409, detail="USERNAME_TAKEN")
    if profile is not None:
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
        if profile is not None:
            profiles.create_applicant_profile(db, user.id, profile)
        else:
            profiles.get_alumni_profile(db, user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="USERNAME_TAKEN")
    db.refresh(user)
    return user_out(user)


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    return _register(db, body, "applicant", "active", body.profile)


@router.post("/register/alumni", status_code=201)
def register_alumni(body: AlumniRegisterIn, db: Session = Depends(get_db)):
    return _register(db, body, "alumni", "pending")


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    stored_hash = user.password_hash if user is not None else security.DUMMY_HASH
    password_ok = security.verify_password(stored_hash, body.password)
    if user is None or not password_ok:
        raise HTTPException(status_code=401, detail="invalid username or password")
    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="ACCOUNT_SUSPENDED")
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(body.password)
    access_token, refresh_token = auth.start_session(db, user)
    auth.set_auth_cookies(response, access_token, refresh_token)
    return user_out(user)

@router.post("/refresh")
def refresh(
    refresh_token: str | None = Cookie(default=None, alias=auth.REFRESH_COOKIE),
    db: Session = Depends(get_db),
):
    try:
        _user, access_token, new_refresh_token = auth.rotate_refresh_token(db, refresh_token)
    except auth.SuspendedAccount:
        return _refresh_failed(403, "ACCOUNT_SUSPENDED")
    except auth.InvalidRefreshToken:
        return _refresh_failed(401, "invalid refresh token")
    ok = JSONResponse({"ok": True})
    auth.set_auth_cookies(ok, access_token, new_refresh_token)
    return ok

@router.post("/logout")
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=auth.REFRESH_COOKIE),

    db: Session = Depends(get_db),
):
    auth.end_session(db, refresh_token)
    auth.clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)
