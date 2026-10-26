# STUB-RAYNALD
"""File type detection from magic bytes.

Final shape: detect(head, doc_type) -> extension or None. The client's filename is not a
parameter on purpose, because detection must not trust it. The caller passes the first bytes
of the upload; the extension stored in documents.ext comes from here.

Interface-stub stage: recognises pdf, jpg, png and mp4 only. JPEG is always reported as "jpg".
The "ftyp" box also appears in other ISO media files, so the real implementation should check
the brand too.
"""

_ALLOWED = {
    "cv": {"pdf"},
    "ktp": {"jpg", "png", "pdf"},
    "intro_video": {"mp4"},
}


def _sniff(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[4:8] == b"ftyp":
        return "mp4"
    return None


# STUB-RAYNALD
def detect(head: bytes, doc_type: str) -> str | None:
    """Frozen interface: the extension for the content, or None when doc_type does not accept it."""
    ext = _sniff(head)
    return ext if ext in _ALLOWED.get(doc_type, ()) else None