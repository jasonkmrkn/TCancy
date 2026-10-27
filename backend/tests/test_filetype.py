import pytest
from sqlalchemy import text

from app import filetype
from app.db import engine
from test_document import MAGIC, URL, as_applicant, files_on_disk

PDF = b"%PDF-1.7\n"
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def mp4(brand=b"mp42", size=b"\x00\x00\x00\x18"):
    return size + b"ftyp" + brand + b"\x00\x00\x00\x00mp42isom"


# --- what each document type accepts --------------------------------------------


@pytest.mark.parametrize(
    "doc_type,head,expected",
    [
        ("cv", PDF, "pdf"), ("cv", JPG, None), ("cv", PNG, None), ("cv", mp4(), None),
        ("ktp", PDF, "pdf"), ("ktp", JPG, "jpg"), ("ktp", PNG, "png"), ("ktp", mp4(), None),
        ("intro_video", mp4(), "mp4"), ("intro_video", PDF, None), ("intro_video", JPG, None), ("intro_video", PNG, None),
    ],
)
def test_each_document_type_accepts_only_its_own_kinds(doc_type, head, expected):
    assert filetype.detect(head + b"rest of the file", doc_type) == expected


def test_an_unknown_document_type_accepts_nothing():
    for head in (PDF, JPG, PNG, mp4()):
        assert filetype.detect(head, "selfie") is None
        assert filetype.detect(head, "") is None


# --- pdf, jpeg, png -------------------------------------------------------------


@pytest.mark.parametrize("version", [b"1.0", b"1.4", b"1.7", b"2.0"])
def test_pdf_versions_are_accepted(version):
    assert filetype.detect(b"%PDF-" + version, "cv") == "pdf"
    assert filetype.detect(b"%PDF-" + version + b"\n%\xe2\xe3\xcf\xd3", "cv") == "pdf"


@pytest.mark.parametrize(
    "head",
    [b"%PDF-", b"%PDF-1", b"%PDF-1.", b"%PDF-x.4", b"%PDF-1,4", b"%PDF-1.x", b"%pdf-1.4", b" %PDF-1.4", b"\n%PDF-1.4",
     b"\xef\xbb\xbf%PDF-1.4", b"PDF-1.4", b"%PDF 1.4"],
)
def test_pdf_lookalikes_are_not_pdfs(head):
    assert filetype.detect(head, "cv") is None
    assert filetype.detect(head, "ktp") is None


@pytest.mark.parametrize("head", [b"\xff\xd8", b"\xff\xd8\x00", b"\xd8\xff\xe0", b"\x00\xff\xd8\xff", b"JFIF"])
def test_jpeg_lookalikes_are_not_jpegs(head):
    assert filetype.detect(head, "ktp") is None


@pytest.mark.parametrize("head", [b"\x89PNG\r\n", b"\x89PNG\r\n\x1a", b"\x89PNG\n\x1a\n\r", b"PNG\r\n\x1a\n", b"\x89png\r\n\x1a\n"])
def test_png_lookalikes_are_not_pngs(head):
    assert filetype.detect(head, "ktp") is None


def test_the_signature_alone_is_enough():
    assert filetype.detect(b"\x89PNG\r\n\x1a\n", "ktp") == "png"
    assert filetype.detect(b"\xff\xd8\xff", "ktp") == "jpg"
    assert filetype.detect(b"%PDF-1.4", "cv") == "pdf"


# --- mp4 and its brand ----------------------------------------------------------


@pytest.mark.parametrize("brand", [b"isom", b"iso2", b"mp41", b"mp42", b"avc1"])
def test_the_five_mp4_brands_are_accepted(brand):
    assert filetype.detect(mp4(brand), "intro_video") == "mp4"
    assert filetype.detect(b"\x00\x00\x00\x18ftyp" + brand, "intro_video") == "mp4"  # exactly twelve bytes


@pytest.mark.parametrize(
    "brand",
    [b"qt  ", b"M4V ", b"M4A ", b"3gp4", b"3g2a", b"heic", b"heix", b"mif1", b"avif", b"MSNV", b"dash", b"ISOM", b"mp4 ", b"\x00\x00\x00\x00", b"junk"],
)
def test_other_iso_media_brands_are_not_accepted(brand):
    assert filetype.detect(mp4(brand), "intro_video") is None
    assert filetype.detect(mp4(brand), "ktp") is None


@pytest.mark.parametrize(
    "head",
    [b"", b"ftyp", b"\x00\x00\x00\x18", b"\x00\x00\x00\x18ftyp", b"\x00\x00\x00\x18ftypmp4", b"\x00\x00\x00\x18ftypmp",
     b"\x00\x00\x00\x18moovmp42", b"\x00\x00\x00\x18FTYPmp42", b"\x00\x00\x00\x18 ftypmp42", b"ftypmp42isom", b"\x00\x00\x00\x18free"],
)
def test_an_incomplete_or_misplaced_ftyp_box_is_not_an_mp4(head):
    assert filetype.detect(head, "intro_video") is None


def test_the_box_size_is_not_trusted_or_needed():
    for size in (b"\x00\x00\x00\x00", b"\x00\x00\x00\x01", b"\xff\xff\xff\xff", b"\x00\x00\x00\x20"):
        assert filetype.detect(mp4(size=size), "intro_video") == "mp4"


# --- junk and odd input ---------------------------------------------------------


