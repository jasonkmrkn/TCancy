from typing import Literal

import anyio
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import audit, documents
from app.db import get_db
from app.deps import require_role
from app.models import User
from app.upload import MultipartUpload

router = APIRouter(prefix="/api/v1", tags=["documents"])


def _audit(db: Session, request: Request, user: User, action: str, doc_id, doc_type: str, size: int) -> None:
    audit.record(
        db, actor_id=user.id, actor_role=user.role, action=action,
        target_type="document", target_id=doc_id,
        details=audit.details(size=size, **{doc_type: 1}),
        **audit.client(request),
    )
    db.commit()


@router.post("/me/documents", status_code=201)
async def upload_document(
    request: Request,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    upload = MultipartUpload(request)
    doc_type = await upload.start()
    meta = await anyio.to_thread.run_sync(documents.put, db, user.id, doc_type, None, upload)
    await anyio.to_thread.run_sync(
        _audit, db, request, user, "document.upload", meta["id"], meta["type"], meta["size"]
    )
    return meta


@router.get("/me/documents")
def list_documents(
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    return [documents.view(d) for d in documents.list_for(db, user)]


@router.get("/me/documents/{doc_id}/download")
def download_document(
    doc_id: str,
    request: Request,
    algorithm: Literal["aes", "des", "rc4"] = "aes",
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    doc = documents.get_owned(db, user, doc_id)
    body = documents.stream(db, doc.id, algorithm=algorithm)
    media_type = documents.MEDIA_TYPES.get(doc.ext, "application/octet-stream")
    filename = "%s.%s" % (doc.type, doc.ext)
    _audit(db, request, user, "document.download", doc.id, doc.type, doc.size_bytes)
    return StreamingResponse(
        body, media_type=media_type,
        headers={"Content-Disposition": 'attachment; filename="%s"' % filename},
    )


@router.delete("/me/documents/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    request: Request,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    doc = documents.get_owned(db, user, doc_id)
    target, doc_type, size = doc.id, doc.type, doc.size_bytes
    documents.delete_for_user(db, user, doc_id)
    _audit(db, request, user, "document.delete", target, doc_type, size)
    return Response(status_code=204)
