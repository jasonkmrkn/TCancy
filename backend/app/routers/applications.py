from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import applications, consent
from app.db import get_db
from app.deps import require_role
from app.models import User
from app.schemas import ApplyIn, RevokeConsentsIn

router = APIRouter(prefix="/api/v1", tags=["applications"])

@router.get("/consent-texts")
def consent_texts():
    return consent.texts_view()


@router.post("/jobs/{job_id}/apply", status_code=201)
def apply(
    job_id: str,
    body: ApplyIn,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    row = applications.apply(db, user, job_id, body)
    return applications.detail_view(db, row)


@router.get("/me/applications")
def list_applications(
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    return applications.summary_views(db, applications.list_for(db, user))


@router.get("/me/applications/{app_id}")
def get_application(
    app_id: str,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    return applications.detail_view(db, applications.get_owned(db, user, app_id))


@router.delete("/me/applications/{app_id}")
def withdraw_application(
    app_id: str,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    row = applications.withdraw(db, user, app_id)
    return applications.detail_view(db, row)


@router.patch("/me/applications/{app_id}/consents")
def patch_consents(
    app_id: str,
    body: RevokeConsentsIn,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    row = applications.revoke_consents(db, user, app_id, body.revoke)
    return applications.detail_view(db, row)