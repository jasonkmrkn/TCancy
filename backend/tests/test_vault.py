import itertools
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, crypto, vault
from app.db import engine
from app.models import User
from helpers import password_hash

BACKEND = Path(__file__).resolve().parents[1]

APPLICANT = {
    "full_name": "Budi Santoso Wicaksono",
    "email": "budi.santoso.vault@example.com",
    "phone": "+6281234567890",
    "nik": "3578012345678901",
    "address": "Jl. Keputih Gang Makam No. 5, Surabaya",
    "birth_date": "2000-05-17",
}

DECRYPT = {"aes": crypto.aes_decrypt, "des": crypto.des_decrypt, "rc4": crypto.rc4_decrypt}


@pytest.fixture
def db():
    with Session(engine) as session:
        yield session


@pytest.fixture
def user(db):
    counter = itertools.count(1)

    def _make():
        u = User(
            username="vault%d_%s" % (next(counter), uuid.uuid4().hex[:6]),
            password_hash=password_hash(), role="applicant", status="active",
        )
        db.add(u)
        db.commit()
        return u.id

    return _make


@pytest.fixture
def policy(monkeypatch):
    def _set(value):
        monkeypatch.setattr(config, "ENCRYPTION_POLICY", value)

    _set("assignment")
    return _set


def rows(user_id, field=None):
    sql = "SELECT field_name, algorithm, salt, nonce, ciphertext FROM encrypted_fields WHERE user_id = :u"
    params = {"u": user_id}
    if field is not None:
        sql += " AND field_name = :f"
        params["f"] = field
    with engine.connect() as conn:
        return {(r.field_name, r.algorithm): r for r in conn.execute(text(sql), params)}


def decrypt(row, user_id):
    item = "%s:%s" % (row.field_name, user_id)
    return DECRYPT[row.algorithm](bytes(row.ciphertext), row.salt, row.nonce, item, 0).decode()


# --- storage -----------------------------------------------------------------


def test_no_plaintext_in_encrypted_fields(db, user, policy):
    uid = user()
    for field, value in APPLICANT.items():
        vault.store_field(db, uid, field, value)
    db.commit()
    stored = rows(uid)
    assert len(stored) == 3 * len(APPLICANT)
    for r in stored.values():
        blob = bytes(r.ciphertext) + bytes(r.salt) + bytes(r.nonce or b"")
        for value in APPLICANT.values():
            assert value.encode() not in blob


def test_assignment_keeps_three_copies_production_one(db, user, policy):
    a, b = user(), user()
    vault.store_field(db, a, "nik", APPLICANT["nik"])
    policy("production")
    vault.store_field(db, b, "nik", APPLICANT["nik"])
    db.commit()
    assert sorted(alg for _, alg in rows(a)) == ["aes", "des", "rc4"]
    assert sorted(alg for _, alg in rows(b)) == ["aes"]
    assert vault.load_field(db, b, "nik") == APPLICANT["nik"]


def test_the_three_copies_decrypt_to_the_same_value(db, user, policy):
    uid = user()
    vault.store_field(db, uid, "address", APPLICANT["address"])
    db.commit()
    stored = rows(uid)
    assert {decrypt(r, uid) for r in stored.values()} == {APPLICANT["address"]}


def test_nonce_and_salt_sizes(db, user, policy):
    uid = user()
    vault.store_field(db, uid, "phone", APPLICANT["phone"])
    db.commit()
    stored = rows(uid)
    assert stored["phone", "rc4"].nonce is None
    assert len(stored["phone", "aes"].nonce) == 8
    assert len(stored["phone", "des"].nonce) == 4
    assert all(len(r.salt) == 16 for r in stored.values())


# --- reads -------------------------------------------------------------------


def test_reads_come_from_aes_also_after_switching_to_production(db, user, policy):
    uid = user()
    vault.store_field(db, uid, "email", "lama.sekali@example.com")
    db.commit()
    policy("production")
    vault.store_field(db, uid, "email", "baru.sekali@example.com")
    db.commit()
    assert vault.load_field(db, uid, "email") == "baru.sekali@example.com"
    stored = rows(uid)
    assert decrypt(stored["email", "aes"], uid) == "baru.sekali@example.com"
    # The des and rc4 copies from the assignment policy are left as they were.
    assert decrypt(stored["email", "des"], uid) == "lama.sekali@example.com"
    assert decrypt(stored["email", "rc4"], uid) == "lama.sekali@example.com"


