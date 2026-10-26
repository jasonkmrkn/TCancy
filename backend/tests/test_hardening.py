"""Hardening checks across the Axel modules (crypto, vault, documents, integrity, analysis).

Fills the gaps the per-module test files leave: limits at their exact edges, policy switches both
ways, tampering with every copy, extreme inputs, leaks through logs, responses, the database and
the disk, clean-up after failures and aborted uploads, and the whole axel migration branch.
"""
import asyncio
import inspect
import io
import os
import subprocess
import sys
import tempfile
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import analysis, benchmarks, config, crypto, documents, integrity, vault
from app.db import engine
from app.main import app
from app.models import Base
from app.routers import admin_benchmarks as admin_benchmarks_router
from app.routers import analysis as analysis_router
from app.routers import documents as documents_router
from helpers import make_profile
from test_analysis import ADMIN, a_pdf, bench, ciphertext
from test_document import CHUNK, MAGIC, MiB, URL, as_applicant, content_for, download, files_on_disk, upload
from test_integrity import assert_integrity_error, copy_of, flip_byte, read_copy, tamper
from test_job import as_user
from test_vault import BACKEND, empty_database

API = "/api/v1"


@pytest.fixture(autouse=True)
def modes(monkeypatch):
    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "assignment")
    monkeypatch.setattr(config, "INTEGRITY_MODE", "off")


def scalar(sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def video(client, size=9 * MiB):
    content = content_for("v.mp4", os.urandom(size))
    return upload(client, "intro_video", "v.mp4", content).json()["id"], content


# --- 1. limits at their exact edges ----------------------------------------------


def test_ktp_size_edge(client):
    as_applicant(client)
    exact = content_for("k.png", b"x" * (5 * MiB - len(MAGIC["png"])))
    assert upload(client, "ktp", "k.png", exact).status_code == 201
    over = content_for("k.png", b"x" * (5 * MiB + 1 - len(MAGIC["png"])))
    r = upload(client, "ktp", "k.png", over)
    assert r.status_code == 413 and r.json()["detail"] == "FILE_TOO_LARGE"


def test_intro_video_exactly_50_mib_is_accepted(client):
    as_applicant(client)
    content = content_for("v.mp4", os.urandom(50 * MiB - len(MAGIC["mp4"])))
    r = upload(client, "intro_video", "v.mp4", content)
    assert r.status_code == 201 and r.json()["size"] == 50 * MiB
    assert download(client, r.json()["id"], "rc4").content == content


# --- 2. production policy, both ways -------------------------------------------------


def test_policy_switch_to_production_and_back(client, monkeypatch):
    uid = uuid.UUID(as_applicant(client))
    old_id = a_pdf(client, b"assignment era " * 300)
    old_content = download(client, old_id).content
    nik = client.get(API + "/me/profile").json()["nik"]

    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "production")
    assert download(client, old_id).content == old_content
    for alg in ("des", "rc4"):
        r = download(client, old_id, alg)
        assert r.status_code == 404 and r.json()["detail"] == "DOCUMENT_NOT_FOUND"
    assert [c["algorithm"] for c in ciphertext(client, old_id).json()["copies"]] == ["aes"]
    assert [x["algorithm"] for x in bench(client, old_id, {"repeats": 1}).json()["results"]] == ["aes"]
    assert client.get(API + "/me/profile").json()["nik"] == nik  # vault data from assignment still reads
    new_id = a_pdf(client, b"production era " * 300)
    # the old des/rc4 copies are kept on disk and in the database
    assert scalar("SELECT count(*) FROM document_copies WHERE document_id = :d", d=old_id) == 3

    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "assignment")
    for alg in ("aes", "des", "rc4"):
        assert download(client, old_id, alg).content == old_content
    assert download(client, new_id).status_code == 200
    assert download(client, new_id, "des").status_code == 404  # never had a des copy
    assert len(ciphertext(client, old_id).json()["copies"]) == 3
    with Session(engine) as db:
        vault.store_field(db, uid, "nik", "3578000011112222")
        db.commit()
        assert vault.load_field(db, uid, "nik") == "3578000011112222"
    rows = scalar("SELECT count(*) FROM encrypted_fields WHERE user_id = :u AND field_name = 'nik'", u=uid)
    assert rows == 3


