"""Contract for app.filetype.detect: a lowercase extension without a dot, or None."""
import pytest

from app import filetype

DOC_TYPES = ["cv", "ktp", "intro_video"]
HEADS = [
    b"%PDF-1.7\n",
    b"\xff\xd8\xff\xe0",
    b"\x89PNG\r\n\x1a\n",
    b"\x00\x00\x00\x18ftypmp42",
    b"junk",
]


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_junk_bytes_are_rejected(doc_type):
    assert filetype.detect(b"junk", doc_type) is None
    assert filetype.detect(b"", doc_type) is None


@pytest.mark.parametrize("head", HEADS)
def test_result_is_a_lowercase_extension_or_none(head):
    for doc_type in DOC_TYPES:
        ext = filetype.detect(head, doc_type)
        if ext is not None:
            assert isinstance(ext, str)
            assert ext and ext == ext.lower() and not ext.startswith(".")