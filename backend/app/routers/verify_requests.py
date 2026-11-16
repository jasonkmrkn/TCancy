import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.admin import _alumni_or_404
from app.db import get_db
from app.deps import require_role
from app.models import User, UserPublicKey, VerificationProof, VerificationRequest

router = APIRouter(prefix="/api/v1", tags=["verify-requests"])
ADMIN = require_role("admin")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_key(db: Session, admin_id: uuid.UUID) -> UserPublicKey | None:
    """The admin's usable key: not revoked and not expired. An expired key counts as no key."""
    return db.scalar(
        select(UserPublicKey).where(
            UserPublicKey.user_id == admin_id,
            UserPublicKey.revoked_at.is_(None),
            UserPublicKey.expires_at > _now(),
        )
    )


def _request_view(req: VerificationRequest) -> dict:
    return {
        "id": str(req.id),
        "alumni_id": str(req.alumni_id),
        "status": req.status,
        "created_at": req.created_at.isoformat(),
        "expires_at": req.expires_at.isoformat(),
    }


@router.post("/admin/alumni/{alumni_id}/proof-request", status_code=201)
def create_proof_request(
    alumni_id: str, user: User = Depends(ADMIN), db: Session = Depends(get_db)
):
    alumni = _alumni_or_404(db, alumni_id)
    if alumni.status != "pending":
        raise HTTPException(status_code=409, detail="NOT_PENDING")
    if _active_key(db, user.id) is None:
        raise HTTPException(status_code=409, detail="NO_PUBLIC_KEY")
    has_proof = db.scalar(
        select(VerificationProof.id).where(VerificationProof.alumni_id == alumni.id)
    )
    if has_proof is None:
        raise HTTPException(status_code=409, detail="NO_PROOF")

    req = VerificationRequest(
        alumni_id=alumni.id,
        admin_id=user.id,
        expires_at=_now() + timedelta(days=config.PROOF_REQUEST_TTL_DAYS),
    )
    db.add(req)
    try:
        db.commit()
    except (
        IntegrityError
    ):  # uq_verification_requests_open: this admin already has an open request
        db.rollback()
        raise HTTPException(status_code=409, detail="REQUEST_EXISTS")
    db.refresh(req)
    return _request_view(req)