# --- 3. tampering with every copy (enforce) -----------------------------------------


@pytest.mark.parametrize("alg", ["aes", "des", "rc4"])
def test_tampering_with_any_copy_is_detected(client, monkeypatch, alg):
    as_applicant(client)
    doc_id, content = video(client)  # 3 chunks
    original = read_copy(doc_id, alg)
    monkeypatch.setattr(config, "INTEGRITY_MODE", "enforce")
    changes = {
        "flip": flip_byte,
        "swap": lambda d: d[CHUNK:2 * CHUNK] + d[:CHUNK] + d[2 * CHUNK:],
        "truncate": lambda d: d[:2 * CHUNK],
        "extend": lambda d: d + d[:CHUNK],
    }
    for name, change in changes.items():
        tamper(doc_id, change, alg)
        assert_integrity_error(download(client, doc_id, alg))
        tamper(doc_id, lambda _: original, alg)
        assert download(client, doc_id, alg).content == content, name
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM integrity_tags WHERE document_copy_id = :i"), {"i": copy_of(doc_id, alg).id})
    assert_integrity_error(download(client, doc_id, alg))


def test_tampered_fields_are_detected(client, monkeypatch):
    a = uuid.UUID(as_applicant(client, "budi"))
    client.post(API + "/auth/logout")
    b = uuid.UUID(as_applicant(client, "siti"))

    def row(user, alg="aes"):
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT id, salt, nonce, ciphertext, tag FROM encrypted_fields "
                "WHERE user_id = :u AND field_name = 'nik' AND algorithm = :a"), {"u": user, "a": alg}).one()

    def set_row(row_id, salt, nonce, ct, tag):
        with engine.begin() as conn:
            conn.execute(text("UPDATE encrypted_fields SET salt = :s, nonce = :n, ciphertext = :c, tag = :t "
                              "WHERE id = :i"), {"s": salt, "n": nonce, "c": ct, "t": tag, "i": row_id})

    mine, theirs, my_des = row(a), row(b), row(a, "des")
    ct = bytes(mine.ciphertext)
    forgeries = {
        "truncate": (mine.salt, mine.nonce, ct[:-1], mine.tag),
        "append": (mine.salt, mine.nonce, ct + b"\x00", mine.tag),
        "another user's row": (theirs.salt, theirs.nonce, theirs.ciphertext, theirs.tag),
        "the des copy": (my_des.salt, my_des.nonce, my_des.ciphertext, my_des.tag),
    }
    monkeypatch.setattr(config, "INTEGRITY_MODE", "enforce")
    with Session(engine) as db:
        for name, values in forgeries.items():
            set_row(mine.id, *values)
            db.expire_all()
            with pytest.raises(HTTPException) as exc:
                vault.load_field(db, a, "nik")
            assert exc.value.detail == "INTEGRITY_ERROR", name
        set_row(mine.id, mine.salt, mine.nonce, mine.ciphertext, mine.tag)
        db.expire_all()
        assert vault.load_field(db, a, "nik") is not None


# --- 4. extreme inputs ------------------------------------------------------------


@pytest.mark.parametrize("repeats", [-1, None, 10**30])
def test_more_bad_repeats_422(client, repeats):
    as_applicant(client)
    doc_id = a_pdf(client)
    assert bench(client, doc_id, {"repeats": repeats}).status_code == 422


@pytest.mark.parametrize("n", [-1, 0, "a", 10**30])
def test_more_bad_preview_bytes_422(client, n):
    as_applicant(client)
    doc_id = a_pdf(client)
    assert ciphertext(client, doc_id, n).status_code == 422


def test_empty_benchmark_body_uses_the_default(client):
    as_applicant(client)
    doc_id = a_pdf(client, b"x" * 10)
    assert bench(client, doc_id, {}).json()["repeats"] == 5
    r = client.post("%s/me/documents/%s/benchmark" % (API, doc_id))
    assert r.status_code == 200 and r.json()["repeats"] == 5


