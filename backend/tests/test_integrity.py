import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import config, integrity, storage, vault
from app.db import engine
from test_document import CHUNK, MiB, as_applicant, content_for, download, upload
from test_vault import empty_database


@pytest.fixture
def mode(monkeypatch):
    def _set(value):
        monkeypatch.setattr(config, "INTEGRITY_MODE", value)

    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "assignment")
    _set("off")
    return _set


def one(sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).one()


def copy_of(doc_id, alg="aes"):
    return one(
        "SELECT id, storage_key, salt, nonce FROM document_copies WHERE document_id = :d AND algorithm = :a",
        d=doc_id, a=alg,
    )


def read_copy(doc_id, alg="aes"):
    return b"".join(storage.read(copy_of(doc_id, alg).storage_key))


def tamper(doc_id, change, alg="aes"):
    """Replace a copy's stored bytes using only the frozen storage interface (read, write, delete)."""
    old = copy_of(doc_id, alg)
    new_key = storage.write([change(b"".join(storage.read(old.storage_key)))])
    with engine.begin() as conn:
        conn.execute(text("UPDATE document_copies SET storage_key = :k WHERE id = :i"), {"k": new_key, "i": old.id})
    storage.delete(old.storage_key)


def flip_byte(data, at=100):
    return data[:at] + bytes([data[at] ^ 1]) + data[at + 1:]


def video(client, size=9 * MiB):
    content = content_for("v.mp4", os.urandom(size))
    return upload(client, "intro_video", "v.mp4", content).json()["id"], content


def assert_integrity_error(r):
    assert r.status_code == 500 and r.json()["detail"] == "INTEGRITY_ERROR"


# --- normal use --------------------------------------------------------------


@pytest.mark.parametrize("value", ["off", "log-only", "enforce"])
def test_upload_then_download_is_identical_in_every_mode(client, mode, value):
    mode(value)
    as_applicant(client)
    doc_id, content = video(client)
    for alg in ("aes", "des", "rc4"):
        r = download(client, doc_id, alg)
        assert r.status_code == 200 and r.content == content
    assert client.get("/api/v1/me/profile").status_code == 200


def test_every_copy_has_a_tag_per_chunk_and_verifies(client, mode):
    as_applicant(client)
    doc_id, _ = video(client)  # 9 MiB + magic: 3 chunks
    for alg in ("aes", "des", "rc4"):
        c = copy_of(doc_id, alg)
        with engine.connect() as conn:
            tags = [bytes(t) for (t,) in conn.execute(text(
                "SELECT tag FROM integrity_tags WHERE document_copy_id = :i ORDER BY chunk_index"), {"i": c.id})]
        assert len(tags) == 3
        data = read_copy(doc_id, alg)
        chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
        ok, ms = integrity.verify(chunks, tags, alg, "file:%s" % doc_id, bytes(c.salt), c.nonce and bytes(c.nonce))
        assert ok is True and isinstance(ms, float) and ms >= 0


def test_tags_are_written_with_integrity_off(client, mode):
    as_applicant(client)
    doc_id, _ = video(client, 10)
    assert one("SELECT count(*) FROM integrity_tags").count == 3
    assert one("SELECT count(*) FROM encrypted_fields WHERE tag IS NULL").count == 0


# --- tampered files ----------------------------------------------------------


def test_flipped_byte_per_mode(client, mode, caplog):
    as_applicant(client)
    doc_id, content = video(client)
    tamper(doc_id, flip_byte)

    mode("enforce")
    assert_integrity_error(download(client, doc_id))

    mode("log-only")
    caplog.set_level("WARNING", logger="tcancy.integrity")
    r = download(client, doc_id)
    assert r.status_code == 200 and r.content != content and len(r.content) == len(content)
    assert any(rec.name == "tcancy.integrity" for rec in caplog.records)

    mode("off")
    caplog.clear()
    assert download(client, doc_id).status_code == 200
    assert not [rec for rec in caplog.records if rec.name == "tcancy.integrity"]
    # the untouched copies still pass under enforce
    mode("enforce")
    assert download(client, doc_id, "des").content == content


def test_swapped_chunks_are_detected(client, mode):
    as_applicant(client)
    doc_id, _ = video(client)
    tamper(doc_id, lambda d: d[CHUNK:2 * CHUNK] + d[:CHUNK] + d[2 * CHUNK:])
    mode("enforce")
    assert_integrity_error(download(client, doc_id))


def test_chunk_from_another_copy_or_file_is_detected(client, mode):
    as_applicant(client)
    doc_id, _ = video(client)
    other_id, _ = video(client)
    des_chunk = read_copy(doc_id, "des")[:CHUNK]
    other_chunk = read_copy(other_id, "aes")[:CHUNK]
    mode("enforce")
    tamper(doc_id, lambda d: des_chunk + d[CHUNK:])
    assert_integrity_error(download(client, doc_id))
    tamper(other_id, lambda d: d)  # untouched control
    assert download(client, other_id).status_code == 200
    third_id, _ = video(client)
    tamper(third_id, lambda d: other_chunk + d[CHUNK:])
    assert_integrity_error(download(client, third_id))


