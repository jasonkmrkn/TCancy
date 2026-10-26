import os

from sqlalchemy import text

from app import config
from app.db import engine
from helpers import make_alumni_profile, make_profile

AUTH = "/api/v1/auth"
URL = "/api/v1/me/documents"
MiB = 1024 * 1024


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


def upload(client, doc_type, name, content=b"data"):
    return client.post(URL, data={"type": doc_type}, files={"file": (name, content)})


def files_on_disk():
    return set(os.listdir(config.UPLOAD_DIR)) if os.path.isdir(config.UPLOAD_DIR) else set()


def test_upload_then_download_is_identical(client):
    as_applicant(client)
    content = b"%PDF-1.4 hello \x00\x01\x02 world"
    r = upload(client, "cv", "My CV.PDF", content)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "type", "ext", "size", "created_at"}
    assert body["type"] == "cv" and body["ext"] == "pdf" and body["size"] == len(content)

    d = client.get("%s/%s/download" % (URL, body["id"]))
    assert d.status_code == 200
    assert d.content == content
    assert d.headers["content-disposition"].startswith("attachment")
    assert d.headers["content-type"] == "application/pdf"


def test_list_documents(client):
    as_applicant(client)
    assert client.get(URL).json() == []
    a = upload(client, "cv", "a.pdf").json()
    b = upload(client, "intro_video", "v.mp4").json()
    got = client.get(URL).json()
    assert [d["id"] for d in got] == [a["id"], b["id"]]
    assert set(got[0]) == {"id", "type", "ext", "size", "created_at"}


def test_wrong_extension_per_type_415(client):
    as_applicant(client)
    assert upload(client, "cv", "a.png").status_code == 415
    assert upload(client, "cv", "a.docx").status_code == 415
    assert upload(client, "cv", "noext").status_code == 415
    assert upload(client, "intro_video", "a.mov").status_code == 415
    assert upload(client, "ktp", "a.mp4").status_code == 415
    r = upload(client, "cv", "a.png")
    assert r.json()["detail"] == "UNSUPPORTED_FILE_TYPE"
    assert upload(client, "ktp", "a.JPG").status_code == 201
    assert upload(client, "ktp", "a.png").status_code == 201
    assert upload(client, "ktp", "a.pdf").status_code == 201


def test_content_is_not_inspected(client):
    as_applicant(client)
    assert upload(client, "cv", "fake.pdf", b"not really a pdf").status_code == 201


def test_unknown_type_422(client):
    as_applicant(client)
    assert upload(client, "passport", "a.pdf").status_code == 422
    assert client.post(URL, files={"file": ("a.pdf", b"x")}).status_code == 422


def test_empty_file_400(client):
    as_applicant(client)
    r = upload(client, "cv", "a.pdf", b"")
    assert r.status_code == 400
    assert r.json()["detail"] == "EMPTY_FILE"


def test_size_limits_413(client):
    as_applicant(client)
    assert upload(client, "cv", "a.pdf", b"x" * (5 * MiB + 1)).status_code == 413
    assert upload(client, "ktp", "a.png", b"x" * (5 * MiB + 1)).status_code == 413
    assert upload(client, "intro_video", "a.mp4", b"x" * (50 * MiB + 1)).status_code == 413
    r = upload(client, "cv", "a.pdf", b"x" * (5 * MiB + 1))
    assert r.json()["detail"] == "FILE_TOO_LARGE"
    assert upload(client, "cv", "a.pdf", b"x" * (5 * MiB)).status_code == 201
    assert upload(client, "intro_video", "a.mp4", b"x" * (6 * MiB)).status_code == 201
    assert client.get(URL).json().__len__() == 2


def test_limit_five_per_type_409(client):
    as_applicant(client)
    for i in range(5):
        assert upload(client, "cv", "c%d.pdf" % i).status_code == 201
    r = upload(client, "cv", "c6.pdf")
    assert r.status_code == 409
    assert r.json()["detail"] == "DOCUMENT_LIMIT"
    # other types are counted separately
    assert upload(client, "intro_video", "v.mp4").status_code == 201


def test_new_ktp_replaces_old(client):
    as_applicant(client)
    first = upload(client, "ktp", "a.jpg", b"one").json()
    before = files_on_disk()
    second = upload(client, "ktp", "b.png", b"two").json()
    docs = client.get(URL).json()
    assert [d["id"] for d in docs] == [second["id"]]
    assert client.get("%s/%s/download" % (URL, first["id"])).status_code == 404
    assert client.get("%s/%s/download" % (URL, second["id"])).content == b"two"
    assert len(files_on_disk()) == len(before)


def test_other_users_document_is_404(client):
    as_applicant(client, "budi")
    doc = upload(client, "cv", "a.pdf").json()
    client.post(AUTH + "/logout")
    as_applicant(client, "siti")
    r = client.get("%s/%s/download" % (URL, doc["id"]))
    assert r.status_code == 404 and r.json()["detail"] == "DOCUMENT_NOT_FOUND"
    r = client.delete("%s/%s" % (URL, doc["id"]))
    assert r.status_code == 404 and r.json()["detail"] == "DOCUMENT_NOT_FOUND"
    assert client.get(URL).json() == []
    login(client, "budi")
    assert client.get("%s/%s/download" % (URL, doc["id"])).status_code == 200


def test_unknown_or_malformed_id_404(client):
    as_applicant(client)
    assert client.get(URL + "/not-a-uuid/download").status_code == 404
    assert client.delete(URL + "/00000000-0000-0000-0000-000000000000").status_code == 404


def test_delete_removes_row_and_file(client):
    as_applicant(client)
    doc = upload(client, "cv", "a.pdf").json()
    assert len(files_on_disk()) == 1
    r = client.delete("%s/%s" % (URL, doc["id"]))
    assert r.status_code == 204
    assert client.get(URL).json() == []
    assert files_on_disk() == set()


def test_requires_login_and_applicant_role(client):
    assert client.get(URL).status_code == 401
    assert upload(client, "cv", "a.pdf").status_code == 401
    client.post(
        AUTH + "/register/alumni",
        json={"username": "alumna", "password": "rahasia123", "profile": make_alumni_profile()},
    )
    login(client, "alumna")
    assert client.get(URL).status_code == 403  # pending alumni
    assert upload(client, "cv", "a.pdf").status_code == 403


def test_delete_account_removes_files(client):
    as_applicant(client)
    upload(client, "cv", "a.pdf")
    upload(client, "ktp", "k.png")
    assert len(files_on_disk()) == 2
    r = client.request("DELETE", "/api/v1/me/account", json={"password": "rahasia123"})
    assert r.status_code == 200
    assert files_on_disk() == set()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() == 0
