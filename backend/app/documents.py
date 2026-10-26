"""Documents: uploads stored encrypted, one file per algorithm copy in `document_copies`.

Files are encrypted in CHUNK_SIZE chunks with app.crypto (item "file:<document_id>"). With
ENCRYPTION_POLICY=assignment every upload keeps three copies (aes, des, rc4); with production
only aes. Reads default to the aes copy. Plaintext only ever passes through memory, one chunk
at a time: the des and rc4 copies are made by reading the aes copy back.
"""
import itertools
import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app import config, crypto, filetype, storage
from app.models import Application, Document, DocumentCopy, User

MiB = 1024 * 1024
CHUNK_SIZE = crypto.CHUNK_SIZE

# type -> max bytes; the allowed extensions per type live in filetype.detect
RULES = {
    "cv": 5 * MiB,
    "ktp": 5 * MiB,
    "intro_video": 50 * MiB,
}
MAX_PER_TYPE = 5

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "mp4": "video/mp4",
}

ALGORITHMS = ("aes", "des", "rc4")
_ENCRYPT = {"aes": crypto.aes_encrypt, "des": crypto.des_encrypt, "rc4": crypto.rc4_encrypt}
_DECRYPT = {"aes": crypto.aes_decrypt, "des": crypto.des_decrypt, "rc4": crypto.rc4_decrypt}


def view(doc: Document) -> dict:
    return {
        "id": str(doc.id),
        "type": doc.type,
        "ext": doc.ext,
        "size": doc.size_bytes,
        "created_at": doc.created_at,
    }


def is_in_use(db: Session, doc: Document) -> bool:
    """True when an active (submitted, shortlisted or accepted) application references the document."""
    return db.scalar(
        select(Application.id).where(
            Application.status.in_(("submitted", "shortlisted", "accepted")),
            or_(
                Application.cv_document_id == doc.id,
                Application.intro_video_document_id == doc.id,
            ),
        ).limit(1)
    ) is not None


def _algorithms() -> tuple[str, ...]:
    return ALGORITHMS if config.ENCRYPTION_POLICY == "assignment" else ("aes",)


def _item(document_id: uuid.UUID) -> str:
    return "file:%s" % document_id


def _copy_keys(db: Session, *where) -> list[str]:
    return list(db.scalars(
        select(DocumentCopy.storage_key).join(Document, Document.id == DocumentCopy.document_id).where(*where)
    ))


def _rechunk(pieces):
    """Regroup pieces of any size into CHUNK_SIZE chunks; only the last may be shorter."""
    buf = bytearray()
    for piece in pieces:
        buf += piece
        while len(buf) >= CHUNK_SIZE:
            yield bytes(buf[:CHUNK_SIZE])
            del buf[:CHUNK_SIZE]
    if buf:
        yield bytes(buf)


def _encrypt(chunks, alg: str, salt: bytes, nonce: bytes | None, item: str):
    for index, chunk in enumerate(chunks):
        ciphertext = _ENCRYPT[alg](chunk, salt, nonce, item, index)
        # A4: integrity tag for this ciphertext chunk goes here.
        yield ciphertext


def _decrypt(pieces, alg: str, salt: bytes, nonce: bytes | None, item: str):
    for index, chunk in enumerate(_rechunk(pieces)):
        # A4: verify this chunk's integrity tag here before decrypting.
        yield _DECRYPT[alg](chunk, salt, nonce, item, index)


def list_for(db: Session, user: User) -> list[Document]:
    return list(db.scalars(
        select(Document).where(Document.owner_id == user.id)
        .order_by(Document.created_at, Document.id)
    ))


def get_owned(db: Session, user: User, doc_id: str) -> Document:
    try:
        key = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="DOCUMENT_NOT_FOUND")
    doc = db.scalar(select(Document).where(Document.id == key, Document.owner_id == user.id))
    if doc is None:
        raise HTTPException(status_code=404, detail="DOCUMENT_NOT_FOUND")
    return doc


def delete_for_user(db: Session, user: User, doc_id: str) -> None:
    doc = get_owned(db, user, doc_id)
    if is_in_use(db, doc):
        raise HTTPException(status_code=409, detail="DOCUMENT_IN_USE")
    keys = _copy_keys(db, Document.id == doc.id)
    # Inactive applications keep existing but lose their reference to the document. Done here
    # because the composite foreign keys (document id, applicant id) cannot SET NULL one column.
    db.execute(update(Application).where(Application.cv_document_id == doc.id).values(cv_document_id=None))
    db.execute(
        update(Application)
        .where(Application.intro_video_document_id == doc.id)
        .values(intro_video_document_id=None)
    )
    db.delete(doc)  # the copy rows go with it (ON DELETE CASCADE)
    db.commit()
    for key in keys:
        storage.delete(key)


def _owner(db: Session, owner_id: uuid.UUID) -> User:
    user = db.get(User, owner_id)
    if user is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return user


