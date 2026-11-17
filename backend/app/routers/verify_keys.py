"""Admin public keys for alumni verification (owner: Axel).

  POST /admin/keys   register the admin's RSA-3072 public key: {"spki": "<base64 of SPKI DER>"},
                     as WebCrypto exportKey("spki") gives it
  GET  /admin/keys   the admin's current key: fingerprint and expires_at

The private key never leaves the admin's browser; the server only stores the public key.
One active key per admin: a new key revokes the old one and ends the grants wrapped for it
(proof_purge.end_grants_for_key). An expired key counts as no key. Keys expire after
config.ADMIN_KEY_TTL_DAYS days.
"""
import base64
import binascii
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, config, proof_purge, verify_crypto
from app.db import get_db
from app.deps import require_role
from app.models import User, UserPublicKey

router = APIRouter(prefix="/api/v1", tags=["verify-keys"])
ADMIN = require_role("admin")
ALGORITHM = "RSA-OAEP-3072-SHA256"


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spki: str = Field(max_length=4096)


def _view(key: UserPublicKey) -> dict:
    return {
        "id": str(key.id), "algorithm": key.algorithm, "fingerprint": key.fingerprint,
        "created_at": key.created_at, "expires_at": key.expires_at,
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/admin/keys", status_code=201)
def register_key(
    request: Request, body: KeyIn, user: User = Depends(ADMIN), db: Session = Depends(get_db)
):
    try:
        spki = base64.b64decode(body.spki, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="INVALID_PUBLIC_KEY")
    fingerprint = verify_crypto.check_public_key(spki)
    now = _now()
    package_keys = []
    try:
        # Expired ones too: the unique index allows one unrevoked key per user.
        old = db.scalars(select(UserPublicKey).where(
            UserPublicKey.user_id == user.id, UserPublicKey.revoked_at.is_(None),
        ).with_for_update()).all()
        for key in old:
            key.revoked_at = now
            ended = proof_purge.end_grants_for_key(db, key.id)
            package_keys += ended
            audit.record(
                db, actor_id=user.id, actor_role=user.role, action="verify.key.revoke",
                target_type="public_key", target_id=key.id,
                details=audit.details(fingerprint=key.fingerprint, grants_ended=len(ended)),
                **audit.client(request),
            )
        db.flush()  # the revoke before the insert, for the unique index
        new = UserPublicKey(
            id=uuid.uuid4(),
            user_id=user.id, algorithm=ALGORITHM, public_key_spki=spki, fingerprint=fingerprint,
            expires_at=now + timedelta(days=config.ADMIN_KEY_TTL_DAYS),
        )
        db.add(new)
        audit.record(
            db, actor_id=user.id, actor_role=user.role, action="verify.key.register",
            target_type="public_key", target_id=new.id,
            details=audit.details(fingerprint=fingerprint, valid_days=config.ADMIN_KEY_TTL_DAYS),
            **audit.client(request),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    proof_purge.delete_files(package_keys)  # only after the commit
    db.refresh(new)
    return _view(new)


@router.get("/admin/keys")
def current_key(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    key = db.scalar(select(UserPublicKey).where(
        UserPublicKey.user_id == user.id, UserPublicKey.revoked_at.is_(None),
        UserPublicKey.expires_at > _now(),
    ))
    if key is None:
        raise HTTPException(status_code=404, detail="KEY_NOT_FOUND")
    return _view(key)
