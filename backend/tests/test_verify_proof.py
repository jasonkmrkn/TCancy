"""A2 V2 (Axel): encrypted copies of the alumni verification proof and /me/verification-proof."""
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, crypto, documents, filetype, proof_purge, storage
from app.db import engine
from app.models import VerificationProof, VerificationProofCopy
from app.routers import verify_proof
from test_document import disk_bytes, files_on_disk
from test_job import login, make_user

URL = "/api/v1/me/verification-proof"
MiB = 1024 * 1024
CHUNK = crypto.CHUNK_SIZE
MAGIC = {"pdf": b"%PDF-1.7\n", "jpg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00", "png": b"\x89PNG\r\n\x1a\n"}


def proof_bytes(size, ext="pdf"):
    head = MAGIC[ext]
    body = bytes((i * 7 + 3) % 251 for i in range(min(size, 4096) - len(head)))
    data = head + body
    return (data * (size // len(data) + 1))[:size]


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "assignment")
    calls = []

    def fake_close(db, alumni_id, reason):
        calls.append((alumni_id, reason))
        return []

    monkeypatch.setattr(proof_purge, "close_grants_for_alumni", fake_close, raising=False)
    return calls


def as_alumni(client, username="sari", status="pending"):
    uid = make_user(client, username, "alumni", status)
    login(client, username)
    return uuid.UUID(uid)


def upload(client, content, name="bukti.pdf"):
    return client.post(URL, files={"file": (name, content)})


def rows(alumni_id):
    with Session(engine) as db:
        proofs = list(db.scalars(select(VerificationProof).where(VerificationProof.alumni_id == alumni_id)))
        copies = list(db.scalars(select(VerificationProofCopy)))
        return proofs, copies


def read_back(alumni_id):
    with Session(engine) as db:
        _, pieces = verify_proof.open_proof(db, alumni_id)
    return b"".join(pieces)


# --- access ----------------------------------------------------------------------------


def test_pending_alumni_can_upload(client):
    as_alumni(client)
    r = upload(client, proof_bytes(100))
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"ext", "size", "sha256", "created_at"}
    assert body["ext"] == "pdf" and body["size"] == 100


@pytest.mark.parametrize("role", ["applicant", "admin"])
def test_other_roles_are_403(client, role):
    make_user(client, "other" + role, role)
    login(client, "other" + role)
    assert upload(client, proof_bytes(100)).status_code == 403
    assert client.get(URL).status_code == 403
    assert client.delete(URL).status_code == 403


def test_not_logged_in_is_401(client):
    assert client.get(URL).status_code == 401


# --- file checks -----------------------------------------------------------------------


@pytest.mark.parametrize("ext", ["pdf", "jpg", "png"])
def test_pdf_jpg_png_are_201(client, ext):
    as_alumni(client)
    r = upload(client, proof_bytes(500, ext), "bukti." + ext)
    assert r.status_code == 201 and r.json()["ext"] == ext


@pytest.mark.parametrize("content", [b"\x00\x00\x00\x18ftypisom" + b"x" * 50, b"just some text here"])
def test_other_types_are_415(client, content):
    as_alumni(client)
    r = upload(client, content)
    assert (r.status_code, r.json()["detail"]) == (415, "UNSUPPORTED_FILE_TYPE")
    assert files_on_disk() == set()


def test_over_5_mib_is_413_and_leaves_nothing(client):
    uid = as_alumni(client)
    r = upload(client, proof_bytes(config.PROOF_MAX_BYTES + 1))
    assert (r.status_code, r.json()["detail"]) == (413, "FILE_TOO_LARGE")
    assert files_on_disk() == set() and rows(uid) == ([], [])


def test_empty_is_400(client):
    as_alumni(client)
    r = upload(client, b"")
    assert (r.status_code, r.json()["detail"]) == (400, "EMPTY_FILE")


# --- GET / DELETE / re-upload ----------------------------------------------------------


def test_get_and_delete_are_404_before_upload(client):
    as_alumni(client)
    assert (client.get(URL).status_code, client.get(URL).json()["detail"]) == (404, "PROOF_NOT_FOUND")
    r = client.delete(URL)
    assert (r.status_code, r.json()["detail"]) == (404, "PROOF_NOT_FOUND")


def test_get_shows_metadata_and_delete_removes_everything(client, setup):
    uid = as_alumni(client)
    meta = upload(client, proof_bytes(1000)).json()
    assert client.get(URL).json() == meta
    assert len(files_on_disk()) == 3
    assert client.delete(URL).status_code == 204
    assert client.get(URL).status_code == 404
    assert files_on_disk() == set() and rows(uid) == ([], [])
    assert setup == [(uid, "proof_deleted")]


