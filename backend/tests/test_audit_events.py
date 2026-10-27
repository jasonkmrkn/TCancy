import ipaddress
import logging
import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import account, audit, config
from app.db import SessionLocal, engine
from app.main import app
from app.models import RefreshToken
from helpers import make_profile
from test_job import make_user
from test_sessions import assert_cookies_cleared, family_of, login, put_refresh, refresh, sign_in

AUTH = "/api/v1/auth"
ME = "/api/v1/me"
PASSWORD = "rahasia123"


def entries(action=None):
    sql = "SELECT * FROM audit_logs" + (" WHERE action = :a" if action else "") + " ORDER BY created_at, id"
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), {"a": action}).mappings()]


def forget():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE audit_logs"))


def one(action):
    found = entries(action)
    assert len(found) == 1, found
    return found[0]


def user_id(username="budi"):
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).scalar()


def attempt(client, username="budi", password="salah-salah", **kwargs):
    return client.post(AUTH + "/login", json={"username": username, "password": password}, **kwargs)


@contextmanager
def from_address(peer):
    async def asgi(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "client": (peer, 5000)}
        await app(scope, receive, send)

    with TestClient(asgi) as c:
        yield c


def lenient_client():
    """A client that answers 500 instead of raising when the app fails."""
    return TestClient(app, raise_server_exceptions=False)


# --- auth.register --------------------------------------------------------------


def test_registering_an_applicant_is_recorded(client):
    r = client.post(AUTH + "/register", json={"username": "budi", "password": PASSWORD, "profile": make_profile()})
    assert r.status_code == 201
    row = one("auth.register")
    uid = uuid.UUID(r.json()["id"])
    assert (row["actor_id"], row["actor_role"], row["target_type"], row["target_id"]) == (uid, "applicant", "user", uid)
    assert row["ip"] == "testclient" and row["user_agent"] == "testclient"
    assert row["details"] is None and row["created_at"] is not None


def test_registering_an_alumni_is_recorded_with_its_role(client):
    r = client.post(AUTH + "/register/alumni", json={"username": "sari", "password": PASSWORD, "profile": {"full_name": "Sari", "company": "Acme", "angkatan": 2015}})
    assert r.status_code == 201
    row = one("auth.register")
    assert row["actor_role"] == "alumni" and row["actor_id"] == uuid.UUID(r.json()["id"])


def test_a_registration_that_did_not_happen_is_not_recorded(client):
    body = {"username": "budi", "password": PASSWORD, "profile": make_profile()}
    assert client.post(AUTH + "/register", json=body).status_code == 201
    forget()
    assert client.post(AUTH + "/register", json={**body, "profile": make_profile()}).status_code == 409  # username taken
    assert client.post(AUTH + "/register", json={"username": "x"}).status_code == 422
    assert entries() == []


def test_a_registration_refused_by_the_rate_limit_is_not_recorded(client, monkeypatch):
    monkeypatch.setattr(config, "REGISTER_LIMIT", 1)
    client.post(AUTH + "/register", json={"username": "budi", "password": PASSWORD, "profile": make_profile()})
    forget()
    assert client.post(AUTH + "/register", json={"username": "siti", "password": PASSWORD, "profile": make_profile()}).status_code == 429
    assert entries() == []


def test_the_registration_and_its_entry_stand_or_fall_together(monkeypatch):
    def broken(db, **kwargs):
        raise RuntimeError("the audit table is gone")

    monkeypatch.setattr(audit, "record", broken)
    r = lenient_client().post(AUTH + "/register", json={"username": "budi", "password": PASSWORD, "profile": make_profile()})
    assert r.status_code == 500
    assert user_id("budi") is None  # no account without its entry


# --- auth.login -----------------------------------------------------------------


def test_a_login_is_recorded(client):
    sign_in(client)
    forget()
    login(client)
    row = one("auth.login")
    uid = user_id()
    assert (row["actor_id"], row["actor_role"], row["target_type"], row["target_id"]) == (uid, "applicant", "user", uid)
    assert row["ip"] == "testclient" and row["details"] is None
    assert entries("auth.login_failed") == []


