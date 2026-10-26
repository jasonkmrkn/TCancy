from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import documents, storage
from app.db import get_db
from app.deps import require_role
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.post("/me/documents", status_code=201)
async def upload_document(
    type: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    # Read one byte past the largest limit so oversize files are detected without reading everything.
    data = await file.read(50 * documents.MiB + 1)
    doc = documents.create(db, user, type, file.filename, data)
    return documents.view(doc)


@router.get("/me/documents")
def list_documents(
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    return [documents.view(d) for d in documents.list_for(db, user)]


@router.get("/me/documents/{doc_id}/download")
def download_document(
    doc_id: str,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    doc = documents.get_owned(db, user, doc_id)
    if not storage.exists(doc.storage_key):
        raise HTTPException(status_code=404, detail="DOCUMENT_NOT_FOUND")
    return FileResponse(
        storage.path_of(doc.storage_key),
        media_type=documents.MEDIA_TYPES.get(doc.ext, "application/octet-stream"),
        filename="%s.%s" % (doc.type, doc.ext),
        content_disposition_type="attachment",
    )


@router.delete("/me/documents/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    documents.delete_for_user(db, user, doc_id)
    return Response(status_code=204)