@pytest.mark.parametrize("sizes", [["a"], [None], "1024"])
def test_more_bad_admin_sizes_422(client, sizes):
    as_user(client, "root", "admin")
    assert client.post(ADMIN + "/run", json={"sizes": sizes}).status_code == 422


# --- 5. crypto ----------------------------------------------------------------------


def test_every_copy_of_every_upload_gets_fresh_salt_and_nonce(client):
    as_applicant(client)
    content = content_for("a.pdf", b"same file " * 200)
    first = upload(client, "cv", "a.pdf", content).json()["id"]
    second = upload(client, "cv", "a.pdf", content).json()["id"]
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT algorithm, salt, nonce FROM document_copies WHERE document_id IN (:a, :b)"),
                            {"a": first, "b": second}).all()
    assert len(rows) == 6
    assert len({bytes(r.salt) for r in rows}) == 6
    nonces = [bytes(r.nonce) for r in rows if r.nonce is not None]
    assert len(nonces) == 4 and len(set(nonces)) == 4
    assert read_copy(first) != read_copy(second)


AXEL_MODULES = [crypto, vault, integrity, documents, analysis, benchmarks,
                documents_router, analysis_router, admin_benchmarks_router]


@pytest.mark.parametrize("module", AXEL_MODULES, ids=lambda m: m.__name__)
def test_no_ecb_in_any_axel_module(module):
    assert "MODE_ECB" not in inspect.getsource(module)


# --- 6. no leaks through logs, responses, the database or the disk ---------------------


PERSONAL = {
    "full_name": "Zebulon Quixotic",
    "email": "zebulon.quixotic@example.com",
    "phone": "+628987654321",
    "nik": "3578099988877766",
    "address": "Jalan Rahasia Nomor Tujuh",
    "birth_date": "1999-12-31",
}


def test_secrets_stay_out_of_logs_and_responses(client, monkeypatch, caplog):
    caplog.set_level("DEBUG")
    responses = {}
    r = client.post(API + "/auth/register",
                    json={"username": "zeb", "password": "rahasia123", "profile": make_profile(**PERSONAL)})
    assert r.status_code == 201
    uid = r.json()["id"]
    client.post(API + "/auth/login", json={"username": "zeb", "password": "rahasia123"})
    marker = b"plaintext marker 3578099988877766 " * 40
    up = upload(client, "cv", "a.pdf", content_for("a.pdf", marker))
    doc_id = up.json()["id"]
    responses["upload"] = up.text
    responses["list"] = client.get(URL).text
    for alg in ("aes", "des", "rc4"):
        download(client, doc_id, alg)
    client.get(API + "/me/profile")
    ciphertext_text = ciphertext(client, doc_id, 128).text
    responses["benchmark"] = bench(client, doc_id, {"repeats": 1}).text
    monkeypatch.setattr(config, "INTEGRITY_MODE", "log-only")
    tamper(doc_id, flip_byte)
    download(client, doc_id)  # integrity failure, logged
    client.post(API + "/auth/logout")
    as_user(client, "root", "admin")
    responses["admin run"] = client.post(ADMIN + "/run", json={"sizes": [64], "repeats": 1}).text
    responses["admin summary"] = client.get(ADMIN).text

    salts, nonces, tags, keys = [], [], [], []
    with engine.connect() as conn:
        for alg, salt, nonce in conn.execute(text(
                "SELECT algorithm, salt, nonce FROM document_copies WHERE document_id = :d"), {"d": doc_id}):
            salts.append(bytes(salt).hex())
            if nonce:
                nonces.append(bytes(nonce).hex())
            keys.append(crypto.derive_key(bytes(salt), "%s:file:%s" % (alg, doc_id), crypto.KEY_BYTES[alg]).hex())
            keys.append(crypto.derive_key(bytes(salt), "mac:%s:file:%s" % (alg, doc_id), 32).hex())
        for salt, nonce, tag in conn.execute(text(
                "SELECT salt, nonce, tag FROM encrypted_fields WHERE user_id = :u"), {"u": uid}):
            salts.append(bytes(salt).hex())
            tags.append(bytes(tag).hex())
            if nonce:
                nonces.append(bytes(nonce).hex())
        tags += [bytes(t).hex() for (t,) in conn.execute(text("SELECT tag FROM integrity_tags"))]

    logged = "\n".join(rec.getMessage() for rec in caplog.records).lower()
    assert "integrity check failed" in logged
    for secret in salts + nonces + tags + keys + [marker.decode()[:30].lower()]:
        assert secret not in logged
    for value in PERSONAL.values():
        assert value.lower() not in logged
    for name, body in {**responses, "ciphertext": ciphertext_text}.items():
        for secret in salts + keys + tags:
            assert secret not in body.lower(), name
    for name, body in responses.items():  # the nonce is shown only by the ciphertext endpoint
        for nonce in nonces:
            assert nonce not in body.lower(), name


