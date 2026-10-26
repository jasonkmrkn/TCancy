import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import applications, documents, jobs, vault
from app.models import (
    Application,
    ApplicantProfile,
    ApplicantSkill,
    ApplicationStatusHistory,
    Document,
    Job,
    Skill,
    User,
)

# Allowed moves by the job owner (plan 6.1). rejected and withdrawn are final.
TRANSITIONS = {
    "submitted": {"shortlisted", "accepted", "rejected"},
    "shortlisted": {"accepted", "rejected"},
    "accepted": {"shortlisted", "rejected"},
}


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="APPLICATION_NOT_FOUND")


def own_job(db: Session, user: User, job_id: str) -> Job:
    job = jobs.get(db, job_id)
    if job.owner_id != user.id:
        raise HTTPException(status_code=403, detail="NOT_JOB_OWNER")
    return job


def get_application(db: Session, user: User, app_id: str) -> Application:
    """An application on a job the user owns; anything else looks like it does not exist."""
    try:
        ident = uuid.UUID(app_id)
    except ValueError:
        raise _not_found()
    row = db.scalar(
        select(Application)
        .join(Job, Job.id == Application.job_id)
        .where(Application.id == ident, Job.owner_id == user.id)
    )
    if row is None:
        raise _not_found()
    return row


def _document_view(doc: Document | None) -> dict | None:
    if doc is None:
        return None
    return {
        "id": str(doc.id),
        "ext": doc.ext,
        "size": doc.size_bytes,
        "created_at": doc.created_at.isoformat(),
    }


def _applicant_views(db: Session, rows: list[Application]) -> dict[uuid.UUID, dict]:
    ids = list({r.applicant_id for r in rows})
    out: dict[uuid.UUID, dict] = {}
    if not ids:
        return out
    skills: dict[uuid.UUID, list[dict]] = {i: [] for i in ids}
    for uid, sid, name in db.execute(
        select(ApplicantSkill.user_id, Skill.id, Skill.name)
        .join(Skill, Skill.id == ApplicantSkill.skill_id)
        .where(ApplicantSkill.user_id.in_(ids))
        .order_by(Skill.name)
    ):
        skills[uid].append({"id": str(sid), "name": name})
    names = vault.load_fields(db, ids, "full_name")
    emails = vault.load_fields(db, ids, "email")
    phones = vault.load_fields(db, ids, "phone")
    for p in db.scalars(select(ApplicantProfile).where(ApplicantProfile.user_id.in_(ids))):
        out[p.user_id] = {
            "full_name": names.get(p.user_id),
            "email": emails.get(p.user_id),
            "angkatan": p.angkatan,
            "skills": skills[p.user_id],
            "phone": phones.get(p.user_id),
        }
    return out


def _documents_of(db: Session, rows: list[Application]) -> dict[uuid.UUID, Document]:
    ids = {r.cv_document_id for r in rows if r.cv_document_id}
    ids |= {r.intro_video_document_id for r in rows if r.intro_video_document_id}
    if not ids:
        return {}
    return {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(ids)))}


def _base_view(row: Application, applicant: dict | None, docs: dict[uuid.UUID, Document]) -> dict:
    return {
        "id": str(row.id),
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "applicant": applicant,
        "documents": {
            "cv": _document_view(docs.get(row.cv_document_id)),
            "video": _document_view(docs.get(row.intro_video_document_id)),
        },
    }


def list_for_job(db: Session, user: User, job_id: str, limit: int, cursor: str | None) -> dict:
    job = own_job(db, user, job_id)
    query = select(Application).where(Application.job_id == job.id)
    if cursor:
        created_at, ident = jobs.decode_cursor(cursor)
        query = query.where(
            or_(
                Application.created_at < created_at,
                and_(Application.created_at == created_at, Application.id < ident),
            )
        )
    rows = list(db.scalars(
        query.order_by(Application.created_at.desc(), Application.id.desc()).limit(limit + 1)
    ))
    page = rows[:limit]
    next_cursor = jobs.encode_cursor(page[-1]) if len(rows) > limit else None
    people = _applicant_views(db, page)
    docs = _documents_of(db, page)
    return {
        "items": [_base_view(r, people.get(r.applicant_id), docs) for r in page],
        "next_cursor": next_cursor,
    }


def detail_view(db: Session, row: Application) -> dict:
    out = _base_view(
        row, _applicant_views(db, [row]).get(row.applicant_id), _documents_of(db, [row])
    )
    out["job"] = jobs.summaries(db, [db.get(Job, row.job_id)])[0]
    out["cover_note"] = row.cover_note
    out["identity"] = {"state": "available", "expires_at": None}
    out["history"] = applications.history_of(db, row.id)
    return out


def change_status(db: Session, user: User, app_id: str, status: str, note: str | None) -> Application:
    row = get_application(db, user, app_id)
    if status not in TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=409, detail="INVALID_TRANSITION")
    db.add(ApplicationStatusHistory(
        application_id=row.id,
        from_status=row.status,
        to_status=status,
        changed_by=user.id,
        note=note or None,
    ))
    row.status = status
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def _file_response(db: Session, doc: Document | None, filename: str) -> StreamingResponse:
    if doc is None:
        raise HTTPException(status_code=404, detail="DOCUMENT_NOT_FOUND")
    return StreamingResponse(
        documents.stream(db, doc.id),
        media_type=documents.MEDIA_TYPES.get(doc.ext, "application/octet-stream"),
        headers={"Content-Disposition": 'attachment; filename="%s.%s"' % (filename, doc.ext)},
    )


def cv_file(db: Session, row: Application) -> StreamingResponse:
    doc = db.get(Document, row.cv_document_id) if row.cv_document_id else None
    return _file_response(db, doc, "cv")


def video_file(db: Session, row: Application) -> StreamingResponse:
    doc = db.get(Document, row.intro_video_document_id) if row.intro_video_document_id else None
    return _file_response(db, doc, "intro_video")


def _ktp(db: Session, row: Application) -> Document | None:
    return db.scalar(
        select(Document)
        .where(Document.owner_id == row.applicant_id, Document.type == "ktp")
        .order_by(Document.created_at.desc())
    )


def identity_view(db: Session, row: Application) -> dict:
    ktp = _ktp(db, row)
    return {
        "nik": vault.load_field(db, row.applicant_id, "nik"),
        "address": vault.load_field(db, row.applicant_id, "address"),
        "birth_date": vault.load_field(db, row.applicant_id, "birth_date"),
        "ktp_available": ktp is not None,
    }


def ktp_file(db: Session, row: Application) -> StreamingResponse:
    ktp = _ktp(db, row)
    if ktp is None:
        raise HTTPException(status_code=404, detail="NO_KTP")
    return _file_response(db, ktp, "ktp")
