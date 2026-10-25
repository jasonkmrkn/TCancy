import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import jobs
from app.models import Application, ApplicantSkill, Job, JobSkill, User

CANDIDATE_LIMIT = 500


def matches_for(db: Session, user: User, limit: int) -> list[dict]:
    """Open, unexpired, not-yet-applied jobs that share at least one skill with the applicant."""
    mine = set(db.scalars(select(ApplicantSkill.skill_id).where(ApplicantSkill.user_id == user.id)))
    if not mine:
        return []
    applied = select(Application.job_id).where(Application.applicant_id == user.id)
    candidates = list(db.scalars(
        select(Job)
        .where(
            Job.status == "open",
            or_(Job.deadline.is_(None), Job.deadline >= date.today()),
            Job.id.not_in(applied),
            Job.id.in_(select(JobSkill.job_id).where(JobSkill.skill_id.in_(mine))),
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(CANDIDATE_LIMIT)
    ))
    summaries = jobs.summaries(db, candidates)
    scored = []
    for summary in summaries:
        shared = [s for s in summary["skills"] if uuid.UUID(s["id"]) in mine]
        scored.append((len(shared), summary, shared))
    # candidates are already newest first; a stable sort keeps that order within a score
    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {"job": summary, "score": score, "matched_skills": shared}
        for score, summary, shared in scored[:limit]
    ]