def test_reupload_replaces_the_old_proof(client, setup):
    uid = as_alumni(client)
    upload(client, proof_bytes(1000))
    old_files = files_on_disk()
    (old,), _ = rows(uid)
    new = upload(client, proof_bytes(2000, "png"), "b.png").json()
    (proof,), copies = rows(uid)
    assert proof.id != old.id and new["ext"] == "png" and new["size"] == 2000
    assert {c.proof_id for c in copies} == {proof.id} and len(copies) == 3
    assert not (files_on_disk() & old_files) and len(files_on_disk()) == 3
    assert client.get(URL).json() == new
    assert setup == [(uid, "proof_replaced")]


def test_first_upload_does_not_close_grants(client, setup):
    as_alumni(client)
    upload(client, proof_bytes(100))
    assert setup == []


def test_other_alumni_cannot_see_or_delete(client):
    owner = as_alumni(client, "sari")
    upload(client, proof_bytes(100))
    client.post("/api/v1/auth/logout")
    as_alumni(client, "dewi")
    assert client.get(URL).status_code == 404
    assert client.delete(URL).status_code == 404
    assert len(rows(owner)[0]) == 1 and len(files_on_disk()) == 3


# --- crypto ----------------------------------------------------------------------------


@pytest.mark.parametrize("size", [CHUNK - 1, CHUNK, CHUNK + 1, config.PROOF_MAX_BYTES])
def test_read_back_is_identical(client, size):
    uid = as_alumni(client)
    data = proof_bytes(size)
    assert upload(client, data).status_code == 201
    assert read_back(uid) == data


def test_one_byte_proof_reads_back(client, monkeypatch):
    # 1 byte cannot pass the PDF signature check, so let the type check accept it.
    monkeypatch.setattr(filetype, "detect", lambda head, kind: "pdf")
    uid = as_alumni(client)
    assert upload(client, b"%").status_code == 201
    assert read_back(uid) == b"%"


def test_disk_holds_no_plaintext_and_copies_match(client):
    uid = as_alumni(client)
    data = proof_bytes(CHUNK + 10)
    upload(client, data)
    for blob in disk_bytes():
        assert len(blob) == len(data) and blob != data and data[100:164] not in blob
    _, copies = rows(uid)
    assert {c.algorithm for c in copies} == {"aes", "des", "rc4"}
    (proof,), _ = rows(uid)
    for c in copies:
        assert c.chunk_size == CHUNK and c.ciphertext_size == len(data)
        plain = b"".join(documents._decrypt(storage.read(c.storage_key), c.algorithm, c.salt, c.nonce,
                                            "proof:%s" % proof.id))
        assert plain == data


def test_production_keeps_only_aes(client, monkeypatch):
    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "production")
    uid = as_alumni(client)
    data = proof_bytes(5000)
    upload(client, data)
    _, copies = rows(uid)
    assert [c.algorithm for c in copies] == ["aes"] and len(files_on_disk()) == 1
    assert read_back(uid) == data


@pytest.mark.parametrize("alg", ["des", "rc4"])
def test_failing_later_copy_leaves_nothing(client, monkeypatch, alg):
    def boom(*a):
        raise storage.StorageError("disk full")

    monkeypatch.setitem(documents._ENCRYPT, alg, boom)
    uid = as_alumni(client)
    r = upload(client, proof_bytes(1000))
    assert (r.status_code, r.json()["detail"]) == (500, "STORAGE_ERROR")
    assert files_on_disk() == set() and rows(uid) == ([], [])


def test_failing_reupload_keeps_the_old_proof(client, monkeypatch):
    uid = as_alumni(client)
    data = proof_bytes(1000)
    upload(client, data)
    before = files_on_disk()

    def boom(*a):
        raise storage.StorageError("disk full")

    monkeypatch.setitem(documents._ENCRYPT, "rc4", boom)
    assert upload(client, proof_bytes(2000)).status_code == 500
    assert files_on_disk() == before and read_back(uid) == data


def test_tampered_aes_copy_is_integrity_error(client):
    uid = as_alumni(client)
    upload(client, proof_bytes(1000))
    _, copies = rows(uid)
    aes = next(c for c in copies if c.algorithm == "aes")
    path = next(p for p in files_on_disk() if p.endswith(aes.storage_key))
    full = os.path.join(config.UPLOAD_DIR, path)
    blob = bytearray(open(full, "rb").read())
    blob[500] ^= 1
    open(full, "wb").write(bytes(blob))
    with Session(engine) as db, pytest.raises(HTTPException) as e:
        verify_proof.open_proof(db, uid)
    assert (e.value.status_code, e.value.detail) == (500, "INTEGRITY_ERROR")


def test_open_proof_404_without_proof(client):
    uid = as_alumni(client)
    with Session(engine) as db, pytest.raises(HTTPException) as e:
        verify_proof.open_proof(db, uid)
    assert (e.value.status_code, e.value.detail) == (404, "PROOF_NOT_FOUND")