@pytest.mark.parametrize("doc_type", ["cv", "ktp", "intro_video"])
@pytest.mark.parametrize(
    "head",
    [b"", b"junk", b"\x00" * 64, b"MZ\x90\x00", b"<html><script>alert(1)</script>", b"<?xml version='1.0'?><svg/>", b"#!/bin/sh\n",
     b"PK\x03\x04", b"GIF89a", b"RIFF\x00\x00\x00\x00WEBP", b"\x7fELF", b"%!PS-Adobe-3.0"],
)
def test_other_content_is_rejected_for_every_type(doc_type, head):
    assert filetype.detect(head, doc_type) is None


def test_the_result_is_a_lowercase_extension_without_a_dot():
    for head, doc_type in ((PDF, "cv"), (JPG, "ktp"), (PNG, "ktp"), (mp4(), "intro_video")):
        ext = filetype.detect(head, doc_type)
        assert ext == ext.lower() and not ext.startswith(".") and ext in ("pdf", "jpg", "png", "mp4")


def test_only_the_start_of_the_content_counts():
    assert filetype.detect(b"junk" * 100 + PDF, "cv") is None
    assert filetype.detect(b"\x00" * 16 + PNG, "ktp") is None


def test_text_and_none_are_not_content():
    assert filetype.detect("%PDF-1.4", "cv") is None
    assert filetype.detect(None, "cv") is None
    assert filetype.detect(bytearray(PDF), "cv") == "pdf"
    assert filetype.detect(memoryview(PNG), "ktp") == "png"


def test_the_detect_signature_has_no_filename_in_it():
    import inspect

    assert list(inspect.signature(filetype.detect).parameters) == ["head", "doc_type"]


# --- over HTTP: a forged name or Content-Type does not matter -------------------


def post(client, doc_type, name, content, content_type=None):
    file = (name, content) if content_type is None else (name, content, content_type)
    return client.post(URL, data={"type": doc_type}, files={"file": file})


def nothing_was_stored():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM documents")).scalar()
    return rows == 0 and files_on_disk() == set()


@pytest.mark.parametrize(
    "doc_type,name,content",
    [
        ("cv", "cv.pdf", b"MZ\x90\x00\x03\x00\x00\x00 an executable"),
        ("cv", "cv.pdf", b"<html><script>alert(document.cookie)</script></html>"),
        ("cv", "cv.pdf", b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>"),
        ("cv", "cv.pdf", b"#!/bin/sh\nrm -rf /\n"),
        ("cv", "cv.pdf", b"PK\x03\x04 a zip, or a .docx"),
        ("cv", "cv.pdf", b"GIF89a gif"),
        ("cv", "cv.pdf", PNG + b"png renamed to pdf"),
        ("cv", "cv.pdf.exe", b"MZ\x90\x00"),
        ("ktp", "ktp.jpg", mp4() + b"video renamed to jpg"),
        ("ktp", "ktp.png", b"<html>not an image</html>"),
        ("ktp", "ktp.jpg", b"GIF89a"),
        ("intro_video", "video.mp4", PDF + b"pdf renamed to mp4"),
        ("intro_video", "video.mp4", JPG + b"jpeg renamed to mp4"),
        ("intro_video", "video.mp4", b"MZ\x90\x00"),
        ("intro_video", "video.mp4", mp4(b"qt  ") + b"a QuickTime movie"),
        ("intro_video", "video.mp4", mp4(b"3gp4") + b"a 3GP video"),
        ("intro_video", "video.mp4", mp4(b"heic") + b"a HEIC photo"),
        ("intro_video", "video.mov", b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  "),
    ],
)
def test_a_name_that_says_one_thing_and_content_that_says_another_is_415(client, doc_type, name, content):
    as_applicant(client)
    r = post(client, doc_type, name, content)
    assert r.status_code == 415 and r.json()["detail"] == "UNSUPPORTED_FILE_TYPE"
    assert name not in r.text
    assert nothing_was_stored()


@pytest.mark.parametrize("content_type", ["application/pdf", "image/png", "video/mp4", "text/html", "application/octet-stream"])
def test_the_content_type_the_client_sends_is_ignored(client, content_type):
    as_applicant(client)
    assert post(client, "cv", "cv.pdf", PNG + b"x", content_type).status_code == 415
    assert nothing_was_stored()
    r = post(client, "cv", "cv.bin", PDF + b"x", content_type)
    assert r.status_code == 201 and r.json()["ext"] == "pdf"


def test_the_stored_extension_comes_from_the_content_not_the_name(client):
    as_applicant(client)
    for name, content, ext in (
        ("scan.txt", JPG, "jpg"), ("scan.pdf", PNG, "png"), ("scan", PDF, "pdf"), ("scan.jpg", PDF, "pdf"), ("scan.exe", PDF, "pdf"),
    ):
        r = post(client, "ktp", name, content + b"x")
        assert r.status_code == 201 and r.json()["ext"] == ext, name


@pytest.mark.parametrize("brand", [b"isom", b"iso2", b"mp41", b"mp42", b"avc1"])
def test_every_accepted_mp4_brand_uploads(client, brand):
    as_applicant(client)
    r = post(client, "intro_video", "anything.dat", mp4(brand) + b"frames")
    assert r.status_code == 201 and r.json()["ext"] == "mp4"


def test_the_magic_bytes_the_other_tests_use_are_still_accepted():
    assert filetype.detect(MAGIC["pdf"], "cv") == "pdf"
    assert filetype.detect(MAGIC["png"], "ktp") == "png"
    assert filetype.detect(MAGIC["jpg"], "ktp") == "jpg"
    assert filetype.detect(MAGIC["mp4"], "intro_video") == "mp4"