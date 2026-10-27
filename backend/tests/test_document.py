import io
import os
import uuid

import pytest
import starlette.formparsers
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import audit, config, documents, filetype, storage
from app.db import engine
from app.models import Application, Job, User
from helpers import make_alumni_profile, make_profile, password_hash
from test_vault import empty_database

AUTH = "/api/v1/auth"
URL = "/api/v1/me/documents"
MiB = 1024 * 1024
CHUNK = documents.CHUNK_SIZE

# Real magic bytes, so the uploads pass content-based type detection.
MAGIC = {
    "pdf": b"%PDF-1.4\n",
    "png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
    "jpg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00",
    "mp4": b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom",
}


def register_applicant(client, username="budi"):
    r = client.post(
        AUTH + "/register",
        json={"username": username, "password": "rahasia123", "profile": make_profile()},
    )
    assert r.status_code == 201
    return r.json()["id"]


def login(client, username):
    r = client.post(AUTH + "/login", json={"username": username, "password": "rahasia123"})
    assert r.status_code == 200


def as_applicant(client, username="budi"):
    uid = register_applicant(client, username)
    login(client, username)
    return uid


def content_for(name, body=b"data"):
    return MAGIC.get(name.rsplit(".", 1)[-1].lower(), b"") + body


def upload(client, doc_type, name, content=None):
    content = content_for(name) if content is None else content
    return client.post(URL, data={"type": doc_type}, files={"file": (name, content)})


def download(client, doc_id, algorithm=None):
    query = "" if algorithm is None else "?algorithm=" + algorithm
    return client.get("%s/%s/download%s" % (URL, doc_id, query))


def files_on_disk():
    root = config.UPLOAD_DIR
    return {
        os.path.relpath(os.path.join(d, f), root) for d, _, names in os.walk(root) for f in names
    } if os.path.isdir(root) else set()


def disk_bytes():
    return [open(os.path.join(config.UPLOAD_DIR, p), "rb").read() for p in files_on_disk()]


@pytest.fixture
def policy(monkeypatch):
    def _set(value):
        monkeypatch.setattr(config, "ENCRYPTION_POLICY", value)

    _set("assignment")
    return _set


# --- round trip --------------------------------------------------------------


def test_upload_then_download_is_identical(client, policy):
    as_applicant(client)
    content = b"%PDF-1.4 hello \x00\x01\x02 world"
    r = upload(client, "cv", "My CV.PDF", content)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "type", "ext", "size", "created_at"}
    assert body["type"] == "cv" and body["ext"] == "pdf" and body["size"] == len(content)

    d = download(client, body["id"])
    assert d.status_code == 200
    assert d.content == content
    assert d.headers["content-disposition"].startswith("attachment")
    assert d.headers["content-type"] == "application/pdf"


@pytest.mark.parametrize(
    "size", [1, CHUNK - 1, CHUNK, CHUNK + 1, 10 * MiB], ids=["1", "4MiB-1", "4MiB", "4MiB+1", "10MiB"]
)
def test_round_trip_sizes_on_every_copy(client, policy, monkeypatch, size):
    # Content type is not the point here, and a 1-byte file has no magic bytes.
    monkeypatch.setattr(filetype, "detect", lambda head, doc_type: "mp4")
    as_applicant(client)
    content = os.urandom(size)
    doc = upload(client, "intro_video", "v.mp4", content).json()
    assert doc["size"] == size
    for alg in ("aes", "des", "rc4"):
        assert download(client, doc["id"], alg).content == content


def test_des_and_rc4_copies_decrypt_like_aes(client, policy):
    as_applicant(client)
    content = content_for("a.pdf", os.urandom(3 * MiB))
    doc = upload(client, "cv", "a.pdf", content).json()
    aes = download(client, doc["id"], "aes").content
    assert aes == content
    assert download(client, doc["id"], "des").content == aes
    assert download(client, doc["id"], "rc4").content == aes


def test_files_on_disk_are_not_plaintext(client, policy):
    as_applicant(client)
    marker = b"NIK 3578012345678901 Budi Santoso " * 50
    upload(client, "cv", "a.pdf", content_for("a.pdf", marker))
    stored = disk_bytes()
    assert len(stored) == 3
    for data in stored:
        assert marker[:34] not in data
        assert not data.startswith(MAGIC["pdf"])


def test_list_documents(client, policy):
    as_applicant(client)
    assert client.get(URL).json() == []
    a = upload(client, "cv", "a.pdf").json()
    b = upload(client, "intro_video", "v.mp4").json()
    got = client.get(URL).json()
    assert [d["id"] for d in got] == [a["id"], b["id"]]
    assert set(got[0]) == {"id", "type", "ext", "size", "created_at"}


