import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app import storage
from app.models import Application, Document, User

MiB = 1024 * 1024

# type -> (allowed extensions, max bytes)
RULES = {
    "cv": ({"pdf"}, 5 * MiB),
    "ktp": ({"jpg", "jpeg", "png", "pdf"}, 5 * MiB),
    "intro_video": ({"mp4"}, 50 * MiB),
}
MAX_PER_TYPE = 5

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "mp4": "video/mp4",
}


def view(doc: Document) -> dict:
    return {
        "id": str(doc.id),
        "type": doc.type,
        "ext": doc.ext,
        "size": doc.size_bytes,
        "created_at": doc.created_at,
    }


def extension_of(filename: str | None) -> str:
    name = filename or ""
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


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


def create(db: Session, user: User, doc_type: str, filename: str | None, data: bytes) -> Document:
    if doc_type not in RULES:
        raise HTTPException(status_code=422, detail="invalid document type")
    exts, max_bytes = RULES[doc_type]
    if extension_of(filename) not in exts:
        raise HTTPException(status_code=415, detail="UNSUPPORTED_FILE_TYPE")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="EMPTY_FILE")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")

    old = list(db.scalars(
        select(Document).where(Document.owner_id == user.id, Document.type == doc_type)
    ))
    if doc_type != "ktp" and len(old) >= MAX_PER_TYPE:
        raise HTTPException(status_code=409, detail="DOCUMENT_LIMIT")

    ext = extension_of(filename)
    try:
        key = storage.save(data, ext)
    except storage.StorageError:
        raise HTTPException(status_code=500, detail="STORAGE_ERROR")

    doc = Document(owner_id=user.id, type=doc_type, ext=ext, size_bytes=len(data), storage_key=key)
    db.add(doc)
    replaced = old if doc_type == "ktp" else []
    old_keys = [r.storage_key for r in replaced]
    for r in replaced:
        db.delete(r)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    for k in old_keys:
        storage.delete(k)
    db.refresh(doc)
    return doc


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


def delete(db: Session, user: User, doc_id: str) -> None:
    doc = get_owned(db, user, doc_id)
    if is_in_use(db, doc):
        raise HTTPException(status_code=409, detail="DOCUMENT_IN_USE")
    key = doc.storage_key
    # Inactive applications keep existing but lose their reference to the document.
    db.execute(update(Application).where(Application.cv_document_id == doc.id).values(cv_document_id=None))
    db.execute(
        update(Application)
        .where(Application.intro_video_document_id == doc.id)
        .values(intro_video_document_id=None)
    )
    db.delete(doc)
    db.commit()
    storage.delete(key)
