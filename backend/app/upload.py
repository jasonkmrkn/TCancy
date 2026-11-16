"""Upload plumbing shared by every endpoint that takes a file (owner: Raynald).

MultipartUpload parses a multipart/form-data body straight from the request stream, so the
file bytes never touch the disk in plaintext. checked_upload() wraps it with the checks every
upload makes, in the same order as app.documents.put: 400 EMPTY_FILE, 415
UNSUPPORTED_FILE_TYPE (from the content via app.filetype, never the filename or the
Content-Type), then 413 FILE_TOO_LARGE while the bytes are read.

Typical use in a router (the blocking part runs in a worker thread):

    upload = MultipartUpload(request)
    await upload.start()
    def store():
        checked = checked_upload(upload, "verification_proof", config.PROOF_MAX_BYTES)
        key = storage.write(encrypt(checked))   # iterate once, front to back
        return checked.ext, checked.size, key
    ext, size, key = await anyio.to_thread.run_sync(store)
"""
import anyio
from fastapi import HTTPException, Request
from python_multipart.multipart import MultipartParser, parse_options_header

from app import filetype

READ_SIZE = 64 * 1024
HEAD_BYTES = 16  

MAX_TYPE_FIELD = 64


class MultipartUpload:
    """The `file` part of a multipart body, parsed straight from the request stream.

    Starlette's UploadFile spools anything over 1 MiB to a temporary file in plaintext, so the
    body is parsed here instead and the file bytes go to documents.put chunk by chunk, never to
    disk. A `type` field, when the endpoint uses one, must come before `file` (the front end
    sends it first); start() returns it, or an empty string when there is none. read() runs
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


class CheckedUpload:
    """The bytes of one upload whose first bytes passed the type check.

    Iterate it once to get the file in pieces; 413 FILE_TOO_LARGE is raised as soon as more
    than max_bytes have been read, so nothing past the limit is ever handed on. `size` is the
    number of bytes handed on so far (the full size once iteration has finished).
    """

    def __init__(self, ext: str, head: bytes, rest, max_bytes: int):
        self.ext = ext
        self.size = 0
        self._head = head
        self._rest = rest
        self._max = max_bytes
        self._used = False

    def __iter__(self):
        if self._used:
            raise RuntimeError("an upload can be read only once")
        self._used = True
        return self._pieces()

    def _pieces(self):
        piece = self._head
        while piece:
            self.size += len(piece)
            if self.size > self._max:
                raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")
            yield piece
            piece = next(self._rest, b"")

    def drain(self) -> int:
        """Read the rest without keeping it (413 still applies) and return the size."""
        for _ in self:
            pass
        return self.size


def checked_upload(stream, kind: str, max_bytes: int, read_size: int = READ_SIZE) -> CheckedUpload:
    """Check an upload read from a file-like `stream` (anything with read(n)).

    400 EMPTY_FILE when there are no bytes at all, 415 UNSUPPORTED_FILE_TYPE when
    filetype.detect(head, kind) does not accept the content. 413 comes later, while iterating.
    """
    rest = iter(lambda: stream.read(read_size), b"")
    head = b""
    for piece in rest:  # read() may return less than asked; the type check needs HEAD_BYTES
        head += piece
        if len(head) >= HEAD_BYTES:
            break
    if not head:
        raise HTTPException(status_code=400, detail="EMPTY_FILE")
    ext = filetype.detect(head, kind)
    if ext is None:
        raise HTTPException(status_code=415, detail="UNSUPPORTED_FILE_TYPE")
    return CheckedUpload(ext, head, rest, max_bytes)