# --- validation --------------------------------------------------------------


def test_type_comes_from_content_not_filename(client, policy):
    as_applicant(client)
    assert upload(client, "cv", "a.pdf", content_for("a.png")).status_code == 415
    assert upload(client, "cv", "a.pdf", b"not really a pdf").status_code == 415
    assert upload(client, "intro_video", "a.mp4", content_for("a.pdf")).status_code == 415
    assert upload(client, "ktp", "a.png", content_for("a.mp4")).status_code == 415
    r = upload(client, "cv", "a.pdf", content_for("a.png"))
    assert r.json()["detail"] == "UNSUPPORTED_FILE_TYPE"
    # The stored extension is the detected one; the filename is ignored.
    assert upload(client, "ktp", "scan.txt", content_for("a.jpg")).json()["ext"] == "jpg"
    assert upload(client, "ktp", "noext", content_for("a.png")).json()["ext"] == "png"
    assert upload(client, "ktp", "k.pdf").json()["ext"] == "pdf"


def test_unknown_type_422(client, policy):
    as_applicant(client)
    assert upload(client, "passport", "a.pdf").status_code == 422
    assert client.post(URL, files={"file": ("a.pdf", content_for("a.pdf"))}).status_code == 422


def test_malformed_upload_422(client, policy):
    as_applicant(client)
    r = client.post(URL, data={"type": "cv"})
    assert r.status_code == 422 and r.json()["detail"] == "INVALID_UPLOAD"
    r = client.post(URL, content=b"garbage", headers={"Content-Type": "multipart/form-data; boundary=xyz"})
    assert r.status_code == 422 and r.json()["detail"] == "INVALID_UPLOAD"
    r = client.post(URL, content=b"{}", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["detail"] == "INVALID_UPLOAD"


def test_empty_file_400(client, policy):
    as_applicant(client)
    r = upload(client, "cv", "a.pdf", b"")
    assert r.status_code == 400
    assert r.json()["detail"] == "EMPTY_FILE"
    assert files_on_disk() == set()


def test_size_limits_413_leave_nothing_on_disk(client, policy):
    as_applicant(client)
    assert upload(client, "cv", "a.pdf", content_for("a.pdf", b"x" * (5 * MiB))).status_code == 413
    assert upload(client, "ktp", "a.png", content_for("a.png", b"x" * (5 * MiB))).status_code == 413
    assert upload(client, "intro_video", "a.mp4", content_for("a.mp4", b"x" * (50 * MiB))).status_code == 413
    r = upload(client, "cv", "a.pdf", content_for("a.pdf", b"x" * (5 * MiB)))
    assert r.json()["detail"] == "FILE_TOO_LARGE"
    assert files_on_disk() == set()
    assert client.get(URL).json() == []
    exact = content_for("a.pdf", b"x" * (5 * MiB - len(MAGIC["pdf"])))
    assert upload(client, "cv", "a.pdf", exact).status_code == 201
    assert upload(client, "intro_video", "a.mp4", content_for("a.mp4", b"x" * (6 * MiB))).status_code == 201
    assert len(client.get(URL).json()) == 2


def test_validation_order(client, policy):
    as_applicant(client)
    big_png = content_for("a.png", b"x" * (5 * MiB))
    big_pdf = content_for("a.pdf", b"x" * (5 * MiB))
    assert upload(client, "passport", "a.png", b"").status_code == 422  # type before empty
    assert upload(client, "cv", "a.pdf", b"").status_code == 400  # empty before type detection
    assert upload(client, "cv", "a.png", big_png).status_code == 415  # content type before size
    for i in range(5):
        assert upload(client, "cv", "c%d.pdf" % i).status_code == 201
    assert upload(client, "cv", "a.pdf", big_pdf).status_code == 413  # size before the limit
    assert upload(client, "cv", "c6.pdf").status_code == 409


def test_limit_five_per_type_409(client, policy):
    as_applicant(client)
    for i in range(5):
        assert upload(client, "cv", "c%d.pdf" % i).status_code == 201
    before = files_on_disk()
    r = upload(client, "cv", "c6.pdf")
    assert r.status_code == 409
    assert r.json()["detail"] == "DOCUMENT_LIMIT"
    assert files_on_disk() == before
    # other types are counted separately
    assert upload(client, "intro_video", "v.mp4").status_code == 201


def test_new_ktp_replaces_old(client, policy):
    as_applicant(client)
    first = upload(client, "ktp", "a.jpg", content_for("a.jpg", b"one")).json()
    before = files_on_disk()
    second = upload(client, "ktp", "b.png", content_for("b.png", b"two")).json()
    docs = client.get(URL).json()
    assert [d["id"] for d in docs] == [second["id"]]
    assert download(client, first["id"]).status_code == 404
    assert download(client, second["id"]).content == content_for("b.png", b"two")
    assert len(files_on_disk()) == len(before) == 3
    assert files_on_disk().isdisjoint(before)


# --- policy ------------------------------------------------------------------


def test_production_keeps_only_aes(client, policy):
    policy("production")
    as_applicant(client)
    content = content_for("a.pdf", b"prod")
    doc = upload(client, "cv", "a.pdf", content).json()
    assert len(files_on_disk()) == 1
    assert download(client, doc["id"]).content == content
    for alg in ("des", "rc4"):
        r = download(client, doc["id"], alg)
        assert r.status_code == 404 and r.json()["detail"] == "DOCUMENT_NOT_FOUND"


def test_unknown_algorithm_is_422(client, policy):
    as_applicant(client)
    doc = upload(client, "cv", "a.pdf").json()
    assert download(client, doc["id"], "ecb").status_code == 422


# --- access ------------------------------------------------------------------


def test_other_users_document_is_404(client, policy):
    as_applicant(client, "budi")
    doc = upload(client, "cv", "a.pdf").json()
    client.post(AUTH + "/logout")
    as_applicant(client, "siti")
    r = download(client, doc["id"])
    assert r.status_code == 404 and r.json()["detail"] == "DOCUMENT_NOT_FOUND"
    r = client.delete("%s/%s" % (URL, doc["id"]))
    assert r.status_code == 404 and r.json()["detail"] == "DOCUMENT_NOT_FOUND"
    assert client.get(URL).json() == []
    login(client, "budi")
    assert download(client, doc["id"]).status_code == 200


def test_unknown_or_malformed_id_404(client, policy):
    as_applicant(client)
    assert client.get(URL + "/not-a-uuid/download").status_code == 404
    assert client.delete(URL + "/00000000-0000-0000-0000-000000000000").status_code == 404


def test_requires_login_and_applicant_role(client, policy):
    assert client.get(URL).status_code == 401
    assert upload(client, "cv", "a.pdf").status_code == 401
    client.post(
        AUTH + "/register/alumni",
        json={"username": "alumna", "password": "rahasia123", "profile": make_alumni_profile()},
    )
    login(client, "alumna")
    assert client.get(URL).status_code == 403  # pending alumni
    assert upload(client, "cv", "a.pdf").status_code == 403


# --- all or nothing ----------------------------------------------------------


def _boom(*args, **kwargs):
    raise RuntimeError("cipher failed")


@pytest.mark.parametrize("alg", ["des", "rc4"])
def test_failure_in_a_later_copy_leaves_no_row_or_file(client, policy, monkeypatch, alg):
    uid = uuid.UUID(as_applicant(client))
    monkeypatch.setitem(documents._ENCRYPT, alg, _boom)
    with Session(engine) as db:
        with pytest.raises(RuntimeError):
            documents.put(db, uid, "cv", "a.pdf", io.BytesIO(content_for("a.pdf", os.urandom(5 * MiB - 100))))
    assert files_on_disk() == set()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM document_copies")).scalar() == 0


def test_storage_failure_on_a_later_copy_is_500_and_leaves_nothing(client, policy, monkeypatch):
    as_applicant(client)
    real_write = storage.write
    calls = []

    def flaky_write(chunks):
        calls.append(1)
        if len(calls) == 2:
            raise storage.StorageError("disk full")
        return real_write(chunks)

    monkeypatch.setattr(storage, "write", flaky_write)
    r = upload(client, "cv", "a.pdf")
    assert r.status_code == 500 and r.json()["detail"] == "STORAGE_ERROR"
    assert files_on_disk() == set()
    assert client.get(URL).json() == []


def test_unreadable_file_is_500_storage_error(client, policy):
    as_applicant(client)
    doc = upload(client, "cv", "a.pdf").json()
    for path in files_on_disk():
        os.remove(os.path.join(config.UPLOAD_DIR, path))
    r = download(client, doc["id"])
    assert r.status_code == 500 and r.json()["detail"] == "STORAGE_ERROR"


# --- delete ------------------------------------------------------------------


def test_delete_removes_row_and_every_copy(client, policy):
    as_applicant(client)
    doc = upload(client, "cv", "a.pdf").json()
    assert len(files_on_disk()) == 3
    r = client.delete("%s/%s" % (URL, doc["id"]))
    assert r.status_code == 204
    assert client.get(URL).json() == []
    assert files_on_disk() == set()


def _application(applicant_id, doc_id, status="submitted"):
    with Session(engine) as db:
        employer = User(username="emp_%s" % uuid.uuid4().hex[:6], password_hash=password_hash(),
                        role="alumni", status="active")
        db.add(employer)
        db.commit()
        job = Job(owner_id=employer.id, title="Backend Intern", company="Acme",
                  type="internship", work_mode="remote", description="Build things")
        db.add(job)
        db.commit()
        row = Application(job_id=job.id, applicant_id=uuid.UUID(applicant_id),
                          cv_document_id=uuid.UUID(doc_id), status=status)
        db.add(row)
        db.commit()
        return row.id


def test_delete_in_use_409_and_after_withdrawal_204(client, policy):
    uid = as_applicant(client)
    doc = upload(client, "cv", "a.pdf").json()
    app_id = _application(uid, doc["id"])
    r = client.delete("%s/%s" % (URL, doc["id"]))
    assert r.status_code == 409 and r.json()["detail"] == "DOCUMENT_IN_USE"
    assert len(files_on_disk()) == 3
    with engine.begin() as conn:
        conn.execute(text("UPDATE applications SET status = 'withdrawn' WHERE id = :i"), {"i": app_id})
    assert client.delete("%s/%s" % (URL, doc["id"])).status_code == 204
    assert files_on_disk() == set()
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT cv_document_id FROM applications WHERE id = :i"), {"i": app_id}
        ).scalar() is None


