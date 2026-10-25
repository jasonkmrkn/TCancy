import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import jobs
from app.models import ROLES, STATUSES, AlumniProfile, Application, Document, Job, User
from app.profiles import alumni_profile_complete, alumni_verification, get_alumni_profile

APPLICATION_STATUSES = ("submitted", "shortlisted", "accepted", "rejected", "withdrawn")
JOB_STATUSES = ("open", "closed")
DOCUMENT_TYPES = ("cv", "ktp", "intro_video")

# Same meaning as profiles.alumni_verification, expressed for SQL.
_APPROVED = or_(AlumniProfile.verified_at.is_not(None), User.status == "active")
_REJECTED = (~_APPROVED) & AlumniProfile.rejected_at.is_not(None)
_PENDING = (~_APPROVED) & AlumniProfile.rejected_at.is_(None)


def _alumni_or_404(db: Session, user_id: str) -> User:
    try:
        ident = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="ALUMNI_NOT_FOUND")
    user = db.get(User, ident)
    if user is None or user.role != "alumni":
        raise HTTPException(status_code=404, detail="ALUMNI_NOT_FOUND")
    return user


def _after_cursor(query, cursor: str | None):
    if not cursor:
        return query
    created_at, ident = jobs.decode_cursor(cursor)
    return query.where(
        or_(User.created_at < created_at, (User.created_at == created_at) & (User.id < ident))
    )


def list_alumni(db: Session, state: str | None, limit: int, cursor: str | None) -> dict:
    query = (
        select(User, AlumniProfile)
        .outerjoin(AlumniProfile, AlumniProfile.user_id == User.id)
        .where(User.role == "alumni")
    )
    if state == "approved":
        query = query.where(_APPROVED)
    elif state == "rejected":
        query = query.where(_REJECTED)
    elif state == "pending":
        query = query.where(_PENDING)
    query = _after_cursor(query, cursor)
    rows = db.execute(
        query.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    items = []
    for user, profile in page:
        if profile is None:
            profile = AlumniProfile(user_id=user.id)
        items.append(
            {
                "id": str(user.id),
                "username": user.username,
                "account_status": user.status,
                "verification": alumni_verification(user, profile),
                "full_name": profile.full_name,
                "company": profile.company,
                "angkatan": profile.angkatan,
                "profile_complete": alumni_profile_complete(profile),
                "created_at": user.created_at.isoformat(),
            }
        )
    next_cursor = jobs.encode_cursor(page[-1][0]) if len(rows) > limit else None
    return {"items": items, "next_cursor": next_cursor}


def _account_out(user: User) -> dict:
    return {"id": str(user.id), "username": user.username, "role": user.role, "status": user.status}


def approve_alumni(db: Session, admin: User, user_id: str) -> dict:
    user = _alumni_or_404(db, user_id)
    profile = get_alumni_profile(db, user.id)
    if user.status == "suspended":
        raise HTTPException(status_code=409, detail="ACCOUNT_SUSPENDED")
    if alumni_verification(user, profile)["state"] == "approved":
        raise HTTPException(status_code=409, detail="ALREADY_APPROVED")
    if not alumni_profile_complete(profile):
        raise HTTPException(status_code=409, detail="PROFILE_INCOMPLETE")
    user.status = "active"
    profile.verified_at = datetime.now(timezone.utc)
    profile.verified_by = admin.id
    profile.rejected_at = None
    profile.rejection_reason = None
    db.commit()
    return _account_out(user)


def reject_alumni(db: Session, user_id: str, reason: str) -> dict:
    user = _alumni_or_404(db, user_id)
    profile = get_alumni_profile(db, user.id)
    if user.status != "pending" or alumni_verification(user, profile)["state"] != "pending":
        raise HTTPException(status_code=409, detail="NOT_PENDING")
    profile.rejected_at = datetime.now(timezone.utc)
    profile.rejection_reason = reason
    db.commit()
    return _account_out(user)


def _user_view(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at.isoformat(),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def list_users(
    db: Session, role: str | None, status: str | None, q: str | None, limit: int, cursor: str | None
) -> dict:
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(User.username.ilike("%" + escaped + "%", escape="\\"))
    query = _after_cursor(query, cursor)
    rows = list(db.scalars(query.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    next_cursor = jobs.encode_cursor(page[-1]) if len(rows) > limit else None
    return {"items": [_user_view(u) for u in page], "next_cursor": next_cursor}


def change_user_status(db: Session, user_id: str, status: str) -> dict:
    try:
        ident = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    user = db.get(User, ident)
    if user is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="CANNOT_MODIFY_ADMIN")
    target = status
    if status == "active" and user.role == "alumni":
        # Reactivating must not skip approval: unverified alumni go back to pending.
        if get_alumni_profile(db, user.id).verified_at is None:
            target = "pending"
    if user.status == target:
        raise HTTPException(status_code=409, detail="NO_CHANGE")
    user.status = target
    db.commit()
    db.refresh(user)
    return _user_view(user)


def _counts(db: Session, column, keys: tuple[str, ...]) -> dict:
    found = dict(db.execute(select(column, func.count()).group_by(column)).all())
    return {k: int(found.get(k, 0)) for k in keys}


def overview(db: Session) -> dict:
    awaiting = db.scalar(
        select(func.count())
        .select_from(User)
        .outerjoin(AlumniProfile, AlumniProfile.user_id == User.id)
        .where(User.role == "alumni", User.status == "pending", _PENDING)
    )
    return {
        "users_by_role": _counts(db, User.role, ROLES),
        "users_by_status": _counts(db, User.status, STATUSES),
        "jobs_by_status": _counts(db, Job.status, JOB_STATUSES),
        "applications_by_status": _counts(db, Application.status, APPLICATION_STATUSES),
        "documents_by_type": _counts(db, Document.type, DOCUMENT_TYPES),
        "alumni_awaiting_decision": int(awaiting or 0),
    }
