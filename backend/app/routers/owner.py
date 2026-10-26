from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import owner
from app.db import get_db
from app.deps import require_role
from app.models import User
from app.schemas import StatusChangeIn

router = APIRouter(prefix="/api/v1", tags=["owner"])

Owner = require_role("alumni", "admin")


@router.get("/jobs/{job_id}/applications")
def list_applications(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(Owner),
    db: Session = Depends(get_db),
):
    return owner.list_for_job(db, user, job_id, limit, cursor)


@router.get("/applications/{app_id}")
def get_application(app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return owner.detail_view(db, owner.get_application(db, user, app_id), user)


@router.patch("/applications/{app_id}/status")
def change_status(
    app_id: str,
    body: StatusChangeIn,
    user: User = Depends(Owner),
    db: Session = Depends(get_db),
):
    row = owner.change_status(db, user, app_id, body.status, body.note)
    return owner.detail_view(db, row, user)


@router.get("/applications/{app_id}/cv")
def download_cv(app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return owner.cv_file(db, owner.get_application(db, user, app_id), user)


@router.get("/applications/{app_id}/video")
def download_video(app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return owner.video_file(db, owner.get_application(db, user, app_id), user)


@router.get("/applications/{app_id}/identity")
def identity(app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return owner.identity_view(db, owner.get_application(db, user, app_id))


@router.get("/applications/{app_id}/identity/ktp")
def identity_ktp(app_id: str, user: User = Depends(Owner), db: Session = Depends(get_db)):
    return owner.ktp_file(db, owner.get_application(db, user, app_id))
