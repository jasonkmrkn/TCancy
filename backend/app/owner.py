import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import applications, config, consent, documents, jobs, policy, vault
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


def _visibility(db: Session, rows: list[Application], caller: User) -> dict[uuid.UUID, policy.Visibility]:
    """What the caller may see of each application, by application id."""
    scopes = consent.active_scopes(db, [r.id for r in rows])
    return {r.id: policy.decide(r.status, scopes[r.id], caller.role) for r in rows}


def _applicant_views(
    db: Session, rows: list[Application], seen: dict[uuid.UUID, policy.Visibility]
) -> dict[uuid.UUID, dict | None]:
    """Applicant objects by application id; None when the profile is not visible.

    The phone key is left out entirely unless the policy allows it.
    """
    out: dict[uuid.UUID, dict | None] = {r.id: None for r in rows}
    shown = [r for r in rows if seen[r.id].profile]
    if not shown:
        return out
    ids = list({r.applicant_id for r in shown})
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
    phone_ids = list({r.applicant_id for r in shown if seen[r.id].phone})
    phones = vault.load_fields(db, phone_ids, "phone") if phone_ids else {}
    profiles = {
        p.user_id: p
        for p in db.scalars(select(ApplicantProfile).where(ApplicantProfile.user_id.in_(ids)))
    }
    for r in shown:
        p = profiles.get(r.applicant_id)
        if p is None:
            continue
        view = {
            "full_name": names.get(r.applicant_id),
            "email": emails.get(r.applicant_id),
            "angkatan": p.angkatan,
            "skills": skills[r.applicant_id],
        }
        if seen[r.id].phone:
            view["phone"] = phones.get(r.applicant_id)
        out[r.id] = view
    return out


def _documents_of(db: Session, rows: list[Application]) -> dict[uuid.UUID, Document]:
    ids = {r.cv_document_id for r in rows if r.cv_document_id}
    ids |= {r.intro_video_document_id for r in rows if r.intro_video_document_id}
    if not ids:
        return {}
    return {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(ids)))}


def _base_view(
    row: Application,
    applicant: dict | None,
    docs: dict[uuid.UUID, Document],
    seen: policy.Visibility,
) -> dict:
    cv = docs.get(row.cv_document_id) if seen.cv else None
    video = docs.get(row.intro_video_document_id) if seen.video else None
    return {
        "id": str(row.id),
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "applicant": applicant,
        "documents": {"cv": _document_view(cv), "video": _document_view(video)},
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
    seen = _visibility(db, page, user)
    people = _applicant_views(db, page, seen)
    docs = _documents_of(db, page)
    return {
        "items": [_base_view(r, people[r.id], docs, seen[r.id]) for r in page],
        "next_cursor": next_cursor,
    }


def detail_view(db: Session, row: Application, user: User) -> dict:
    seen = _visibility(db, [row], user)
    out = _base_view(
        row,
        _applicant_views(db, [row], seen)[row.id],
        _documents_of(db, [row]),
        seen[row.id],
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
    now = datetime.now(timezone.utc)
    db.add(ApplicationStatusHistory(
        application_id=row.id,
        from_status=row.status,
        to_status=status,
        changed_by=user.id,
        note=note or None,
    ))
    row.status = status
    row.updated_at = now
    if status == "accepted" and row.accepted_at is None:
        # The identity window starts at the first acceptance and is never extended.
        row.accepted_at = now
        row.identity_access_expires_at = now + timedelta(days=config.IDENTITY_ACCESS_DAYS)
    db.commit()
    db.refresh(row)
    return row


def _file_response(db: Session, document_id, filename: str) -> StreamingResponse:
    meta = documents.get_meta(db, document_id) if document_id else None
    if meta is None:
        raise HTTPException(status_code=404, detail="DOCUMENT_NOT_FOUND")
    # documents.stream reads the first chunk itself, so a missing or unreadable file
    # raises its own HTTP error (404 or 500 STORAGE_ERROR) before the response starts.
    return StreamingResponse(
        documents.stream(db, meta.id),
        media_type=documents.MEDIA_TYPES.get(meta.ext, "application/octet-stream"),
        headers={
            "Content-Disposition": 'attachment; filename="%s.%s"' % (filename, meta.ext)
        },
    )


def _not_visible() -> HTTPException:
    return HTTPException(status_code=403, detail="NOT_VISIBLE")


def cv_file(db: Session, row: Application, user: User) -> StreamingResponse:
    if not _visibility(db, [row], user)[row.id].cv:
        raise _not_visible()
    return _file_response(db, row.cv_document_id, "cv")


def video_file(db: Session, row: Application, user: User) -> StreamingResponse:
    if not _visibility(db, [row], user)[row.id].video:
        raise _not_visible()
    return _file_response(db, row.intro_video_document_id, "intro_video")


def _ktp_id(db: Session, row: Application) -> str | None:
    """The applicant's newest ID card document, found through the documents interface."""
    cards = [d for d in documents.list_for_owner(db, row.applicant_id) if d["type"] == "ktp"]
    return cards[-1]["id"] if cards else None


def identity_view(db: Session, row: Application) -> dict:
    return {
        "nik": vault.load_field(db, row.applicant_id, "nik"),
        "address": vault.load_field(db, row.applicant_id, "address"),
        "birth_date": vault.load_field(db, row.applicant_id, "birth_date"),
        "ktp_available": _ktp_id(db, row) is not None,
    }


def ktp_file(db: Session, row: Application) -> StreamingResponse:
    ktp_id = _ktp_id(db, row)
    if ktp_id is None:
        raise HTTPException(status_code=404, detail="NO_KTP")
    return _file_response(db, ktp_id, "ktp")
