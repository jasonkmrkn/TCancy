from typing import Literal

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from python_multipart.multipart import MultipartParser, parse_options_header
from sqlalchemy.orm import Session

from app import audit, clientip, documents
from app.db import get_db
from app.deps import require_role
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["documents"])

MAX_TYPE_FIELD = 64


class _Upload:
    """The `file` part of a multipart body, parsed straight from the request stream.

    Starlette's UploadFile spools anything over 1 MiB to a temporary file in plaintext, so the
    body is parsed here instead and the file bytes go to documents.put chunk by chunk, never to
    disk. The `type` field must come before `file` (the front end sends it first). read() runs
    in a worker thread and pulls more of the body from the event loop when it needs it.
    """

    def __init__(self, request: Request):
        content_type, params = parse_options_header(request.headers.get("content-type", ""))
        if content_type != b"multipart/form-data" or not params.get(b"boundary"):
            raise HTTPException(status_code=422, detail="INVALID_UPLOAD")
        self._body = request.stream().__aiter__()
        self._eof = False
        self._header_field = bytearray()
        self._header_value = bytearray()
        self._part = None
        self._type = bytearray()
        self._in_file = False
        self._file_done = False
        self._buf = bytearray()
        self._parser = MultipartParser(params[b"boundary"], {
            "on_part_begin": self._on_part_begin,
            "on_header_field": lambda d, s, e: self._header_field.extend(d[s:e]),
            "on_header_value": lambda d, s, e: self._header_value.extend(d[s:e]),
            "on_header_end": self._on_header_end,
            "on_headers_finished": self._on_headers_finished,
            "on_part_data": self._on_part_data,
            "on_part_end": self._on_part_end,
        })

    def _on_part_begin(self):
        self._part = None

    def _on_header_end(self):
        if bytes(self._header_field).lower() == b"content-disposition":
            self._part = parse_options_header(bytes(self._header_value))[1].get(b"name")
        self._header_field.clear()
        self._header_value.clear()

    def _on_headers_finished(self):
        if self._part == b"file" and not self._file_done:
            self._in_file = True

    def _on_part_data(self, data, start, end):
        if self._in_file:
            self._buf += data[start:end]
        elif self._part == b"type" and not self._file_done:
            self._type += data[start:end]
            if len(self._type) > MAX_TYPE_FIELD:
                raise HTTPException(status_code=422, detail="invalid document type")

    def _on_part_end(self):
        if self._in_file:
            self._in_file = False
            self._file_done = True

    async def _pump(self) -> None:
        try:
            chunk = await self._body.__anext__()
        except StopAsyncIteration:
            chunk = b""
        try:
            if chunk:
                self._parser.write(chunk)
            else:
                self._eof = True
                self._parser.finalize()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=422, detail="INVALID_UPLOAD")

    async def start(self) -> str:
        """Read up to the start of the file data and return the `type` field."""
        while not (self._in_file or self._file_done or self._eof):
            await self._pump()
        if not (self._in_file or self._file_done):
            raise HTTPException(status_code=422, detail="INVALID_UPLOAD")
        return self._type.decode(errors="replace")

    def read(self, n: int) -> bytes:
        while len(self._buf) < n and not (self._file_done or self._eof):
            anyio.from_thread.run(self._pump)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


def _audit(db: Session, request: Request, user: User, action: str, doc_id, doc_type: str, size: int) -> None:
    audit.record(
        db, actor_id=user.id, actor_role=user.role, action=action,
        target_type="document", target_id=doc_id,
        ip=clientip.client_ip(request), user_agent=request.headers.get("user-agent"),
        details={"type": doc_type, "size": size},
    )
    db.commit()


@router.post("/me/documents", status_code=201)
async def upload_document(
    request: Request,
    user: User = Depends(require_role("applicant")),
    db: Session = Depends(get_db),
):
    upload = _Upload(request)
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
