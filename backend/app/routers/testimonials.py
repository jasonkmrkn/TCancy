from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app import auditing, testimonials
from app.db import get_db
from app.deps import require_role
from app.models import User
from app.schemas import TestimonialIn, TestimonialStatusIn

router = APIRouter(prefix="/api/v1", tags=["testimonials"])

Applicant = require_role("applicant")
Admin = require_role("admin")


@router.get("/testimonials")
def list_public(
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    return testimonials.list_public(db, limit, cursor)


@router.post("/testimonials", status_code=201)
def create(
    request: Request, body: TestimonialIn, user: User = Depends(Applicant), db: Session = Depends(get_db)
):
    out = testimonials.create(db, user, body)
    auditing.log(db, request, user, "testimonial.create", "testimonial", out["id"])
    return out


@router.get("/me/testimonials")
def list_mine(user: User = Depends(Applicant), db: Session = Depends(get_db)):
    return testimonials.list_mine(db, user)


@router.delete("/testimonials/{testimonial_id}", status_code=204)
def delete(
    request: Request, testimonial_id: str, user: User = Depends(Applicant), db: Session = Depends(get_db)
):
    testimonials.delete(db, user, testimonial_id)
    auditing.log(db, request, user, "testimonial.delete", "testimonial", testimonial_id)
    return Response(status_code=204)


@router.get("/admin/testimonials")
def list_admin(
    status: Literal["pending", "approved", "hidden"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(Admin),
    db: Session = Depends(get_db),
):
    return testimonials.list_admin(db, status, limit, cursor)


@router.patch("/admin/testimonials/{testimonial_id}")
def moderate(
    request: Request,
    testimonial_id: str,
    body: TestimonialStatusIn,
    admin: User = Depends(Admin),
    db: Session = Depends(get_db),
):
    out = testimonials.moderate(db, admin, testimonial_id, body.status)
    auditing.log(db, request, admin, "admin.testimonial_moderate", "testimonial", testimonial_id,
                 {"status": body.status})
    return out
