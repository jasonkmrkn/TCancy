from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app import admin, auditing
from app.db import get_db
from app.deps import require_role
from app.models import User
from app.schemas import RejectIn, UserStatusIn

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

Admin = require_role("admin")


@router.get("/alumni")
def list_alumni(
    state: Literal["pending", "rejected", "approved"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(Admin),
    db: Session = Depends(get_db),
):
    return admin.list_alumni(db, state, limit, cursor)


@router.post("/alumni/{user_id}/approve")
def approve(request: Request, user_id: str, user: User = Depends(Admin), db: Session = Depends(get_db)):
    out = admin.approve_alumni(db, user, user_id)
    auditing.log(db, request, user, "admin.alumni_approve", "user", user_id)
    return out


@router.post("/alumni/{user_id}/reject")
def reject(
    request: Request, user_id: str, body: RejectIn, user: User = Depends(Admin), db: Session = Depends(get_db)
):
    out = admin.reject_alumni(db, user_id, body.reason)
    auditing.log(db, request, user, "admin.alumni_reject", "user", user_id)  # the reason text stays out
    return out


@router.get("/users")
def list_users(
    role: Literal["applicant", "alumni", "admin"] | None = None,
    status: Literal["pending", "active", "suspended"] | None = None,
    q: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(Admin),
    db: Session = Depends(get_db),
):
    return admin.list_users(db, role, status, q, limit, cursor)


@router.patch("/users/{user_id}/status")
def change_status(
    request: Request,
    user_id: str,
    body: UserStatusIn,
    user: User = Depends(Admin),
    db: Session = Depends(get_db),
):
    out = admin.change_user_status(db, user_id, body.status)
    auditing.log(db, request, user, "admin.user_status", "user", user_id, {"status": body.status})
    return out


@router.get("/overview")
def overview(_: User = Depends(Admin), db: Session = Depends(get_db)):
    return admin.overview(db)