def test_second_store_replaces_the_old_value(db, user, policy):
    uid = user()
    vault.store_field(db, uid, "full_name", "Nama Pertama Panjang")
    db.commit()
    before = rows(uid)
    vault.store_field(db, uid, "full_name", "Nama Kedua Panjang")
    db.commit()
    after = rows(uid)
    assert vault.load_field(db, uid, "full_name") == "Nama Kedua Panjang"
    assert len(after) == 3
    for key, r in after.items():
        assert decrypt(r, uid) == "Nama Kedua Panjang"
        assert bytes(r.salt) != bytes(before[key].salt)


def test_load_fields_for_many_users(db, user, policy):
    a, b, c = user(), user(), user()
    vault.store_field(db, a, "full_name", "Andi Pratama")
    vault.store_field(db, b, "full_name", "Bunga Lestari")
    vault.store_field(db, c, "phone", "+6289999")
    db.commit()
    assert vault.load_fields(db, [a, b, c], "full_name") == {a: "Andi Pratama", b: "Bunga Lestari"}
    assert vault.load_fields(db, [a, b], "never_stored") == {}
    assert vault.load_fields(db, [], "full_name") == {}
    assert vault.load_field(db, c, "full_name") is None


# --- all or nothing ----------------------------------------------------------


def _boom(*args, **kwargs):
    raise RuntimeError("cipher failed")


@pytest.mark.parametrize("alg", ["des", "rc4"])
def test_failure_in_a_later_copy_writes_nothing(db, user, policy, monkeypatch, alg):
    fresh, existing = user(), user()
    vault.store_field(db, existing, "nik", "1111222233334444")
    db.commit()
    monkeypatch.setitem(vault._ENCRYPT, alg, _boom)
    with pytest.raises(RuntimeError):
        vault.store_field(db, fresh, "nik", APPLICANT["nik"])
    with pytest.raises(RuntimeError):
        vault.store_field(db, existing, "nik", APPLICANT["nik"])
    db.commit()
    assert rows(fresh) == {}
    assert {decrypt(r, existing) for r in rows(existing).values()} == {"1111222233334444"}


def test_failed_flush_rolls_back_every_copy(db, user, policy, monkeypatch):
    fresh, existing = user(), user()
    vault.store_field(db, existing, "nik", "1111222233334444")
    db.commit()
    # A None ciphertext breaks NOT NULL on the last copy, after aes and des were queued.
    monkeypatch.setitem(vault._ENCRYPT, "rc4", lambda *args: None)
    for uid in (fresh, existing):
        with pytest.raises(IntegrityError):
            vault.store_field(db, uid, "nik", APPLICANT["nik"])
    db.commit()  # the caller's transaction is still usable
    assert rows(fresh) == {}
    assert len(rows(existing)) == 3
    assert vault.load_field(db, existing, "nik") == "1111222233334444"


# --- no leaks ----------------------------------------------------------------


def test_nothing_is_logged_or_printed(db, user, policy, caplog, capsys):
    caplog.set_level("DEBUG")
    uid = user()
    vault.store_field(db, uid, "nik", APPLICANT["nik"])
    db.commit()
    vault.load_field(db, uid, "nik")
    vault.load_fields(db, [uid], "nik")
    assert [r for r in caplog.records if r.name.startswith("app")] == []
    out = capsys.readouterr()
    assert APPLICANT["nik"] not in out.out + out.err


# --- migration ---------------------------------------------------------------


def _alembic(url, *args):
    done = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr


def test_axel_migration_upgrade_downgrade_upgrade_on_an_empty_database():
    base = engine.url
    name = base.database.removesuffix("_test") + "_axelmig_test"
    url = base.set(database=name).render_as_string(hide_password=False)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")

    def has_table():
        probe = create_engine(url)
        try:
            with probe.connect() as conn:
                return conn.execute(text("SELECT to_regclass('encrypted_fields')")).scalar() is not None
        finally:
            probe.dispose()

    with admin.connect() as conn:
        conn.execute(text('DROP DATABASE IF EXISTS "%s"' % name))
        conn.execute(text('CREATE DATABASE "%s"' % name))
    try:
        _alembic(url, "upgrade", "axel@head")
        assert has_table()
        _alembic(url, "downgrade", "axel_00_branch_root")
        assert not has_table()
        _alembic(url, "upgrade", "axel@head")
        assert has_table()
    finally:
        with admin.connect() as conn:
            conn.execute(text('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % name))
        admin.dispose()
