import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app import auditing, jobs
from app.db import get_db
from app.deps import require_role
from app.models import User
from app.schemas import JobIn

router = APIRouter(prefix="/api/v1", tags=["jobs"])


@router.get("/jobs")
def list_jobs(
    type: str | None = None,
    work_mode: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    location: str | None = Query(default=None, max_length=100),
    skill: list[uuid.UUID] = Query(default=[], max_length=20),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    return jobs.search(
        db, type=type, work_mode=work_mode, q=q, location=location,
        skill=skill, limit=limit, cursor=cursor,
    )


@router.get("/me/jobs")
def my_jobs(
    user: User = Depends(require_role("alumni", "admin")),
    db: Session = Depends(get_db),
):
    return jobs.summaries(db, jobs.owned_by(db, user))


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return jobs.detail(db, jobs.get(db, job_id))


@router.post("/jobs", status_code=201)
def create_job(
    request: Request,
    body: JobIn,
    user: User = Depends(require_role("alumni", "admin")),
    db: Session = Depends(get_db),
):
    row = jobs.create(db, user, body)
    auditing.log(db, request, user, "job.create", "job", row.id)
    return jobs.detail(db, row)


@router.put("/jobs/{job_id}")
def update_job(
    request: Request,
    job_id: str,
    body: JobIn,
    user: User = Depends(require_role("alumni", "admin")),
    db: Session = Depends(get_db),
):
    row = jobs.update(db, user, job_id, body)
    auditing.log(db, request, user, "job.update", "job", row.id)
    return jobs.detail(db, row)


@router.post("/jobs/{job_id}/close")
def close_job(
    request: Request,
    job_id: str,
    user: User = Depends(require_role("alumni", "admin")),
    db: Session = Depends(get_db),
):
    row = jobs.close(db, user, job_id)
    auditing.log(db, request, user, "job.close", "job", row.id)
    return jobs.detail(db, row)
