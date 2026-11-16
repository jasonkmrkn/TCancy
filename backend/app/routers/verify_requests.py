import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, storage, verify_crypto
from app.admin import _alumni_or_404
from app.db import get_db
from app.deps import require_role
from app.models import (
    ProofGrant,
    User,
    UserPublicKey,
    VerificationProof,
    VerificationRequest,
)
from app.routers.verify_proof import open_proof

router = APIRouter(prefix="/api/v1", tags=["verify-requests"])
ADMIN = require_role("admin")
ALUMNI = require_role("alumni", allow_pending=True)
OPEN = ("pending", "granted")


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
    except IntegrityError:
        # uq_verification_requests_open: this admin already has an open request
        db.rollback()
        raise HTTPException(status_code=409, detail="REQUEST_EXISTS")
    db.refresh(req)
    return _request_view(req)


def _shown_key(db: Session, req: VerificationRequest) -> UserPublicKey | None:
    """The key the alumni should check: the one a grant was wrapped for, else the admin's active key."""
    if req.status == "granted":
        grant = db.scalar(select(ProofGrant).where(ProofGrant.request_id == req.id))
        if grant is not None:
            return db.get(UserPublicKey, grant.recipient_key_id)
    return _active_key(db, req.admin_id)


@router.get("/me/verification-requests")
def my_verification_requests(
    user: User = Depends(ALUMNI), db: Session = Depends(get_db)
):
    rows = db.execute(
        select(VerificationRequest, User.username)
        .join(User, User.id == VerificationRequest.admin_id)
        .where(
            VerificationRequest.alumni_id == user.id,
            VerificationRequest.status.in_(OPEN),
            # past 14 days counts as gone, even before the cron runs
            VerificationRequest.expires_at > _now(),
        )
        .order_by(VerificationRequest.created_at.desc())
    ).all()
    out = []
    for req, admin_username in rows:
        key = _shown_key(db, req)
        out.append(
            {
                "id": str(req.id),
                "status": req.status,
                "admin_username": admin_username,
                "admin_fingerprint": key.fingerprint if key else None,
                "created_at": req.created_at.isoformat(),
                "expires_at": req.expires_at.isoformat(),
            }
        )
    return out


def _own_request(db: Session, user: User, request_id: str) -> VerificationRequest:
    """The alumni's own request, locked for this transaction. Someone else's request is 404 too."""
    try:
        ident = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="REQUEST_NOT_FOUND")
    req = db.scalar(
        select(VerificationRequest)
        .where(
            VerificationRequest.id == ident,
            VerificationRequest.alumni_id == user.id,
        )
        .with_for_update()
    )
    if req is None:
        raise HTTPException(status_code=404, detail="REQUEST_NOT_FOUND")
    return req


class _Counted:
    """Passes the package chunks through to storage and adds up their size on the way."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.size = 0

    def __iter__(self):
        for chunk in self.chunks:
            self.size += len(chunk)
            yield chunk


@router.post("/me/verification-requests/{request_id}/grant", status_code=201)
def grant_request(
    request_id: str, user: User = Depends(ALUMNI), db: Session = Depends(get_db)
):
    req = _own_request(db, user, request_id)
    if req.status != "pending" or req.expires_at <= _now():
        raise HTTPException(status_code=409, detail="REQUEST_ENDED")
    key = _active_key(db, req.admin_id)
    if key is None:
        raise HTTPException(status_code=409, detail="NO_PUBLIC_KEY")
    if (
        db.scalar(
            select(VerificationProof.id).where(VerificationProof.alumni_id == user.id)
        )
        is None
    ):
        raise HTTPException(status_code=409, detail="NO_PROOF")

    _, plaintext = open_proof(db, user.id)  # checks the stored sha256 first
    grant_id = (
        uuid.uuid4()
    )  # chosen here: the package AAD and the KEK context both need it
    k = verify_crypto.new_share_key()
    pkg_nonce, sealed = verify_crypto.encrypt_package(
        plaintext,
        k,
        grant_id,
        chunk_size=config.PROOF_CHUNK_SIZE,
    )
    package = _Counted(sealed)
    try:
        pkg_key = storage.write(package)
    except storage.StorageError:
        db.rollback()
        raise HTTPException(status_code=500, detail="STORAGE_ERROR")

    try:
        access_code = verify_crypto.wrap_for_recipient(key.public_key_spki, k)
        db.add(
            ProofGrant(
                id=grant_id,
                request_id=req.id,
                recipient_key_id=key.id,
                pkg_nonce=pkg_nonce,
                pkg_storage_key=pkg_key,
                pkg_size=package.size,
                **verify_crypto.wrap_kek(k, grant_id=grant_id, recipient_key_id=key.id),
            )
        )
        req.status = "granted"
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(
            pkg_key
        )  # no row points at the package, so it must not stay on disk
        raise

    return {
        "request_id": str(req.id),
        "grant_id": str(grant_id),
        "access_code": access_code,
        "admin_fingerprint": key.fingerprint,
    }


def _admin_grant(
    db: Session, user: User, request_id: str
) -> tuple[VerificationRequest, ProofGrant]:
    """The admin's own granted request and its grant.

    {id} in /admin/proof-grants/{id} is the request id: the admin already has it from
    proof-request, and the request row outlives the grant (purge deletes the grant).
    404 GRANT_NOT_FOUND: unknown, another admin's, or not granted yet.
    410 GRANT_ENDED: closed, expired, or its KEK version was removed from the environment.
    """
    try:
        ident = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="GRANT_NOT_FOUND")
    req = db.scalar(
        select(VerificationRequest).where(
            VerificationRequest.id == ident,
            VerificationRequest.admin_id == user.id,
        )
    )
    if req is None or req.status == "pending":
        raise HTTPException(status_code=404, detail="GRANT_NOT_FOUND")
    grant = db.scalar(select(ProofGrant).where(ProofGrant.request_id == req.id))
    if req.status != "granted" or req.expires_at <= _now() or grant is None:
        raise HTTPException(status_code=410, detail="GRANT_ENDED")
    if grant.kek_version not in config.PROOF_KEKS:
        raise HTTPException(status_code=410, detail="GRANT_ENDED")
    return req, grant


@router.get("/admin/proof-grants/{request_id}")
def grant_metadata(
    request_id: str, user: User = Depends(ADMIN), db: Session = Depends(get_db)
):
    req, grant = _admin_grant(db, user, request_id)
    proof = db.scalar(
        select(VerificationProof).where(VerificationProof.alumni_id == req.alumni_id)
    )
    if (
        proof is None
    ):  # cannot happen while the grant exists (purge removes both), but never 500
        raise HTTPException(status_code=410, detail="GRANT_ENDED")
    key = db.get(UserPublicKey, grant.recipient_key_id)
    return {
        "request_id": str(req.id),
        "grant_id": str(grant.id),
        "ext": proof.ext,
        "size": proof.size,
        "pkg_size": grant.pkg_size,
        "pkg_nonce": grant.pkg_nonce.hex(),
        "chunk_size": config.PROOF_CHUNK_SIZE,
        "recipient_fingerprint": key.fingerprint,
        "expires_at": req.expires_at.isoformat(),
        "opened_at": grant.opened_at.isoformat() if grant.opened_at else None,
    }