def test_purge_user_files_removes_every_file_of_that_user(client, policy):
    uid = as_applicant(client, "budi")
    upload(client, "cv", "a.pdf")
    upload(client, "ktp", "k.png")
    client.post(AUTH + "/logout")
    as_applicant(client, "siti")
    other = upload(client, "cv", "b.pdf").json()
    kept = files_on_disk()
    with Session(engine) as db:
        documents.purge_user_files(db, uuid.UUID(uid))
    assert len(files_on_disk()) == 3 and files_on_disk() < kept
    assert download(client, other["id"]).status_code == 200


def test_delete_account_removes_files(client, policy):
    as_applicant(client)
    upload(client, "cv", "a.pdf")
    upload(client, "ktp", "k.png")
    assert len(files_on_disk()) == 6
    r = client.request("DELETE", "/api/v1/me/account", json={"password": "rahasia123"})
    assert r.status_code == 200
    assert files_on_disk() == set()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM document_copies")).scalar() == 0


# --- no plaintext elsewhere, audit ---------------------------------------------


def test_upload_creates_no_temporary_file(client, policy, monkeypatch):
    def no_temp_files(*args, **kwargs):
        raise AssertionError("plaintext would be spooled to a temporary file")

    for name in ("SpooledTemporaryFile", "TemporaryFile", "NamedTemporaryFile"):
        monkeypatch.setattr("tempfile." + name, no_temp_files)
    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", no_temp_files)
    as_applicant(client)
    content = content_for("a.pdf", os.urandom(3 * MiB))
    doc = upload(client, "cv", "a.pdf", content)
    assert doc.status_code == 201
    assert download(client, doc.json()["id"]).content == content


