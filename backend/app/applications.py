import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import jobs
from app.models import Application, ApplicationStatusHistory, Document, Job, User
from app.schemas import ApplyIn

FINAL = ("rejected", "withdrawn")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="APPLICATION_NOT_FOUND")


def _owned_document(db: Session, user: User, doc_id: uuid.UUID | None, doc_type: str) -> Document | None:
    if doc_id is None:
        return None
    doc = db.scalar(select(Document).where(Document.id == doc_id, Document.owner_id == user.id))
    if doc is None or doc.type != doc_type:
        raise HTTPException(status_code=422, detail="invalid document")
    return doc


def apply(db: Session, user: User, job_id: str, data: ApplyIn) -> Application:
    job = jobs.get(db, job_id)
    if job.status == "closed":
        raise HTTPException(status_code=409, detail="JOB_CLOSED")
    if job.deadline is not None and job.deadline < date.today():
        raise HTTPException(status_code=409, detail="JOB_EXPIRED")
    exists = db.scalar(
        select(Application.id).where(Application.job_id == job.id, Application.applicant_id == user.id)
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="ALREADY_APPLIED")
    cv = _owned_document(db, user, data.cv_document_id, "cv")
    video = _owned_document(db, user, data.intro_video_document_id, "intro_video")

    row = Application(
        job_id=job.id,
        applicant_id=user.id,
        cover_note=data.cover_note or None,
        cv_document_id=cv.id,
        intro_video_document_id=video.id if video else None,
    )
    db.add(row)
    try:
        db.flush()
        db.add(ApplicationStatusHistory(
            application_id=row.id, from_status=None, to_status="submitted", changed_by=user.id,
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="ALREADY_APPLIED")
    db.refresh(row)
    return row


def _jobs_of(db: Session, rows: list[Application]) -> dict[uuid.UUID, dict]:
    ids = list({r.job_id for r in rows})
    found = list(db.scalars(select(Job).where(Job.id.in_(ids)))) if ids else []
    return {j.id: s for j, s in zip(found, jobs.summaries(db, found))}


def summary_views(db: Session, rows: list[Application]) -> list[dict]:
    by_job = _jobs_of(db, rows)
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "job": by_job[r.job_id],
        }
        for r in rows
    ]


def history_of(db: Session, app_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == app_id)
        .order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)
    )
    return [
        {
            "from_status": h.from_status,
            "to_status": h.to_status,
            "note": h.note,
            "created_at": h.created_at.isoformat(),
        }
        for h in rows
    ]


def detail_view(db: Session, row: Application) -> dict:
    return {
        "id": str(row.id),
        "job": _jobs_of(db, [row])[row.job_id],
        "status": row.status,
        "cover_note": row.cover_note,
        "cv_document_id": str(row.cv_document_id) if row.cv_document_id else None,
        "intro_video_document_id": (
            str(row.intro_video_document_id) if row.intro_video_document_id else None
        ),
        "created_at": row.created_at.isoformat(),
        "history": history_of(db, row.id),
    }


def list_for(db: Session, user: User) -> list[Application]:
    return list(db.scalars(
        select(Application)
        .where(Application.applicant_id == user.id)
        .order_by(Application.created_at.desc(), Application.id.desc())
        .limit(200)
    ))


def get_owned(db: Session, user: User, app_id: str) -> Application:
    try:
        ident = uuid.UUID(app_id)
    except ValueError:
        raise _not_found()
    row = db.scalar(
        select(Application).where(Application.id == ident, Application.applicant_id == user.id)
    )
    if row is None:
        raise _not_found()
    return row


def withdraw(db: Session, user: User, app_id: str) -> Application:
    row = get_owned(db, user, app_id)
    if row.status in FINAL:
        raise HTTPException(status_code=409, detail="INVALID_STATUS")
    db.add(ApplicationStatusHistory(
        application_id=row.id, from_status=row.status, to_status="withdrawn", changed_by=user.id,
    ))
    row.status = "withdrawn"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
