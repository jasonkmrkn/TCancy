import base64
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Job, JobSkill, Skill, User
from app.profiles import check_skills
from app.schemas import JobIn


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="JOB_NOT_FOUND")


def encode_cursor(job: Job) -> str:
    raw = "%s|%s" % (job.created_at.isoformat(), job.id)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        stamp, ident = raw.split("|")
        created_at = datetime.fromisoformat(stamp)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at, uuid.UUID(ident)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid cursor")


def _skills_by_job(db: Session, job_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    out: dict[uuid.UUID, list[dict]] = {j: [] for j in job_ids}
    if not job_ids:
        return out
    rows = db.execute(
        select(JobSkill.job_id, Skill.id, Skill.name)
        .join(Skill, Skill.id == JobSkill.skill_id)
        .where(JobSkill.job_id.in_(job_ids))
        .order_by(Skill.name)
    ).all()
    for job_id, sid, name in rows:
        out[job_id].append({"id": str(sid), "name": name})
    return out


def summaries(db: Session, jobs: list[Job]) -> list[dict]:
    skills = _skills_by_job(db, [j.id for j in jobs])
    return [
        {
            "id": str(j.id),
            "title": j.title,
            "company": j.company,
            "type": j.type,
            "work_mode": j.work_mode,
            "location": j.location,
            "deadline": j.deadline.isoformat() if j.deadline else None,
            "status": j.status,
            "skills": skills[j.id],
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs
    ]


def detail(db: Session, job: Job) -> dict:
    out = summaries(db, [job])[0]
    out["description"] = job.description
    out["requirements"] = job.requirements
    return out


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + escaped + "%"


def search(
    db: Session,
    *,
    type: str | None,
    work_mode: str | None,
    q: str | None,
    location: str | None,
    skill: list[uuid.UUID],
    limit: int,
    cursor: str | None,
) -> dict:
    query = select(Job)
    if type:
        query = query.where(Job.type == type)
    if work_mode:
        query = query.where(Job.work_mode == work_mode)
    if q:
        pattern = _like(q)
        query = query.where(
            or_(
                Job.title.ilike(pattern, escape="\\"),
                Job.company.ilike(pattern, escape="\\"),
                Job.description.ilike(pattern, escape="\\"),
            )
        )
    if location:
        query = query.where(Job.location.ilike(_like(location), escape="\\"))
    if skill:
        query = query.where(
            Job.id.in_(select(JobSkill.job_id).where(JobSkill.skill_id.in_(skill)))
        )
    if cursor:
        created_at, ident = decode_cursor(cursor)
        query = query.where(
            or_(Job.created_at < created_at, and_(Job.created_at == created_at, Job.id < ident))
        )
    rows = list(
        db.scalars(query.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1))
    )
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1]) if len(rows) > limit else None
    return {"items": summaries(db, page), "next_cursor": next_cursor}


def get(db: Session, job_id: str) -> Job:
    try:
        ident = uuid.UUID(job_id)
    except ValueError:
        raise _not_found()
    job = db.get(Job, ident)
    if job is None:
        raise _not_found()
    return job


def _set_skills(db: Session, job: Job, skill_ids: list[uuid.UUID]) -> None:
    wanted = set(skill_ids)
    have = set()
    for row in db.scalars(select(JobSkill).where(JobSkill.job_id == job.id)):
        if row.skill_id in wanted:
            have.add(row.skill_id)
        else:
            db.delete(row)
    db.add_all([JobSkill(job_id=job.id, skill_id=s) for s in wanted - have])


def _apply(job: Job, data: JobIn) -> None:
    job.title = data.title
    job.company = data.company
    job.type = data.type
    job.work_mode = data.work_mode
    job.location = data.location
    job.description = data.description
    job.requirements = data.requirements
    job.deadline = data.deadline


def _check_deadline(deadline: date | None, unchanged: date | None = None) -> None:
    if deadline is None or deadline == unchanged:
        return
    if deadline < date.today():
        raise HTTPException(status_code=422, detail="deadline must not be in the past")


def create(db: Session, user: User, data: JobIn) -> Job:
    _check_deadline(data.deadline)
    check_skills(db, data.skill_ids)
    job = Job(owner_id=user.id)
    _apply(job, data)
    db.add(job)
    db.flush()
    _set_skills(db, job, data.skill_ids)
    db.commit()
    db.refresh(job)
    return job


def update(db: Session, user: User, job_id: str, data: JobIn) -> Job:
    job = get(db, job_id)
    if job.owner_id != user.id:
        raise HTTPException(status_code=403, detail="NOT_JOB_OWNER")
    if job.status == "closed":
        raise HTTPException(status_code=409, detail="JOB_CLOSED")
    _check_deadline(data.deadline, job.deadline)
    check_skills(db, data.skill_ids)
    _apply(job, data)
    _set_skills(db, job, data.skill_ids)
    db.commit()
    db.refresh(job)
    return job


def close(db: Session, user: User, job_id: str) -> Job:
    job = get(db, job_id)
    if user.role != "admin" and job.owner_id != user.id:
        raise HTTPException(status_code=403, detail="NOT_JOB_OWNER")
    if job.status == "closed":
        raise HTTPException(status_code=409, detail="JOB_CLOSED")
    job.status = "closed"
    job.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def owned_by(db: Session, user: User) -> list[Job]:
    return list(
        db.scalars(
            select(Job)
            .where(Job.owner_id == user.id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(200)
        )
    )
