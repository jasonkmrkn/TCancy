import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import jobs, profiles
from app.models import Application, Job, Testimonial, User
from app.schemas import TestimonialIn


def _own_view(t: Testimonial) -> dict:
    return {
        "id": str(t.id),
        "application_id": str(t.application_id),
        "content": t.content,
        "show_name": t.show_name,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
    }


def _admin_view(t: Testimonial) -> dict:
    item = _own_view(t)
    item.update(
        author_id=str(t.author_id),
        display_first_name=t.display_first_name,
        display_company=t.display_company,
    )
    return item


def _find(db: Session, testimonial_id: str) -> Testimonial | None:
    try:
        ident = uuid.UUID(testimonial_id)
    except ValueError:
        return None
    return db.get(Testimonial, ident)


def create(db: Session, user: User, data: TestimonialIn) -> dict:
    app = db.scalar(
        select(Application).where(
            Application.id == data.application_id, Application.applicant_id == user.id
        )
    )
    if app is None:
        raise HTTPException(status_code=404, detail="APPLICATION_NOT_FOUND")
    if app.status != "accepted":
        raise HTTPException(status_code=409, detail="APPLICATION_NOT_ACCEPTED")
    exists = db.scalar(select(Testimonial.id).where(Testimonial.application_id == app.id))
    if exists is not None:
        raise HTTPException(status_code=409, detail="TESTIMONIAL_EXISTS")
    job = db.get(Job, app.job_id)
    full_name = (profiles.display_name(db, user.id) or "").strip()
    testimonial = Testimonial(
        application_id=app.id,
        author_id=user.id,
        content=data.content,
        show_name=data.show_name,
        display_first_name=full_name.split()[0] if full_name else None,
        display_company=job.company if job else None,
    )
    db.add(testimonial)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="TESTIMONIAL_EXISTS")
    db.refresh(testimonial)
    return _own_view(testimonial)


def list_mine(db: Session, user: User) -> dict:
    rows = db.scalars(
        select(Testimonial)
        .where(Testimonial.author_id == user.id)
        .order_by(Testimonial.created_at.desc(), Testimonial.id.desc())
    )
    return {"items": [_own_view(t) for t in rows]}


def delete(db: Session, user: User, testimonial_id: str) -> None:
    t = _find(db, testimonial_id)
    if t is None or t.author_id != user.id:
        raise HTTPException(status_code=404, detail="TESTIMONIAL_NOT_FOUND")
    db.delete(t)
    db.commit()


def _page(db: Session, status: str | None, limit: int, cursor: str | None):
    query = select(Testimonial)
    if status is not None:
        query = query.where(Testimonial.status == status)
    if cursor:
        created_at, ident = jobs.decode_cursor(cursor)
        query = query.where(
            (Testimonial.created_at < created_at)
            | ((Testimonial.created_at == created_at) & (Testimonial.id < ident))
        )
    rows = list(
        db.scalars(
            query.order_by(Testimonial.created_at.desc(), Testimonial.id.desc()).limit(limit + 1)
        )
    )
    page = rows[:limit]
    next_cursor = jobs.encode_cursor(page[-1]) if len(rows) > limit else None
    return page, next_cursor


def list_public(db: Session, limit: int, cursor: str | None) -> dict:
    page, next_cursor = _page(db, "approved", limit, cursor)
    items = []
    for t in page:
        author = None
        if t.show_name:
            author = {"first_name": t.display_first_name, "company": t.display_company}
        items.append(
            {
                "id": str(t.id),
                "content": t.content,
                "created_at": t.created_at.isoformat(),
                "author": author,
            }
        )
    return {"items": items, "next_cursor": next_cursor}


def list_admin(db: Session, status: str | None, limit: int, cursor: str | None) -> dict:
    page, next_cursor = _page(db, status, limit, cursor)
    return {"items": [_admin_view(t) for t in page], "next_cursor": next_cursor}


def moderate(db: Session, admin: User, testimonial_id: str, status: str) -> dict:
    t = _find(db, testimonial_id)
    if t is None:
        raise HTTPException(status_code=404, detail="TESTIMONIAL_NOT_FOUND")
    if t.status == status:
        raise HTTPException(status_code=409, detail="NO_CHANGE")
    t.status = status
    t.moderated_by = admin.id
    t.moderated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(t)
    return _admin_view(t)
