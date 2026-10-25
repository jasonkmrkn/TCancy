from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import applications, matching
from app.models import Application, Document, Job, User

APPLICATION_STATUSES = ("submitted", "shortlisted", "accepted", "rejected", "withdrawn")
DOCUMENT_TYPES = ("cv", "ktp", "intro_video")
NEW_APPLICATION_DAYS = 7


def _counts(rows, keys) -> dict[str, int]:
    out = {k: 0 for k in keys}
    for key, n in rows:
        if key in out:
            out[key] = n
    return out


def applicant_dashboard(db: Session, user: User) -> dict:
    statuses = db.execute(
        select(Application.status, func.count())
        .where(Application.applicant_id == user.id)
        .group_by(Application.status)
    ).all()
    docs = db.execute(
        select(Document.type, func.count()).where(Document.owner_id == user.id).group_by(Document.type)
    ).all()
    recent = list(db.scalars(
        select(Application)
        .where(Application.applicant_id == user.id)
        .order_by(Application.created_at.desc(), Application.id.desc())
        .limit(5)
    ))
    return {
        "applications": _counts(statuses, APPLICATION_STATUSES),
        "documents": _counts(docs, DOCUMENT_TYPES),
        "recent_applications": applications.summary_views(db, recent),
        "matches": matching.matches_for(db, user, 3),
    }


def owner_dashboard(db: Session, user: User) -> dict:
    job_rows = db.execute(
        select(Job.status, func.count()).where(Job.owner_id == user.id).group_by(Job.status)
    ).all()
    owned = select(Job.id).where(Job.owner_id == user.id)
    statuses = db.execute(
        select(Application.status, func.count())
        .where(Application.job_id.in_(owned))
        .group_by(Application.status)
    ).all()
    since = datetime.now(timezone.utc) - timedelta(days=NEW_APPLICATION_DAYS)
    new = db.scalar(
        select(func.count()).where(
            Application.job_id.in_(owned),
            Application.status == "submitted",
            Application.created_at >= since,
        )
    )
    return {
        "jobs": _counts(job_rows, ("open", "closed")),
        "applications": _counts(statuses, APPLICATION_STATUSES),
        "new_applications": new or 0,
    }