def test_the_login_and_its_entry_stand_or_fall_together(client, monkeypatch):
    sign_in(client)
    client.cookies.clear()
    forget()
    with SessionLocal() as db:
        sessions_before = len(db.scalars(select(RefreshToken)).all())

    def broken(db, **kwargs):
        raise RuntimeError("the audit table is gone")

    monkeypatch.setattr(audit, "record", broken)
    c = lenient_client()
    r = c.post(AUTH + "/login", json={"username": "budi", "password": PASSWORD})
    assert r.status_code == 500 and "access_token" not in c.cookies
    with SessionLocal() as db:
        assert len(db.scalars(select(RefreshToken)).all()) == sessions_before  # no session was started


# --- auth.login_failed ----------------------------------------------------------


def test_a_wrong_password_is_recorded_against_the_account(client):
    sign_in(client)
    forget()
    assert attempt(client).status_code == 401
    row = one("auth.login_failed")
    assert (row["actor_id"], row["actor_role"]) == (None, None)
    assert (row["target_type"], row["target_id"]) == ("user", user_id())
    assert row["details"] == {"known_user": 1, "suspended": 0}
    assert row["ip"] == "testclient" and row["user_agent"] == "testclient"
    assert entries("auth.login") == []


def test_an_unknown_username_is_recorded_without_a_target(client):
    assert attempt(client, "hantu").status_code == 401
    row = one("auth.login_failed")
    assert (row["actor_id"], row["target_type"], row["target_id"]) == (None, None, None)
    assert row["details"] == {"known_user": 0, "suspended": 0}


def test_a_login_to_a_suspended_account_is_recorded_as_failed(client):
    make_user(client, "budi", "applicant", status="suspended")
    forget()
    r = attempt(client, "budi", PASSWORD)
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_SUSPENDED"
    row = one("auth.login_failed")
    assert row["target_id"] == user_id() and row["details"] == {"known_user": 1, "suspended": 1}
    assert entries("auth.login") == []


def test_every_failed_attempt_gets_its_own_entry_until_the_limit(client):
    for _ in range(5):
        assert attempt(client, "hantu").status_code == 401
    assert attempt(client, "hantu").status_code == 429  # refused by the limiter: not recorded
    assert len(entries("auth.login_failed")) == 5


def test_the_typed_username_is_never_stored(client):
    typed_password = "Sup3rSecretTyped!"
    attempt(client, typed_password)
    attempt(client, "budi-yang-tidak-ada")
    everything = " ".join(str(v) for row in entries() for v in row.values())
    assert typed_password.lower() not in everything.lower() and "tidak-ada" not in everything


def test_the_answer_does_not_depend_on_whether_the_audit_entry_is_written(client):
    sign_in(client)
    first = attempt(client)
    forget()
    second = attempt(client, "hantu")
    assert first.status_code == second.status_code == 401 and first.json() == second.json()


def test_a_user_agent_with_a_nul_byte_cannot_turn_a_failed_login_into_a_500(client):
    r = attempt(client, "hantu", headers={"User-Agent": "Mozilla/5.0\x00 (X11)"})
    assert r.status_code == 401
    assert one("auth.login_failed")["user_agent"] == "Mozilla/5.0 (X11)"


def test_a_huge_user_agent_is_cut(client):
    attempt(client, "hantu", headers={"User-Agent": "A" * 100_000})
    assert len(one("auth.login_failed")["user_agent"]) == 256


