"""File type detection from magic bytes.

detect(head, doc_type) -> extension or None. The client's filename and Content-Type are not
parameters on purpose, because detection must not trust them. The caller passes the first
bytes of the upload; the extension stored in documents.ext comes from here.

What is recognised, and only at the very start of the file:
  pdf  "%PDF-" and a version such as 1.7 or 2.0
  jpg  FF D8 FF (every JPEG is reported as "jpg")
  png  the eight-byte PNG signature
  mp4  an "ftyp" box whose brand is one of isom, iso2, mp41, mp42 or avc1. The "ftyp" box
       also starts other ISO media files (QuickTime, HEIC, 3GP...), so the brand is checked.

This looks at the start of the content only. It does not validate the rest of the file and it
is not a virus scan.
"""

_ALLOWED = {
    "cv": {"pdf"},
    "ktp": {"jpg", "png", "pdf"},
    "intro_video": {"mp4"},
}

_MP4_BRANDS = frozenset({b"isom", b"iso2", b"mp41", b"mp42", b"avc1"})
_DIGITS = b"0123456789"


def _sniff(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        version = head[5:8]
        if len(version) == 3 and version[0] in _DIGITS and version[1:2] == b"." and version[2] in _DIGITS:
            return "pdf"
        return None
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[4:8] == b"ftyp" and head[8:12] in _MP4_BRANDS:
        return "mp4"
    return None


def detect(head: bytes, doc_type: str) -> str | None:
    """Frozen interface: the extension for the content, or None when doc_type does not accept it."""
    if not isinstance(head, (bytes, bytearray, memoryview)):
        return None
    ext = _sniff(bytes(head[:16]))
    return ext if ext in _ALLOWED.get(doc_type, ()) else None