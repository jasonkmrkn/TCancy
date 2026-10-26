import logging
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import auth, config, tokens
from app.db import SessionLocal, engine
from app.main import app
from app.models import RefreshToken, User
from helpers import make_profile

BASE = "/api/v1/auth"
PASSWORD = "rahasia123"


# --- helpers -------------------------------------------------------------------


def sign_in(client, username="budi"):
    r = client.post(
        BASE + "/register",
        json={"username": username, "password": PASSWORD, "profile": make_profile()},
    )
    assert r.status_code == 201
    return login(client, username)


def login(client, username="budi"):
    r = client.post(BASE + "/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return r


def refresh(client):
    return client.post(BASE + "/refresh")


def put_cookie(client, name, value, path="/"):
    # Same domain the client stores real cookies under, so a later Set-Cookie from the
    # server replaces this one instead of sitting next to it (a browser has one jar entry).
    client.cookies.delete(name)
    client.cookies.set(name, value, domain="testserver.local", path=path)


def put_refresh(client, value):
    put_cookie(client, "refresh_token", value, auth.REFRESH_COOKIE_PATH)
    if not any(c.name == "csrf_token" for c in client.cookies.jar):
        put_cookie(client, "csrf_token", "chosen-by-the-caller")


def sql(statement, **params):
    with engine.begin() as conn:
        conn.execute(text(statement), params)


def all_rows():
    with SessionLocal() as db:
        return db.scalars(select(RefreshToken).order_by(RefreshToken.created_at)).all()


def family_of(raw_token):
    with SessionLocal() as db:
        return db.scalars(
            select(RefreshToken).where(
                RefreshToken.family_id
                == select(RefreshToken.family_id)
                .where(RefreshToken.token_hash == tokens.hash_refresh_token(raw_token))
                .scalar_subquery()
            )
        ).all()


def user_id():
    with SessionLocal() as db:
        return db.scalar(select(User.id))


def cleared_cookies(response):
    """Set-Cookie headers that delete a cookie, by cookie name."""
    out = {}
    for header in response.headers.get_list("set-cookie"):
        if "Max-Age=0" in header:
            out[header.split("=", 1)[0]] = header
    return out


def assert_cookies_cleared(response):
    gone = cleared_cookies(response)
    assert set(gone) == {"access_token", "refresh_token", "csrf_token"}
    assert "Path=/;" in gone["access_token"] + ";"
    assert "Path=/api/v1/auth" in gone["refresh_token"]
    assert "Path=/;" in gone["csrf_token"] + ";" and "HttpOnly" not in gone["csrf_token"]


# --- cookie flags --------------------------------------------------------------


def test_cookie_attributes_on_login(client):
    r = sign_in(client)
    headers = {h.split("=", 1)[0]: h for h in r.headers.get_list("set-cookie")}
    access, refresh_cookie = headers["access_token"], headers["refresh_token"]
    for header in (access, refresh_cookie):
        assert "HttpOnly" in header
        assert "SameSite=lax" in header
        assert "Secure" not in header  # tests run with COOKIE_SECURE=false (conftest)
    assert "Max-Age=900" in access and "Path=/;" in access + ";"
    assert "Max-Age=604800" in refresh_cookie and "Path=/api/v1/auth" in refresh_cookie


def test_secure_flag_follows_config(client, monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    r = sign_in(client)
    for header in r.headers.get_list("set-cookie"):
        assert "Secure" in header
    out = client.post(BASE + "/logout")
    assert_cookies_cleared(out)
    for name, header in cleared_cookies(out).items():
        assert "Secure" in header and "SameSite=lax" in header
        assert ("HttpOnly" in header) == (name != "csrf_token")


def test_refresh_cookie_is_only_sent_to_auth_endpoints(client):
    sign_in(client)
    assert "refresh_token" not in client.get("/healthz").request.headers["cookie"]
    assert "access_token" in client.get("/healthz").request.headers["cookie"]
    assert "refresh_token" in client.get(BASE + "/me").request.headers["cookie"]


# --- rotation ------------------------------------------------------------------


def test_refresh_rotates_both_tokens(client):
    sign_in(client)
    old_access, old_refresh = client.cookies["access_token"], client.cookies["refresh_token"]

    r = refresh(client)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert client.cookies["refresh_token"] != old_refresh
    assert client.cookies["access_token"] != old_access
    assert client.get(BASE + "/me").status_code == 200

    old_row, new_row = all_rows()
    assert old_row.revoked_at is not None
    assert new_row.revoked_at is None
    assert new_row.family_id == old_row.family_id
    assert new_row.token_hash == tokens.hash_refresh_token(client.cookies["refresh_token"])
    assert new_row.expires_at > old_row.expires_at


def test_rotation_can_be_repeated(client):
    sign_in(client)
    for _ in range(3):
        assert refresh(client).status_code == 200
    rows = all_rows()
    assert len(rows) == 4
    assert len({r.family_id for r in rows}) == 1
    assert [r.revoked_at is not None for r in rows] == [True, True, True, False]
    assert client.get(BASE + "/me").status_code == 200


def test_every_login_starts_its_own_family(client):
    sign_in(client)
    with TestClient(app) as phone:
        login(phone)
    rows = all_rows()
    assert len(rows) == 2 and rows[0].family_id != rows[1].family_id


def test_refresh_works_after_the_access_token_expired(client):
    sign_in(client)
    expired = tokens.create_access_token(
        user_id(), now=datetime.now(timezone.utc) - timedelta(minutes=20)
    )
    put_cookie(client, "access_token", expired)
    assert client.get(BASE + "/me").status_code == 401

    assert refresh(client).status_code == 200
    assert client.get(BASE + "/me").status_code == 200


def test_refresh_needs_no_access_cookie(client):
    sign_in(client)
    client.cookies.delete("access_token")  # the browser drops it when Max-Age runs out
    assert refresh(client).status_code == 200
    assert client.get(BASE + "/me").status_code == 200


def test_role_and_status_changes_apply_without_a_new_login(client):
    sign_in(client)
    sql("UPDATE users SET role = 'admin'")
    assert client.get(BASE + "/me").json()["role"] == "admin"
    sql("UPDATE users SET role = 'alumni'")
    assert refresh(client).status_code == 200
    assert client.get(BASE + "/me").json()["role"] == "alumni"


# --- replay detection ----------------------------------------------------------


def test_replaying_a_spent_token_revokes_the_family(client, caplog):
    sign_in(client)
    first = client.cookies["refresh_token"]
    assert refresh(client).status_code == 200
    second = client.cookies["refresh_token"]

    put_refresh(client, first)  # an attacker holding the stolen, already-spent token
    with caplog.at_level(logging.WARNING, logger="tcancy.auth"):
        r = refresh(client)
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid refresh token"}
    assert_cookies_cleared(r)
    assert all(row.revoked_at is not None for row in all_rows())
    assert "reuse" in caplog.text
    assert first not in caplog.text and second not in caplog.text  # never log a token

    put_refresh(client, second)  # and the victim's newest token is dead too
    assert refresh(client).status_code == 401
    assert len(all_rows()) == 2  # nothing new was issued


def test_replay_only_hits_its_own_family(client):
    sign_in(client)
    with TestClient(app) as phone:
        login(phone)
        phone_token = phone.cookies["refresh_token"]

        stolen = client.cookies["refresh_token"]
        assert refresh(client).status_code == 200
        put_refresh(client, stolen)
        assert refresh(client).status_code == 401

        assert refresh(phone).status_code == 200  # the other login survives
        assert phone.cookies["refresh_token"] != phone_token


@pytest.mark.parametrize(
    "value",
    [None, "", "nonsense", "x" * 43, "a" * 5000],
    ids=["no-cookie", "empty", "junk", "right-shape-unknown", "5000-chars"],
)
def test_unusable_refresh_tokens_are_rejected(client, value):
    sign_in(client)
    before = len(all_rows())
    client.cookies.delete("refresh_token")
    if value is not None:
        put_refresh(client, value)
    r = refresh(client)
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid refresh token"}
    assert_cookies_cleared(r)
    rows = all_rows()
    assert len(rows) == before and rows[0].revoked_at is None  # unknown token harms nobody


def test_expired_refresh_token_is_rejected(client):
    sign_in(client)
    sql("UPDATE refresh_tokens SET expires_at = now() - interval '1 second'")
    r = refresh(client)
    assert r.status_code == 401
    assert_cookies_cleared(r)
    assert len(all_rows()) == 1


def test_suspended_user_cannot_refresh(client):
    sign_in(client)
    token = client.cookies["refresh_token"]
    sql("UPDATE users SET status = 'suspended'")
    r = refresh(client)
    assert r.status_code == 403
    assert r.json() == {"detail": "ACCOUNT_SUSPENDED"}
    assert_cookies_cleared(r)
    assert all(row.revoked_at is not None for row in all_rows())

    sql("UPDATE users SET status = 'active'")  # lifting the suspension does not revive it
    put_refresh(client, token)
    assert refresh(client).status_code == 401


def test_deleted_account_cannot_refresh(client):
    sign_in(client)
    token = client.cookies["refresh_token"]
    r = client.request("DELETE", "/api/v1/me/account", json={"password": PASSWORD})
    assert r.status_code == 200
    assert_cookies_cleared(r)
    assert all_rows() == []  # ON DELETE CASCADE

    put_refresh(client, token)
    assert refresh(client).status_code == 401


# --- concurrency ---------------------------------------------------------------


def test_concurrent_refresh_with_one_token_has_exactly_one_winner(client):
    sign_in(client)
    for _ in range(4):
        login(client)  # a fresh family each round
        token = client.cookies["refresh_token"]
        results, barrier = [], threading.Barrier(2)

        def attempt():
            with TestClient(app) as c:
                put_refresh(c, token)
                barrier.wait()
                results.append(c.post(BASE + "/refresh").status_code)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Whatever the interleaving: one request wins, the other is a replay, and the
        # replay revokes the family, including the token the winner just received.
        assert sorted(results) == [200, 401]
        family = family_of(token)
        assert len(family) == 2
        assert all(row.revoked_at is not None for row in family)


class RacingSession:
    """A real session that lets a rival spend the same token just before the first UPDATE."""

    def __init__(self, db, rival):
        self._db, self._rival, self._fired = db, rival, False

    def execute(self, *args, **kwargs):
        if not self._fired:
            self._fired = True
            self._rival()
        return self._db.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._db, name)


def test_losing_the_race_for_a_token_counts_as_a_replay(client):
    # Deterministic version of the test above: forces the "UPDATE matched 0 rows" branch.
    sign_in(client)
    token = client.cookies["refresh_token"]

    def rival():
        with SessionLocal() as other:
            auth.rotate_refresh_token(other, token)

    with SessionLocal() as db:
        with pytest.raises(auth.InvalidRefreshToken):
            auth.rotate_refresh_token(RacingSession(db, rival), token)

    family = family_of(token)
    assert len(family) == 2  # the rival's new token exists, and is revoked as well
    assert all(row.revoked_at is not None for row in family)


# --- logout --------------------------------------------------------------------


def test_logout_revokes_the_whole_family(client):
    sign_in(client)
    refresh(client)
    refresh(client)
    latest = client.cookies["refresh_token"]
    r = client.post(BASE + "/logout")
    assert r.status_code == 200
    assert_cookies_cleared(r)
    assert len(all_rows()) == 3 and all(row.revoked_at is not None for row in all_rows())

    put_refresh(client, latest)
    assert refresh(client).status_code == 401


def test_logout_works_with_only_the_refresh_cookie(client):
    sign_in(client)
    client.cookies.delete("access_token")  # expired and dropped by the browser
    assert client.post(BASE + "/logout").status_code == 200
    assert all_rows()[0].revoked_at is not None


def test_logout_with_an_unknown_refresh_cookie_changes_nothing(client):
    sign_in(client)
    put_refresh(client, "nonsense")
    r = client.post(BASE + "/logout")
    assert r.status_code == 200
    assert_cookies_cleared(r)
    assert all_rows()[0].revoked_at is None


def test_logout_leaves_other_devices_logged_in(client):
    sign_in(client)
    with TestClient(app) as phone:
        login(phone)
        assert client.post(BASE + "/logout").status_code == 200
        assert refresh(phone).status_code == 200


def test_access_token_outlives_logout_until_it_expires(client):
    # Documents a known limit of stateless access tokens: logout revokes the refresh
    # family, but an access token that was already issued stays valid for up to 15
    # minutes. Closing that gap needs a per-user cutoff (tokens_valid_after), not in this stage.
    sign_in(client)
    access = client.cookies["access_token"]
    client.post(BASE + "/logout")
    assert client.get(BASE + "/me").status_code == 401
    put_cookie(client, "access_token", access)
    assert client.get(BASE + "/me").status_code == 200


# --- server configuration problems ---------------------------------------------


def test_app_refuses_to_start_with_a_bad_secret(monkeypatch):
    monkeypatch.setattr(config, "SESSION_SECRET", "")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        with TestClient(app):
            pass


def test_bad_secret_at_login_creates_no_session(client, monkeypatch):
    client.post(
        BASE + "/register",
        json={"username": "budi", "password": PASSWORD, "profile": make_profile()},
    )
    monkeypatch.setattr(config, "SESSION_SECRET", "short")
    with pytest.raises(RuntimeError):
        client.post(BASE + "/login", json={"username": "budi", "password": PASSWORD})
    assert all_rows() == []
    with SessionLocal() as db:
        assert db.scalar(select(User.last_login_at)) is None


def test_bad_secret_at_refresh_does_not_burn_the_token(client, monkeypatch):
    sign_in(client)
    with monkeypatch.context() as m:
        m.setattr(config, "SESSION_SECRET", "short")
        with pytest.raises(RuntimeError):
            refresh(client)
    assert all_rows()[0].revoked_at is None
    assert refresh(client).status_code == 200