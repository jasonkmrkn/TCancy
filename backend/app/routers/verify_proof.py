"""Alumni verification proof upload (owner: Axel).

  POST   /me/verification-proof   upload the proof (PDF/JPG/PNG, at most config.PROOF_MAX_BYTES)
  GET    /me/verification-proof   metadata of the stored proof
  DELETE /me/verification-proof   delete the stored proof

Stored like A1 documents: chunks of crypto.CHUNK_SIZE under keys from HKDF over MASTER_KEY
(item "proof:<proof_id>", salt and nonce per copy); three copies (aes, des, rc4) under
ENCRYPTION_POLICY=assignment, aes only under production. The des and rc4 copies are made by
reading the aes copy back, so the upload is read once. There is no tag table for proofs:
open_proof() checks the decrypted aes copy against VerificationProof.sha256 instead.

File type checks and upload parsing come from app.upload, storage from app.storage (Raynald).
The body limit for the upload is set in app.main. Approve and reject stay in routers/admin.py.
"""
import hashlib
import itertools
import uuid
from collections.abc import Iterator

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, crypto, documents, proof_purge, storage
from app.db import get_db
from app.deps import require_role
from app.models import User, VerificationProof, VerificationProofCopy
from app.upload import MultipartUpload, checked_upload

router = APIRouter(prefix="/api/v1", tags=["verify-proof"])
ALUMNI = require_role("alumni", allow_pending=True)

# One chunk size for the cipher calls and the chunk_size column. crypto.CHUNK_SIZE is what the
# CTR counter offsets assume, so config.PROOF_CHUNK_SIZE must agree with it.
CHUNK_SIZE = crypto.CHUNK_SIZE
if config.PROOF_CHUNK_SIZE != CHUNK_SIZE:
    raise RuntimeError("PROOF_CHUNK_SIZE must equal crypto.CHUNK_SIZE")


def _close_grants(db: Session, alumni_id: uuid.UUID, reason: str) -> list[str]:
    """Close the alumni's grants (Raynald, V6). Does not commit; returns the package storage keys
    to delete after the commit. ponytail: placeholder name until agreed with Raynald."""
    return proof_purge.close_grants_for_alumni(db, alumni_id, reason) or []


def _view(p: VerificationProof) -> dict:
    return {"ext": p.ext, "size": p.size, "sha256": p.sha256, "created_at": p.created_at}


def _item(proof_id: uuid.UUID) -> str:
    return "proof:%s" % proof_id


def _encrypt(chunks, alg: str, salt: bytes, nonce: bytes | None, item: str):
    for index, chunk in enumerate(chunks):
        yield documents._ENCRYPT[alg](chunk, salt, nonce, item, index)


def _get(db: Session, alumni_id: uuid.UUID) -> VerificationProof:
    proof = db.scalar(select(VerificationProof).where(VerificationProof.alumni_id == alumni_id))
    if proof is None:
        raise HTTPException(status_code=404, detail="PROOF_NOT_FOUND")
    return proof


def _copy_keys(db: Session, proof_id: uuid.UUID) -> list[str]:
    return list(db.scalars(select(VerificationProofCopy.storage_key).where(VerificationProofCopy.proof_id == proof_id)))


