from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import applications, config, consent, matching, policy
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


def _open_windows(db: Session, *conditions) -> list[tuple[Application, Job]]:
    """Applications matching `conditions` whose identity window is open now, soonest first.

    The accepted and has-a-window filters only narrow the query. The rule itself is
    policy.identity_window_open, fed with the active consents of all rows in one query.
    """
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.status == "accepted",
            Application.identity_access_expires_at.is_not(None),
            *conditions,
        )
        .order_by(Application.identity_access_expires_at, Application.id)
    ).all()
    scopes = consent.active_scopes(db, [a.id for a, _ in rows])
    return [
        (a, job)
        for a, job in rows
        if policy.identity_window_open(a.status, scopes[a.id], a.identity_access_expires_at, now)
    ]


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
    windows = [
        {
            "application_id": str(a.id),
            "job_title": job.title,
            "expires_at": a.identity_access_expires_at.isoformat(),
        }
        for a, job in _open_windows(db, Application.applicant_id == user.id)
    ]
    return {
        "applications": _counts(statuses, APPLICATION_STATUSES),
        "documents": _counts(docs, DOCUMENT_TYPES),
        "recent_applications": applications.summary_views(db, recent),
        "matches": matching.matches_for(db, user, 3),
        "identity_windows": windows,
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
    soon = datetime.now(timezone.utc) + timedelta(days=config.ACCESS_REMINDER_DAYS)
    ending = [
        {
            "application_id": str(a.id),
            "job_id": str(job.id),
            "job_title": job.title,
            "expires_at": a.identity_access_expires_at.isoformat(),
        }
        for a, job in _open_windows(
            db, Job.owner_id == user.id, Application.identity_access_expires_at <= soon
        )
    ]
    return {
        "jobs": _counts(job_rows, ("open", "closed")),
        "applications": _counts(statuses, APPLICATION_STATUSES),
        "new_applications": new or 0,
        "identity_windows_ending_soon": ending,
    }