def test_no_plain_personal_data_in_any_table_or_file(client):
    r = client.post(API + "/auth/register",
                    json={"username": "zeb", "password": "rahasia123", "profile": make_profile(**PERSONAL)})
    assert r.status_code == 201
    client.post(API + "/auth/login", json={"username": "zeb", "password": "rahasia123"})
    marker = b"plaintext marker zebulon " * 40
    upload(client, "cv", "a.pdf", content_for("a.pdf", marker))
    upload(client, "ktp", "k.png", content_for("k.png", marker))
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for row in conn.execute(select(table)):
                for column, value in zip(table.columns, row):
                    if value is None:
                        continue
                    blob = bytes(value) if isinstance(value, (bytes, memoryview)) else str(value).encode()
                    for name, plain in PERSONAL.items():
                        assert plain.encode() not in blob, "%s.%s holds %s" % (table.name, column.name, name)
    for path in files_on_disk():
        with open(os.path.join(config.UPLOAD_DIR, path), "rb") as f:
            data = f.read()
        assert marker[:20] not in data
        assert not any(data.startswith(m) for m in MAGIC.values())


# --- 7. failures and clean-up -------------------------------------------------------


def copy_and_tag_rows(doc_id):
    return (
        scalar("SELECT count(*) FROM document_copies WHERE document_id = :d", d=doc_id),
        scalar("SELECT count(*) FROM integrity_tags t JOIN document_copies c ON c.id = t.document_copy_id "
               "WHERE c.document_id = :d", d=doc_id),
    )


def test_delete_replace_and_account_removal_leave_no_copies_tags_or_files(client):
    as_applicant(client)
    doc_id = a_pdf(client)
    assert copy_and_tag_rows(doc_id) == (3, 3)
    assert client.delete("%s/%s" % (URL, doc_id)).status_code == 204
    assert copy_and_tag_rows(doc_id) == (0, 0) and files_on_disk() == set()

    old_ktp = upload(client, "ktp", "k.png").json()["id"]
    new_ktp = upload(client, "ktp", "k.jpg").json()["id"]
    assert copy_and_tag_rows(old_ktp) == (0, 0) and copy_and_tag_rows(new_ktp) == (3, 3)
    assert len(files_on_disk()) == 3

    a_pdf(client)
    assert client.request("DELETE", API + "/me/account", json={"password": "rahasia123"}).status_code == 200
    assert scalar("SELECT count(*) FROM document_copies") == 0
    assert scalar("SELECT count(*) FROM integrity_tags") == 0
    assert files_on_disk() == set()


@pytest.fixture
def clean_tempdir(monkeypatch, tmp_path):
    folder = tmp_path / "temp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def no_leftovers(clean_tempdir):
    assert not [p for p in files_on_disk() if p.endswith(".tmp")]
    assert list(clean_tempdir.iterdir()) == []