def _store(db: Session, user: User, upload: MultipartUpload) -> dict:
    checked = checked_upload(upload, "verification_proof", config.PROOF_MAX_BYTES)
    digest = hashlib.sha256()

    def plain():  # plaintext, read once, hashed on the way
        for piece in checked:
            digest.update(piece)
            yield piece

    proof_id = uuid.uuid4()
    item = _item(proof_id)
    new_keys = []
    try:
        copies = []
        for alg in documents._algorithms():
            salt, nonce = crypto.new_params(alg, item)
            if not copies:
                source = documents._rechunk(plain())
            else:
                aes = copies[0]
                source = documents._decrypt(storage.read(aes.storage_key), "aes", aes.salt, aes.nonce, item)
            key = storage.write(_encrypt(source, alg, salt, nonce, item))
            new_keys.append(key)
            copies.append(VerificationProofCopy(
                proof_id=proof_id, algorithm=alg, salt=salt, nonce=nonce,
                storage_key=key, chunk_size=CHUNK_SIZE, ciphertext_size=checked.size,
            ))

        old = db.scalar(select(VerificationProof).where(VerificationProof.alumni_id == user.id))
        old_keys = []
        if old is not None:
            old_keys = _copy_keys(db, old.id) + _close_grants(db, user.id, "proof_replaced")
            db.delete(old)  # the copies go with it (ON DELETE CASCADE)
            db.flush()  # before the insert: alumni_id is unique
        proof = VerificationProof(id=proof_id, alumni_id=user.id, ext=checked.ext,
                                  size=checked.size, sha256=digest.hexdigest())
        db.add(proof)
        db.flush()  # the proof row before its copies (foreign key)
        db.add_all(copies)
        db.commit()
    except Exception as e:
        db.rollback()
        for key in new_keys:  # new files go when anything fails
            storage.delete(key)
        if isinstance(e, storage.StorageError):
            raise HTTPException(status_code=500, detail="STORAGE_ERROR") from e
        raise
    for key in old_keys:  # old files only after the commit
        storage.delete(key)
    db.refresh(proof)
    return _view(proof)


def _delete(db: Session, user: User) -> None:
    proof = _get(db, user.id)
    keys = _copy_keys(db, proof.id) + _close_grants(db, user.id, "proof_deleted")
    db.delete(proof)
    db.commit()
    for key in keys:
        storage.delete(key)


def _aes_plain(copy: VerificationProofCopy, item: str):
    return documents._decrypt(storage.read(copy.storage_key), "aes", copy.salt, copy.nonce, item)


def open_proof(db: Session, alumni_id: uuid.UUID) -> tuple[VerificationProof, Iterator[bytes]]:
    """The alumni's proof row and an iterator of its plaintext, in chunks of CHUNK_SIZE.

    For V4: the iterator goes straight into verify_crypto.encrypt_package. The aes copy is read
    once to compare its sha256 with the stored one before anything is returned: 404
    PROOF_NOT_FOUND, 500 STORAGE_ERROR, 500 INTEGRITY_ERROR. The iterator holds only plain
    values, so it keeps working after the session is closed. Does not commit.
    """
    proof = _get(db, alumni_id)
    copy = db.scalar(select(VerificationProofCopy).where(
        VerificationProofCopy.proof_id == proof.id, VerificationProofCopy.algorithm == "aes",
    ))
    if copy is None:
        raise HTTPException(status_code=404, detail="PROOF_NOT_FOUND")
    item = _item(proof.id)
    digest = hashlib.sha256()
    try:
        for chunk in _aes_plain(copy, item):
            digest.update(chunk)
        pieces = _aes_plain(copy, item)
        first = next(pieces, b"")
    except storage.StorageError:
        raise HTTPException(status_code=500, detail="STORAGE_ERROR")
    if digest.hexdigest() != proof.sha256:
        raise HTTPException(status_code=500, detail="INTEGRITY_ERROR")
    return proof, itertools.chain([first], pieces)


@router.post("/me/verification-proof", status_code=201)
async def upload_proof(request: Request, user: User = Depends(ALUMNI), db: Session = Depends(get_db)):
    upload = MultipartUpload(request)
    await upload.start()
    return await anyio.to_thread.run_sync(_store, db, user, upload)


@router.get("/me/verification-proof")
def get_proof(user: User = Depends(ALUMNI), db: Session = Depends(get_db)):
    return _view(_get(db, user.id))


@router.delete("/me/verification-proof", status_code=204)
def delete_proof(user: User = Depends(ALUMNI), db: Session = Depends(get_db)):
    _delete(db, user)
    return Response(status_code=204)
