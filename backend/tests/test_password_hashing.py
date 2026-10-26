from argon2 import PasswordHasher
from sqlalchemy import text

from app import cli, security
from app.db import engine
from helpers import make_alumni_profile, make_profile

AUTH = "/api/v1/auth"

WEAK = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


def register(client, username="budi", password="rahasia123"):
    r = client.post(
        AUTH + "/register",
        json={"username": username, "password": password, "profile": make_profile()},
    )
    assert r.status_code == 201
    return r


def login(client, username="budi", password="rahasia123"):
    return client.post(AUTH + "/login", json={"username": username, "password": password})


def stored_hash(username="budi"):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT password_hash FROM users WHERE username = :u"), {"u": username}
        ).scalar_one()


def set_hash(value, username="budi"):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET password_hash = :h WHERE username = :u"),
            {"h": value, "u": username},
        )


# --- storage -----------------------------------------------------------------


def test_password_is_stored_as_argon2id_hash(client):
    register(client)
    h = stored_hash()
    assert h.startswith("$argon2id$")
    assert "rahasia123" not in h
    assert security.verify_password(h, "rahasia123")
    assert not security.verify_password(h, "rahasia124")


def test_alumni_registration_also_hashes(client):
    client.post(
        AUTH + "/register/alumni",
        json={"username": "alum", "password": "rahasia123", "profile": make_alumni_profile()},
    )
    assert stored_hash("alum").startswith("$argon2id$")


def test_same_password_gets_different_hashes(client):
    register(client, "budi")
    register(client, "ani")
    assert stored_hash("budi") != stored_hash("ani")  # random salt per hash


def test_plaintext_column_is_gone():
    with engine.connect() as conn:
        cols = set(conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
        )).scalars())
    assert "password_hash" in cols
    assert "password" not in cols


def test_cli_create_admin_stores_hash(client):
    cli.create_admin("boss", "secret-pass")
    h = stored_hash("boss")
    assert h.startswith("$argon2id$") and "secret-pass" not in h
    assert login(client, "boss", "secret-pass").status_code == 200


# --- login -------------------------------------------------------------------


def test_login_correct_and_wrong_password(client):
    register(client)
    assert login(client).status_code == 200
    client.cookies.clear()
    r = login(client, password="salahsalah")
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid username or password"
    assert "set-cookie" not in r.headers


def test_unknown_username_response_equals_wrong_password(client):
    register(client)
    wrong = login(client, "budi", "salahsalah")
    unknown = login(client, "nobody", "salahsalah")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    assert "set-cookie" not in unknown.headers and "set-cookie" not in wrong.headers


def test_unknown_username_still_verifies_against_dummy_hash(client, monkeypatch):
    register(client)
    seen = []
    real = security.verify_password

    def spy(stored, password):
        seen.append(stored)
        return real(stored, password)

    monkeypatch.setattr(security, "verify_password", spy)
    login(client, "nobody", "salahsalah")
    assert seen == [security.DUMMY_HASH]
    seen.clear()
    login(client, "budi", "salahsalah")
    assert seen == [stored_hash()]  # exactly one verification in both cases


def test_dummy_hash_costs_the_same_as_real_hashes():
    assert security.DUMMY_HASH.startswith("$argon2id$")
    assert not security.needs_rehash(security.DUMMY_HASH)


def test_corrupt_stored_hash_is_a_failed_login_not_a_500(client):
    register(client)
    set_hash("not-an-argon2-hash")
    assert login(client).status_code == 401


# --- needs_rehash ------------------------------------------------------------


def test_needs_rehash_flags_weaker_parameters_only():
    assert security.needs_rehash(WEAK.hash("rahasia123"))
    assert not security.needs_rehash(security.hash_password("rahasia123"))


def test_login_rehashes_an_outdated_hash(client):
    register(client)
    old = WEAK.hash("rahasia123")
    set_hash(old)
    assert login(client).status_code == 200
    new = stored_hash()
    assert new != old
    assert not security.needs_rehash(new)
    assert security.verify_password(new, "rahasia123")
    client.post(AUTH + "/logout")
    assert login(client).status_code == 200  # the upgraded hash still works


def test_failed_login_does_not_rehash(client):
    register(client)
    old = WEAK.hash("rahasia123")
    set_hash(old)
    assert login(client, password="salahsalah").status_code == 401
    assert stored_hash() == old


def test_current_hash_is_left_alone_on_login(client):
    register(client)
    before = stored_hash()
    assert login(client).status_code == 200
    assert stored_hash() == before