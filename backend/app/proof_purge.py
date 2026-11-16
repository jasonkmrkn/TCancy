"""Removal of verification proofs, packages and wrapped keys (owner: Raynald).

When a proof, a package or a wrapped K must go:
  - the admin approves or rejects             -> purge_for_alumni(db, alumni_id, "approved" | "rejected")
  - the request passes its 14 days            -> purge_expired(db)  (cron: python -m app.cli purge-expired-proofs)
  - the alumni uploads a new proof            -> end_grants_for_alumni(db, alumni_id)
  - the admin registers a new key (old revoked) -> end_grants_for_key(db, old_key_id)
  - an account is deleted                     -> keys_for_user(db, user_id), see app.account

proof_grants hangs off verification_requests, not off verification_proofs, so deleting a proof
does not cascade to its grants; these functions remove them explicitly.

Contract: every function except purge_expired only changes the caller's transaction. It does
not commit, and it returns the storage keys whose files must go. The caller commits first and
deletes the files after, so a rolled-back transaction never loses a file that a row still
points at:

    keys = proof_purge.purge_for_alumni(db, alumni.id, "approved")
    db.commit()
    proof_purge.delete_files(keys)

A file left behind by a crash between the commit and delete_files is an orphan nobody can
reach (no row points at it); it is never the other way round.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.models import ProofGrant, VerificationProof, VerificationProofCopy, VerificationRequest

log = logging.getLogger("tcancy.proof_purge")

OPEN = ("pending", "granted")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def delete_files(keys) -> None:
    """Remove stored files. Never raises: a missing file is nothing to do, an error is logged."""
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            log.warning("could not delete stored file of a purged proof")


def _drop_grants(db: Session, request_ids) -> list[str]:
    request_ids = list(request_ids)
    if not request_ids:
        return []
    grants = db.scalars(
        select(ProofGrant).where(ProofGrant.request_id.in_(request_ids)).with_for_update()
    ).all()
    keys = [g.pkg_storage_key for g in grants]
    for grant in grants:
        db.delete(grant)  
    db.flush()
    return keys


def _close(requests, status: str, reason: str, now: datetime) -> None:
    for req in requests:
        req.status = status
        req.closed_at = now
        req.close_reason = reason


def _drop_proof(db: Session, alumni_id: uuid.UUID) -> list[str]:
    proof = db.scalar(
        select(VerificationProof).where(VerificationProof.alumni_id == alumni_id).with_for_update()
    )
    if proof is None:
        return []
    copies = db.scalars(
        select(VerificationProofCopy).where(VerificationProofCopy.proof_id == proof.id)
    ).all()
    keys = [c.storage_key for c in copies]
    for copy in copies:
        db.delete(copy)
    db.flush()  
    db.delete(proof)
    db.flush()
    return keys


def keys_for_user(db: Session, user_id: uuid.UUID) -> list[str]:
    """Storage keys of every proof copy and package that goes when this user's account goes.

    The rows go by ON DELETE CASCADE with the user (as alumni or as admin); only the files need
    this. Changes nothing, so the caller deletes the user, commits, then calls delete_files().
    """
    copies = db.scalars(
        select(VerificationProofCopy.storage_key)
        .join(VerificationProof, VerificationProof.id == VerificationProofCopy.proof_id)
        .where(VerificationProof.alumni_id == user_id)
    ).all()
    packages = db.scalars(
        select(ProofGrant.pkg_storage_key)
        .join(VerificationRequest, VerificationRequest.id == ProofGrant.request_id)
        .where((VerificationRequest.alumni_id == user_id) | (VerificationRequest.admin_id == user_id))
    ).all()
    return list(copies) + list(packages)


def end_grants_for_key(db: Session, key_id: uuid.UUID, reason: str = "key_revoked") -> list[str]:
    """Close every granted request whose grant is wrapped for `key_id`; drop those grants."""
    requests = db.scalars(
        select(VerificationRequest)
        .join(ProofGrant, ProofGrant.request_id == VerificationRequest.id)
        .where(ProofGrant.recipient_key_id == key_id)
        .with_for_update(of=VerificationRequest)
    ).all()
    keys = _drop_grants(db, [r.id for r in requests])
    _close([r for r in requests if r.status in OPEN], "closed", reason, _now())
    db.flush()
    return keys


def end_grants_for_alumni(db: Session, alumni_id: uuid.UUID, reason: str = "proof_replaced") -> list[str]:
    """Close the alumni's granted requests (their package holds the old proof); pending ones stay."""
    requests = db.scalars(
        select(VerificationRequest)
        .where(VerificationRequest.alumni_id == alumni_id, VerificationRequest.status == "granted")
        .with_for_update()
    ).all()
    keys = _drop_grants(db, [r.id for r in requests])
    _close(requests, "closed", reason, _now())
    db.flush()
    return keys


def purge_for_alumni(db: Session, alumni_id: uuid.UUID, reason: str) -> list[str]:
    """After a decision: the proof, every copy, every grant and package go; open requests close."""
    requests = db.scalars(
        select(VerificationRequest).where(VerificationRequest.alumni_id == alumni_id).with_for_update()
    ).all()
    keys = _drop_grants(db, [r.id for r in requests])
    _close([r for r in requests if r.status in OPEN], "closed", reason, _now())
    keys += _drop_proof(db, alumni_id)
    db.flush()
    return keys


def purge_expired(db: Session, now: datetime | None = None) -> int:
    """Expire open requests whose expires_at has passed. Commits and deletes the files itself.

    Their grants and packages go. The alumni's proof goes too, unless the alumni still has
    another open request that needs it. Returns the number of requests that expired.
    """
    now = now or _now()
    expired = db.scalars(
        select(VerificationRequest)
        .where(VerificationRequest.status.in_(OPEN), VerificationRequest.expires_at <= now)
        .with_for_update(skip_locked=True)  
    ).all()
    if not expired:
        db.rollback()
        return 0
    keys = _drop_grants(db, [r.id for r in expired])
    _close(expired, "expired", "expired", now)
    db.flush()
    for alumni_id in {r.alumni_id for r in expired}:
        still_open = db.scalar(
            select(VerificationRequest.id).where(
                VerificationRequest.alumni_id == alumni_id, VerificationRequest.status.in_(OPEN)
            ).limit(1)
        )
        if still_open is None:
            keys += _drop_proof(db, alumni_id)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    delete_files(keys)
    return len(expired)