def test_the_address_behind_a_trusted_proxy_is_recorded_in_full(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", (ipaddress.ip_network("172.18.0.0/16"),))
    with from_address("172.18.0.2") as proxy:
        attempt(proxy, "hantu", headers={"X-Forwarded-For": "6.6.6.6, 2001:db8:1:2:aaaa:bbbb:cccc:dddd"})
        attempt(proxy, "hantu", headers={"X-Forwarded-For": "198.51.100.7"})
    assert [r["ip"] for r in entries("auth.login_failed")] == ["2001:db8:1:2:aaaa:bbbb:cccc:dddd", "198.51.100.7"]


def test_a_forged_forwarded_for_is_not_recorded_when_no_proxy_is_trusted(client):
    attempt(client, "hantu", headers={"X-Forwarded-For": "6.6.6.6"})
    assert one("auth.login_failed")["ip"] == "testclient"


# --- auth.logout ----------------------------------------------------------------


def test_a_logout_is_recorded(client):
    sign_in(client)
    forget()
    assert client.post(AUTH + "/logout").status_code == 200
    row = one("auth.logout")
    uid = user_id()
    assert (row["actor_id"], row["actor_role"], row["target_type"], row["target_id"]) == (uid, "applicant", "user", uid)
    assert row["ip"] == "testclient"


def test_a_logout_without_a_live_session_is_not_recorded(client):
    sign_in(client)
    token = client.cookies["refresh_token"]
    client.post(AUTH + "/logout")
    forget()
    client.post(AUTH + "/logout")  # the cookies are gone: nothing to end
    put_refresh(client, token)
    assert client.post(AUTH + "/logout").status_code == 200  # a token whose family is already revoked
    client.cookies.clear()
    put_refresh(client, "not-a-token")
    assert client.post(AUTH + "/logout").status_code == 200
    assert entries() == []


def test_a_failing_audit_does_not_stop_a_logout(client, caplog, monkeypatch):
    sign_in(client)
    token = client.cookies["refresh_token"]
    forget()

    def broken(db, **kwargs):
        raise RuntimeError("secret detail about budi 203.0.113.9")

    monkeypatch.setattr(audit, "record", broken)
    with caplog.at_level(logging.INFO):
        r = client.post(AUTH + "/logout")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert_cookies_cleared(r)
    assert all(row.revoked_at is not None for row in family_of(token))  # the session really ended
    assert entries() == []
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "tcancy.audit"]
    assert lines == ["audit entry auth.logout could not be written (RuntimeError)"]
    assert "secret detail" not in caplog.text and "budi" not in caplog.text and "203.0.113.9" not in caplog.text
    assert str(user_id()) not in caplog.text


def test_a_database_error_in_the_audit_does_not_stop_a_logout_either(client, caplog, monkeypatch):
    sign_in(client)
    token = client.cookies["refresh_token"]

    def broken(db, **kwargs):
        db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(audit, "record", broken)
    with caplog.at_level(logging.INFO):
        r = client.post(AUTH + "/logout")
    assert r.status_code == 200
    assert_cookies_cleared(r)
    assert all(row.revoked_at is not None for row in family_of(token))
    assert "audit entry auth.logout could not be written (DataError)" in caplog.text
    assert "division" not in caplog.text


# --- auth.refresh_reuse ---------------------------------------------------------


def spent_token(client):
    sign_in(client)
    old = client.cookies["refresh_token"]
    assert refresh(client).status_code == 200
    put_refresh(client, old)
    return old


def test_replaying_a_spent_refresh_token_is_recorded(client):
    old = spent_token(client)
    forget()
    r = refresh(client)
    assert r.status_code == 401 and r.json()["detail"] == "invalid refresh token"
    assert_cookies_cleared(r)
    row = one("auth.refresh_reuse")
    uid = user_id()
    family = family_of(old)[0].family_id
    assert (row["actor_id"], row["actor_role"], row["target_type"], row["target_id"]) == (uid, "applicant", "refresh_family", family)
    assert row["details"] == {"revoked_tokens": 1}  # the live successor that was cut off
    assert row["ip"] == "testclient"


def test_normal_refreshes_and_unusable_tokens_are_not_recorded(client):
    sign_in(client)
    forget()
    assert refresh(client).status_code == 200
    assert refresh(client).status_code == 200
    client.cookies.clear()
    assert refresh(client).status_code == 401  # no cookie
    put_refresh(client, "not-a-token")
    assert refresh(client).status_code == 401
    assert entries() == []


def test_each_replay_is_recorded(client):
    old = spent_token(client)
    forget()
    refresh(client)
    put_refresh(client, old)  # the first answer cleared the cookies; replay the same token again
    refresh(client)
    assert [r["details"] for r in entries("auth.refresh_reuse")] == [{"revoked_tokens": 1}, {"revoked_tokens": 0}]


def test_a_failing_audit_does_not_change_the_answer_to_a_replay(client, caplog, monkeypatch):
    old = spent_token(client)
    forget()

    def broken(db, **kwargs):
        raise RuntimeError("secret detail about budi")

    monkeypatch.setattr(audit, "record", broken)
    with caplog.at_level(logging.INFO):
        r = refresh(client)
    assert r.status_code == 401 and r.json() == {"detail": "invalid refresh token"}
    assert_cookies_cleared(r)
    assert all(row.revoked_at is not None for row in family_of(old))  # the family is still revoked
    assert entries() == []
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "tcancy.audit"]
    assert lines == ["audit entry auth.refresh_reuse could not be written (RuntimeError)"]
    assert "secret detail" not in caplog.text and "budi" not in caplog.text
    assert all(str(user_id()) not in line for line in lines)


