"""A2 V2 (Raynald): file type and upload checks for the alumni verification proof."""
import io

import pytest
from fastapi import HTTPException

from app import config, filetype
from app.main import app
from app.middleware import BodySizeLimitMiddleware
from app.upload import CheckedUpload, checked_upload

PDF = b"%PDF-1.7\n" + b"x" * 100
JPG = b"\xff\xd8\xff\xe0" + b"x" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 100
MP4 = b"\x00\x00\x00\x18ftypisom" + b"x" * 100
KIND = "verification_proof"


class Trickle:
    """A stream that returns at most `step` bytes per read, like a slow network body."""

    def __init__(self, data: bytes, step: int):
        self._buf = io.BytesIO(data)
        self._step = step

    def read(self, n: int) -> bytes:
        return self._buf.read(min(n, self._step))


def status_of(fn):
    with pytest.raises(HTTPException) as e:
        fn()
    return e.value.status_code, e.value.detail


# --- filetype -------------------------------------------------------------------------


@pytest.mark.parametrize("data, ext", [(PDF, "pdf"), (JPG, "jpg"), (PNG, "png")])
def test_proof_accepts_pdf_jpg_png(data, ext):
    assert filetype.detect(data, KIND) == ext


@pytest.mark.parametrize("data", [MP4, b"GIF89a" + b"x" * 20, b"PK\x03\x04" + b"x" * 20, b"plain text, not a file"])
def test_proof_refuses_everything_else(data):
    assert filetype.detect(data, KIND) is None


def test_other_document_types_are_unchanged():
    assert filetype.detect(PDF, "cv") == "pdf"
    assert filetype.detect(PNG, "cv") is None
    assert filetype.detect(MP4, "intro_video") == "mp4"


# --- checked_upload -------------------------------------------------------------------


def test_empty_upload_is_400():
    assert status_of(lambda: checked_upload(io.BytesIO(b""), KIND, 100)) == (400, "EMPTY_FILE")


def test_wrong_type_is_415_before_reading_the_rest():
    stream = io.BytesIO(b"MZ" + b"\x00" * 1_000_000)  # a Windows executable
    assert status_of(lambda: checked_upload(stream, KIND, 10)) == (415, "UNSUPPORTED_FILE_TYPE")
    assert stream.tell() <= 64 * 1024  # only the head was read, the body was not


def test_type_comes_from_content_even_in_tiny_reads():
    checked = checked_upload(Trickle(PNG, 3), KIND, 1000)  # head arrives 3 bytes at a time
    assert checked.ext == "png"
    assert b"".join(checked) == PNG
    assert checked.size == len(PNG)


def test_exact_limit_passes_and_one_byte_more_is_413():
    limit = config.PROOF_MAX_BYTES
    exact = PDF + b"y" * (limit - len(PDF))
    checked = checked_upload(io.BytesIO(exact), KIND, limit)
    assert b"".join(checked) == exact and checked.size == limit

    over = checked_upload(io.BytesIO(exact + b"y"), KIND, limit)
    assert status_of(lambda: b"".join(over)) == (413, "FILE_TOO_LARGE")


def test_413_stops_before_handing_on_the_byte_over_the_limit():
    handed = []
    checked = checked_upload(Trickle(PDF + b"z" * 50, 10), KIND, 40)
    with pytest.raises(HTTPException) as e:
        for piece in checked:
            handed.append(piece)
    assert e.value.status_code == 413
    assert sum(map(len, handed)) <= 40


def test_drain_reports_size_and_still_enforces_the_limit():
    assert checked_upload(io.BytesIO(PDF), KIND, 1000).drain() == len(PDF)
    big = checked_upload(io.BytesIO(PDF), KIND, 50)
    assert status_of(big.drain) == (413, "FILE_TOO_LARGE")


def test_an_upload_can_be_read_only_once():
    checked = checked_upload(io.BytesIO(PDF), KIND, 1000)
    b"".join(checked)
    with pytest.raises(RuntimeError):
        iter(checked)
    assert isinstance(checked, CheckedUpload)


# --- body limit for the proof endpoint -------------------------------------------------


def test_proof_endpoint_has_its_own_body_limit_above_the_file_limit():
    limits = None
    for m in app.user_middleware:
        if m.cls is BodySizeLimitMiddleware:
            limits = m.kwargs["limits"]
    assert limits is not None
    proof_limit = limits[("POST", "/api/v1/me/verification-proof")]
    # room for the multipart framing around a file of exactly PROOF_MAX_BYTES, but not much more
    assert config.PROOF_MAX_BYTES < proof_limit <= config.PROOF_MAX_BYTES + 2 * 1024 * 1024
