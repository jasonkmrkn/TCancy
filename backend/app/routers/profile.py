from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import profiles
from app.db import get_db
from app.deps import require_role
from app.models import Skill, User
from app.schemas import AlumniProfileIn, ApplicantProfileIn

router = APIRouter(prefix="/api/v1", tags=["profile"])


def _parse(model, body: dict):
    """Validate by role inside the handler; report errors in the usual 422 shape."""
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        errors = [
            {"loc": ("body", *e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        raise RequestValidationError(errors)


@router.get("/skills")
def list_skills(db: Session = Depends(get_db)):
    rows = db.execute(select(Skill.id, Skill.name).order_by(Skill.name)).all()
    return [{"id": str(i), "name": n} for i, n in rows]


@router.get("/me/profile")
def get_profile(
    user: User = Depends(require_role("applicant", "alumni", allow_pending=True)),
    db: Session = Depends(get_db),
):
    out = profiles.read(db, user)
    db.commit()  # reading an alumni profile may create its row
    return out


@router.put("/me/profile")
def put_profile(
    body: dict = Body(...),
    user: User = Depends(require_role("applicant", "alumni", allow_pending=True)),
    db: Session = Depends(get_db),
):
    if user.role == "alumni":
        data = _parse(AlumniProfileIn, body)
    else:
        if user.status != "active":
            raise HTTPException(status_code=403, detail="ACCOUNT_PENDING")
        data = _parse(ApplicantProfileIn, body)
    try:
        out = profiles.update(db, user, data)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        code = profiles.conflict_code(exc)
        if code is None:
            raise
        raise HTTPException(status_code=409, detail=code) from None
    except Exception:
        db.rollback()
        raise
    return out
