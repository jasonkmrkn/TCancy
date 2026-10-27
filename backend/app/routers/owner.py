from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app import auditing, owner
from app.db import get_db
from app.deps import require_role
from app.models import User
from app.schemas import StatusChangeIn

router = APIRouter(prefix="/api/v1", tags=["owner"])

Owner = require_role("alumni", "admin")

# The refusals worth an audit entry: somebody tried to open data they may not see yet.
DENIED = {"NOT_VISIBLE", "IDENTITY_LOCKED", "IDENTITY_EXPIRED", "DOWNLOAD_LIMIT"}


def _guarded(request: Request, db: Session, user: User, app_id: str, action: str, open_file):
    """Open one protected resource and record the outcome: the action, or owner.access_denied."""
    row = owner.get_application(db, user, app_id)  # another owner's application is still a plain 404
    try:
        out = open_file(db, row, user)
    except HTTPException as exc:
        if exc.detail in DENIED:
            auditing.log(db, request, user, "owner.access_denied", "application", app_id,
                         {"action": action, "reason": exc.detail})
        raise
    auditing.log(db, request, user, action, "application", app_id)
    return out


@router.get("/jobs/{job_id}/applications")
def list_applications(
    request: Request,
    job_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(Owner),
    db: Session = Depends(get_db),
):
    out = owner.list_for_job(db, user, job_id, limit, cursor)
    auditing.log(db, request, user, "owner.view_applicants", "job", job_id, {"count": len(out["items"])})
    return out


@router.get("/applications/{app_id}")
def get_application(app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return owner.detail_view(db, owner.get_application(db, user, app_id), user)


@router.patch("/applications/{app_id}/status")
def change_status(
    request: Request,
    app_id: str,
    body: StatusChangeIn,
    user: User = Depends(Owner),
    db: Session = Depends(get_db),
):
    row = owner.change_status(db, user, app_id, body.status, body.note)
    auditing.log(db, request, user, "application.status_change", "application", row.id, {"to": row.status})
    return owner.detail_view(db, row, user)


@router.get("/applications/{app_id}/cv")
def download_cv(request: Request, app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return _guarded(request, db, user, app_id, "owner.download_cv", owner.cv_file)


@router.get("/applications/{app_id}/video")
def download_video(request: Request, app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return _guarded(request, db, user, app_id, "owner.download_video", owner.video_file)


@router.get("/applications/{app_id}/identity")
def identity(request: Request, app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return _guarded(request, db, user, app_id, "owner.view_identity", owner.identity_view)


@router.get("/applications/{app_id}/identity/ktp")
def identity_ktp(request: Request, app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return _guarded(request, db, user, app_id, "owner.download_ktp", owner.ktp_file)