def test_truncated_or_extended_file_is_detected(client, mode):
    as_applicant(client)
    cut_id, _ = video(client)
    grown_id, _ = video(client)
    extra = read_copy(grown_id)[:CHUNK]
    tamper(cut_id, lambda d: d[:2 * CHUNK])  # drop the last chunk, at a chunk boundary
    tamper(grown_id, lambda d: d + extra)  # append a chunk
    mode("enforce")
    assert_integrity_error(download(client, cut_id))
    assert_integrity_error(download(client, grown_id))


def test_deleted_tag_rows_are_detected(client, mode):
    as_applicant(client)
    doc_id, _ = video(client)
    c = copy_of(doc_id)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM integrity_tags WHERE document_copy_id = :i AND chunk_index = 2"), {"i": c.id})
    mode("enforce")
    assert_integrity_error(download(client, doc_id))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM integrity_tags WHERE document_copy_id = :i"), {"i": c.id})
    assert_integrity_error(download(client, doc_id))


# --- tampered fields ---------------------------------------------------------


def test_tampered_field_fails_load_field_under_enforce(client, mode):
    uid = uuid.UUID(as_applicant(client))
    row = one("SELECT id, ciphertext FROM encrypted_fields WHERE user_id = :u AND field_name = 'nik' "
              "AND algorithm = 'aes'", u=uid)
    with engine.begin() as conn:
        conn.execute(text("UPDATE encrypted_fields SET ciphertext = :c WHERE id = :i"),
                     {"c": flip_byte(bytes(row.ciphertext), 0), "i": row.id})
    mode("enforce")
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc:
            vault.load_field(db, uid, "nik")
        assert exc.value.status_code == 500 and exc.value.detail == "INTEGRITY_ERROR"
        with pytest.raises(HTTPException):
            vault.load_fields(db, [uid], "nik")
        assert vault.load_field(db, uid, "email") is not None  # other fields are fine
    assert_integrity_error(client.get("/api/v1/me/profile"))
    mode("off")
    assert client.get("/api/v1/me/profile").status_code == 200


def test_missing_field_tag_fails_under_enforce(client, mode):
    uid = uuid.UUID(as_applicant(client))
    with engine.begin() as conn:
        conn.execute(text("UPDATE encrypted_fields SET tag = NULL WHERE user_id = :u AND field_name = 'phone'"),
                     {"u": uid})
    mode("enforce")
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc:
            vault.load_field(db, uid, "phone")
        assert exc.value.detail == "INTEGRITY_ERROR"


# --- off checks nothing, logs leak nothing -------------------------------------


def test_off_runs_no_check(client, mode, monkeypatch):
    def no_checks(*args, **kwargs):
        raise AssertionError("integrity checked while INTEGRITY_MODE=off")

    monkeypatch.setattr(integrity, "verify", no_checks)
    as_applicant(client)
    doc_id, content = video(client, 1000)
    tamper(doc_id, flip_byte)
    assert download(client, doc_id).status_code == 200
    assert client.get("/api/v1/me/profile").status_code == 200


def test_integrity_log_holds_no_secrets(client, mode, caplog):
    as_applicant(client)
    marker = b"plaintext marker 3578012345678901 " * 10
    doc_id = upload(client, "cv", "a.pdf", content_for("a.pdf", marker)).json()["id"]
    tamper(doc_id, flip_byte)
    mode("log-only")
    caplog.set_level("DEBUG")
    assert download(client, doc_id).status_code == 200
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert "integrity check failed" in logged
    c = copy_of(doc_id)
    with engine.connect() as conn:
        tags = [bytes(t).hex() for (t,) in conn.execute(
            text("SELECT tag FROM integrity_tags WHERE document_copy_id = :i"), {"i": c.id})]
    secrets = [bytes(c.salt).hex(), bytes(c.nonce).hex(), marker.decode()[:30], *tags]
    for secret in secrets:
        assert secret not in logged


# --- migration ---------------------------------------------------------------


def test_axel_integrity_migration_upgrade_downgrade_upgrade_on_an_empty_database():
    with empty_database() as (alembic, scalar):
        def state():
            tags = scalar("SELECT to_regclass('integrity_tags')") is not None
            column = scalar(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'encrypted_fields' AND column_name = 'tag'"
            ) == 1
            return tags, column

        alembic("upgrade", "axel@head")
        assert state() == (True, True)
        alembic("downgrade", "axel_02_document_copies")
        assert state() == (False, False)
        alembic("upgrade", "axel@head")
        assert state() == (True, True)