def test_audit_records_type_and_size_only(client, policy, monkeypatch):
    calls = []
    monkeypatch.setattr(audit, "record", lambda db, **kw: calls.append(kw))
    as_applicant(client)
    doc = upload(client, "cv", "secret-name.pdf").json()
    download(client, doc["id"])
    client.delete("%s/%s" % (URL, doc["id"]))
    calls = [c for c in calls if c["action"].startswith("document.")]
    assert [c["action"] for c in calls] == ["document.upload", "document.download", "document.delete"]
    for c in calls:
        assert c["details"] == {"cv": 1, "size": doc["size"]}
        assert str(c["target_id"]) == doc["id"]
        assert "secret-name" not in repr(c)


def test_nothing_is_logged_or_printed(client, policy, caplog, capsys):
    caplog.set_level("DEBUG")
    as_applicant(client)
    marker = b"plaintext marker 3578012345678901"
    doc = upload(client, "cv", "a.pdf", content_for("a.pdf", marker)).json()
    download(client, doc["id"], "des")
    text_out = " ".join(r.getMessage() for r in caplog.records)
    out = capsys.readouterr()
    assert marker.decode() not in text_out + out.out + out.err


# --- migration ---------------------------------------------------------------


def test_axel_document_migration_upgrade_downgrade_upgrade_on_an_empty_database():
    with empty_database() as (alembic, scalar):
        def state():
            copies = scalar("SELECT to_regclass('document_copies')") is not None
            key = scalar(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'documents' AND column_name = 'storage_key'"
            ) == 1
            return copies, key

        alembic("upgrade", "axel@head")
        assert state() == (True, False)
        alembic("downgrade", "axel_01_encrypted_fields")
        assert state() == (False, True)
        alembic("upgrade", "axel@head")
        assert state() == (True, False)