def put(db: Session, owner_id: uuid.UUID, doc_type: str, filename: str | None, stream) -> dict:
    """Store an upload read once, front to back, from a file-like `stream`.

    Returns {id, type, ext, size, created_at}. Checks, in order: 422 unknown type, 400 EMPTY_FILE,
    415 UNSUPPORTED_FILE_TYPE (from the content, never the filename), 413 FILE_TOO_LARGE,
    409 DOCUMENT_LIMIT. The filename is not stored. All copies are written or none, and this
    commits: the one exception to "the caller commits", because the files on disk must pair
    with the database rows.
    """
    user = _owner(db, owner_id)
    if doc_type not in RULES:
        raise HTTPException(status_code=422, detail="invalid document type")
    max_bytes = RULES[doc_type]
    chunks = _rechunk(iter(lambda: stream.read(CHUNK_SIZE), b""))
    head = next(chunks, b"")
    if not head:
        raise HTTPException(status_code=400, detail="EMPTY_FILE")
    ext = filetype.detect(head, doc_type)
    if ext is None:
        raise HTTPException(status_code=415, detail="UNSUPPORTED_FILE_TYPE")

    size = 0

    def counted():
        nonlocal size
        for chunk in itertools.chain([head], chunks):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")
            yield chunk

    old = list(db.scalars(select(Document).where(Document.owner_id == user.id, Document.type == doc_type)))
    if doc_type != "ktp" and len(old) >= MAX_PER_TYPE:
        for _ in counted():  # an oversize file still answers 413 before 409
            pass
        raise HTTPException(status_code=409, detail="DOCUMENT_LIMIT")

    doc_id = uuid.uuid4()
    item = _item(doc_id)
    copies = []
    try:
        for alg in _algorithms():
            salt, nonce = crypto.new_params(alg, item)
            if not copies:
                source = counted()
            else:
                aes = copies[0]
                source = _decrypt(storage.read(aes.storage_key), "aes", aes.salt, aes.nonce, item)
            key = storage.write(_encrypt(source, alg, salt, nonce, item))
            copies.append(DocumentCopy(
                document_id=doc_id, algorithm=alg, salt=salt, nonce=nonce,
                storage_key=key, chunk_size=CHUNK_SIZE, ciphertext_size=size,
            ))
        doc = Document(id=doc_id, owner_id=user.id, type=doc_type, ext=ext, size_bytes=size)
        db.add(doc)
        db.add_all(copies)
        replaced = old if doc_type == "ktp" else []
        old_keys = _copy_keys(db, Document.id.in_([r.id for r in replaced])) if replaced else []
        for r in replaced:
            db.delete(r)
        db.commit()
    except Exception as e:
        db.rollback()
        for c in copies:
            storage.delete(c.storage_key)
        if isinstance(e, storage.StorageError):
            raise HTTPException(status_code=500, detail="STORAGE_ERROR") from e
        raise
    for key in old_keys:
        storage.delete(key)
    db.refresh(doc)
    return view(doc)


def list_for_owner(db: Session, owner_id: uuid.UUID) -> list[dict]:
    """The owner's documents, oldest first, in the same shape as view()."""
    return [view(d) for d in list_for(db, _owner(db, owner_id))]


def get_meta(db: Session, document_id) -> Document | None:
    """The Document row (id, owner_id, type, ext, size_bytes) or None."""
    if not isinstance(document_id, uuid.UUID):
        try:
            document_id = uuid.UUID(str(document_id))
        except ValueError:
            return None
    return db.get(Document, document_id)


def stream(db: Session, document_id, *, algorithm="aes"):
    """An iterator of the document's plaintext bytes, decrypted chunk by chunk.

    404 DOCUMENT_NOT_FOUND when the document or its copy for `algorithm` is missing (des and rc4
    under the production policy). 500 STORAGE_ERROR when the file cannot be read; the first read
    happens here, before any response starts. The iterator holds only plain values, so it keeps
    working after the database session is closed.
    """
    doc = get_meta(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="DOCUMENT_NOT_FOUND")
    copy = db.scalar(select(DocumentCopy).where(
        DocumentCopy.document_id == doc.id, DocumentCopy.algorithm == algorithm,
    ))
    if copy is None:
        raise HTTPException(status_code=404, detail="DOCUMENT_NOT_FOUND")
    pieces = storage.read(copy.storage_key)
    try:
        first = next(pieces, b"")
    except storage.StorageError:
        raise HTTPException(status_code=500, detail="STORAGE_ERROR")
    return _decrypt(itertools.chain([first], pieces), algorithm, copy.salt, copy.nonce, _item(doc.id))


def delete(db: Session, owner_id: uuid.UUID, document_id) -> None:
    """Delete one document of the owner, its copies and their files.

    404 DOCUMENT_NOT_FOUND, 409 DOCUMENT_IN_USE. Wraps delete_for_user(), so it commits like it.
    """
    delete_for_user(db, _owner(db, owner_id), str(document_id))


def purge_user_files(db: Session, user_id: uuid.UUID) -> None:
    """Remove every stored file of a user from disk.

    Called by account.py before the account is deleted; the database rows go with the user
    (ON DELETE CASCADE). Does not commit.
    """
    for key in _copy_keys(db, Document.owner_id == user_id):
        storage.delete(key)