def test_a_database_error_in_the_audit_does_not_change_the_answer_to_a_replay(client, caplog, monkeypatch):
    old = spent_token(client)

    def broken(db, **kwargs):
        db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(audit, "record", broken)
    with caplog.at_level(logging.INFO):
        r = refresh(client)
    assert r.status_code == 401
    assert all(row.revoked_at is not None for row in family_of(old))
    assert "audit entry auth.refresh_reuse could not be written (DataError)" in caplog.text


def test_replays_are_still_logged_the_old_way(client, caplog):
    spent_token(client)
    with caplog.at_level(logging.WARNING, logger="tcancy.auth"):
        refresh(client)
    assert "refresh token reuse: revoked family" in caplog.text


# --- account.delete -------------------------------------------------------------


def delete(client, password=PASSWORD):
    return client.request("DELETE", ME + "/account", json={"password": password})


def test_deleting_an_account_is_recorded_and_the_entry_outlives_the_account(client):
    sign_in(client)
    uid = user_id()
    forget()
    assert delete(client).status_code == 200
    assert user_id() is None  # the account is gone
    row = one("account.delete")
    assert (row["actor_id"], row["actor_role"], row["target_type"], row["target_id"]) == (uid, "applicant", "user", uid)
    assert row["ip"] == "testclient" and row["details"] is None


def test_a_deletion_that_did_not_happen_is_not_recorded(client, monkeypatch):
    sign_in(client)
    forget()
    assert delete(client, "salah-salah").status_code == 403
    assert entries("account.delete") == []
    monkeypatch.setattr(config, "DELETE_ACCOUNT_LIMIT", 1)
    delete(client, "salah-salah")
    forget()
    assert delete(client).status_code == 429
    assert entries() == [] and user_id() is not None


def test_the_deletion_and_its_entry_stand_or_fall_together(client, monkeypatch):
    sign_in(client)
    forget()

    def broken_delete(db, user):
        raise RuntimeError("the deletion failed half way")

    monkeypatch.setattr(account, "delete_account", broken_delete)
    c = lenient_client()
    c.cookies = client.cookies
    r = c.request("DELETE", ME + "/account", json={"password": PASSWORD}, headers={"X-CSRF-Token": client.cookies["csrf_token"]})
    assert r.status_code == 500
    assert entries("account.delete") == [] and user_id() is not None


def test_no_entry_means_no_deletion(client, monkeypatch):
    sign_in(client)

    def broken(db, **kwargs):
        raise RuntimeError("the audit table is gone")

    monkeypatch.setattr(audit, "record", broken)
    c = lenient_client()
    c.cookies = client.cookies
    r = c.request("DELETE", ME + "/account", json={"password": PASSWORD}, headers={"X-CSRF-Token": client.cookies["csrf_token"]})
    assert r.status_code == 500 and user_id() is not None


# --- what is never in the log ---------------------------------------------------


def test_no_secret_ends_up_in_the_audit_log(client):
    profile = make_profile()
    typed_into_username = "Sup3rSecretTyped!"
    client.post(AUTH + "/register", json={"username": "budi", "password": PASSWORD, "profile": profile})
    attempt(client, "budi", "salah-salah")
    attempt(client, typed_into_username, "salah-salah")
    login(client)
    secrets = {name: client.cookies[name] for name in ("access_token", "refresh_token", "csrf_token")}
    old = secrets["refresh_token"]
    refresh(client)
    put_refresh(client, old)
    refresh(client)  # replay
    login(client)
    client.post(AUTH + "/logout")
    login(client)
    delete(client)
    actions = {row["action"] for row in entries()}
    assert actions == {"auth.register", "auth.login", "auth.login_failed", "auth.refresh_reuse", "auth.logout", "account.delete"}
    with engine.connect() as conn:
        dump = " ".join(conn.execute(text("SELECT row_to_json(a)::text FROM audit_logs a")).scalars())
    forbidden = {"password": PASSWORD, "wrong password": "salah-salah", "typed username": typed_into_username, **secrets,
                 "email": profile["email"], "nik": profile["nik"], "name": profile["full_name"], "phone": profile["phone"]}
    for label, value in forbidden.items():
        assert value not in dump, label
    assert "budi" not in dump  # not even the username