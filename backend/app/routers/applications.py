from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import applications, auditing, consent
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
    request: Request,
    job_id: str,
    body: ApplyIn,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    row = applications.apply(db, user, job_id, body)
    auditing.log(db, request, user, "application.apply", "application", row.id,
                    {"consents": len(body.consents), "video": int(body.intro_video_document_id is not None)})
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
    request: Request,
    app_id: str,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    row = applications.withdraw(db, user, app_id)
    auditing.log(db, request, user, "application.withdraw", "application", row.id)
    return applications.detail_view(db, row)


@router.patch("/me/applications/{app_id}/consents")
def patch_consents(
    request: Request,
    app_id: str,
    body: RevokeConsentsIn,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    row = applications.revoke_consents(db, user, app_id, body.revoke)
    auditing.log(db, request, user, "application.consent_revoke", "application", row.id,
                 {"scopes": sorted(set(body.revoke))})
    return applications.detail_view(db, row)