def test_no_temporary_files_after_success_or_failure(client, monkeypatch, clean_tempdir):
    uid = uuid.UUID(as_applicant(client))
    assert upload(client, "cv", "a.pdf", content_for("a.pdf", os.urandom(3 * MiB))).status_code == 201
    no_leftovers(clean_tempdir)
    assert upload(client, "cv", "a.pdf", content_for("a.pdf", b"x" * (5 * MiB))).status_code == 413
    no_leftovers(clean_tempdir)

    def boom(*args):
        raise RuntimeError("cipher failed")

    monkeypatch.setitem(documents._ENCRYPT, "rc4", boom)
    with Session(engine) as db:
        with pytest.raises(RuntimeError):
            documents.put(db, uid, "cv", None, io.BytesIO(content_for("a.pdf", os.urandom(MiB))))
    no_leftovers(clean_tempdir)
    assert scalar("SELECT count(*) FROM documents") == 1 and len(files_on_disk()) == 3


def test_aborted_upload_leaves_nothing(client, clean_tempdir, monkeypatch):
    as_applicant(client)
    writes = []
    real_write = documents.storage.write

    def counting_write(chunks):
        writes.append(1)
        return real_write(chunks)

    monkeypatch.setattr(documents.storage, "write", counting_write)
    cookies = {c.name: c.value for c in client.cookies.jar}
    opening = (
        b"--XB\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ncv\r\n"
        b"--XB\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.pdf\"\r\n"
        b"Content-Type: application/pdf\r\n\r\n" + MAGIC["pdf"]
    )
    # More than one 4 MiB chunk, so the aes copy is already being written when the client goes away.
    pieces = [opening] + [os.urandom(MiB)] * 6
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": URL, "raw_path": URL.encode(), "query_string": b"",
        "root_path": "", "server": ("testserver", 80), "client": ("1.2.3.4", 1),
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"multipart/form-data; boundary=XB"),
            (b"cookie", "; ".join("%s=%s" % kv for kv in cookies.items()).encode()),
            (b"x-csrf-token", cookies["csrf_token"].encode()),
        ],
    }
    sent = iter(pieces)

    async def receive():
        piece = next(sent, None)
        if piece is None:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": piece, "more_body": True}

    async def send(message):
        pass

    try:
        asyncio.run(app(scope, receive, send))
    except Exception:
        pass  # the disconnect may surface here; only the clean-up matters
    assert writes, "the upload never reached storage, so clean-up was not exercised"
    assert scalar("SELECT count(*) FROM documents") == 0
    assert scalar("SELECT count(*) FROM document_copies") == 0
    assert files_on_disk() == set()
    no_leftovers(clean_tempdir)


# --- 9. the whole axel migration branch ------------------------------------------------


def test_whole_axel_branch_and_all_heads_on_an_empty_database():
    heads = subprocess.run([sys.executable, "-m", "alembic", "heads"], cwd=BACKEND,
                           capture_output=True, text=True, check=True).stdout
    assert len([line for line in heads.splitlines() if "(axel)" in line]) == 1

    with empty_database() as (alembic, scalar_in):
        def objects():
            def table(name):
                return scalar_in("SELECT to_regclass('%s')" % name) is not None

            def column(tbl, col):
                return scalar_in("SELECT count(*) FROM information_schema.columns "
                                 "WHERE table_name = '%s' AND column_name = '%s'" % (tbl, col)) == 1

            return {
                "encrypted_fields": table("encrypted_fields"),
                "encrypted_fields.tag": column("encrypted_fields", "tag"),
                "document_copies": table("document_copies"),
                "integrity_tags": table("integrity_tags"),
                "crypto_benchmarks": table("crypto_benchmarks"),
                "documents.storage_key": column("documents", "storage_key"),
            }

        at_head = {
            "encrypted_fields": True, "encrypted_fields.tag": True, "document_copies": True,
            "integrity_tags": True, "crypto_benchmarks": True, "documents.storage_key": False,
        }
        at_root = {k: not v for k, v in at_head.items()}

        alembic("upgrade", "axel@head")
        assert objects() == at_head
        alembic("downgrade", "axel_00_branch_root")
        assert objects() == at_root
        alembic("upgrade", "axel@head")
        assert objects() == at_head

        alembic("upgrade", "heads")
        alembic("downgrade", "base")
        assert scalar_in("SELECT to_regclass('users')") is None
        alembic("upgrade", "heads")
        assert objects() == at_head
