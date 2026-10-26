import ipaddress
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import config, ratelimit, security
from app.db import engine
from app.main import app
from app.ratelimit import RateLimitUnavailable
from helpers import make_alumni_profile, make_profile

AUTH = "/api/v1/auth"
ACCOUNT = "/api/v1/me/account"
HEADERS = {
    "x-content-type-options": "nosniff", "x-frame-options": "DENY",
    "referrer-policy": "no-referrer", "cache-control": "no-store",
}


@contextmanager
def from_address(peer):
    """A client whose connection comes from `peer` (this Starlette's TestClient always says "testclient")."""

    async def asgi(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "client": (peer, 5000)}
        await app(scope, receive, send)

    with TestClient(asgi) as c:
        yield c


def register(c, username="budi", headers=None):
    return c.post(AUTH + "/register", headers=headers,
                  json={"username": username, "password": "rahasia123", "profile": make_profile()})


def register_alumni(c, username="alumna"):
    return c.post(AUTH + "/register/alumni",
                  json={"username": username, "password": "rahasia123", "profile": make_alumni_profile()})


def login(c, username="budi", password="rahasia123", headers=None):
    return c.post(AUTH + "/login", json={"username": username, "password": password}, headers=headers)


def delete(c, password="rahasia123"):
    return c.request("DELETE", ACCOUNT, json={"password": password})


def users():
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM users")).scalar()


def assert_limited(r):
    assert r.status_code == 429, r.text
    assert r.json() == {"detail": "RATE_LIMITED"}
    assert 1 <= int(r.headers["retry-after"]) <= 3600
    for name, value in HEADERS.items():
        assert r.headers[name] == value
    assert "set-cookie" not in r.headers


class Broken:
    def hit(self, *a):
        raise RateLimitUnavailable()


def assert_unavailable(r):
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": "RATE_LIMIT_UNAVAILABLE"}
    for name, value in HEADERS.items():
        assert r.headers[name] == value
    assert "set-cookie" not in r.headers


# --- register -------------------------------------------------------------------


def test_the_eleventh_registration_in_an_hour_is_refused(client):
    for i in range(10):
        assert register(client, f"user{i:02d}").status_code == 201
    assert_limited(register(client, "user10"))
    assert users() == 10


def test_both_registration_endpoints_share_one_budget(client):
    for i in range(6):
        assert register(client, f"user{i:02d}").status_code == 201
    for i in range(4):
        assert register_alumni(client, f"alum{i:02d}").status_code == 201
    assert_limited(register_alumni(client, "alum04"))
    assert_limited(register(client, "user06"))


def test_another_address_has_its_own_registration_budget(client):
    for i in range(10):
        register(client, f"user{i:02d}")
    assert_limited(register(client, "user10"))
    with from_address("198.51.100.20") as other:
        assert register(other, "user10").status_code == 201


def test_invalid_bodies_never_reach_the_limiter(client):
    for _ in range(15):
        assert client.post(AUTH + "/register", json={"username": "x"}).status_code == 422
    assert register(client, "budi").status_code == 201


def test_registration_is_limited_before_the_database_is_asked(client, monkeypatch):
    monkeypatch.setattr(config, "REGISTER_LIMIT", 1)
    assert register(client, "budi").status_code == 201
    assert_limited(register(client, "budi"))  # a duplicate would have been 409 had the database been asked


def test_the_window_comes_from_config(client, monkeypatch):
    monkeypatch.setattr(config, "REGISTER_LIMIT", 1)
    monkeypatch.setattr(config, "REGISTER_WINDOW_SECONDS", 30)
    register(client, "budi")
    r = register(client, "siti")
    assert r.status_code == 429 and int(r.headers["retry-after"]) <= 30


# --- login ----------------------------------------------------------------------


def test_the_sixth_login_for_one_account_in_a_minute_is_refused_even_with_the_right_password(client):
    register(client, "budi")
    for _ in range(5):
        assert login(client, "budi", "salah-salah").status_code == 401
    assert_limited(login(client, "budi"))
    assert_limited(login(client, "budi", "salah-salah"))


def test_successful_logins_count_too(client):
    register(client, "budi")
    for _ in range(5):
        assert login(client, "budi").status_code == 200
    assert_limited(login(client, "budi"))


def test_one_account_being_limited_does_not_block_other_accounts_from_the_same_address(client):
    register(client, "budi")
    register(client, "siti")
    for _ in range(5):
        login(client, "budi", "salah-salah")
    assert_limited(login(client, "budi"))
    assert login(client, "siti").status_code == 200


def test_the_username_budget_is_per_address(client):
    register(client, "budi")
    for _ in range(5):
        login(client, "budi", "salah-salah")
    assert_limited(login(client, "budi"))
    with from_address("198.51.100.20") as other:
        assert login(other, "budi").status_code == 200  # the owner is not locked out by an attacker elsewhere


def test_spelling_the_username_differently_does_not_buy_more_attempts(client):
    register(client, "budi")
    for name in ["budi", "BUDI", " Budi", "budi ", "bUdI"]:
        login(client, name, "salah-salah")
    assert_limited(login(client, "budi"))


def test_unknown_usernames_are_limited_like_known_ones(client):
    for _ in range(5):
        assert login(client, "hantu", "salah-salah").status_code == 401
    assert_limited(login(client, "hantu"))


def test_sixty_logins_a_minute_per_address(client, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_IP_LIMIT", 6)
    for i in range(6):
        assert login(client, f"user{i}", "salah-salah").status_code == 401
    assert_limited(login(client, "user6", "salah-salah"))
    with from_address("198.51.100.20") as other:
        assert login(other, "user6", "salah-salah").status_code == 401


def test_a_refused_login_does_no_hashing_and_touches_no_database(client, monkeypatch):
    register(client, "budi")
    for _ in range(5):
        login(client, "budi", "salah-salah")
    calls = []
    real = security.verify_password
    monkeypatch.setattr(security, "verify_password", lambda *a: calls.append(a) or real(*a))
    assert_limited(login(client, "budi"))
    assert calls == []


def test_an_invalid_login_body_is_not_counted(client):
    for _ in range(10):
        assert client.post(AUTH + "/login", json={"username": "budi"}).status_code == 422
    register(client, "budi")
    assert login(client, "budi").status_code == 200


# --- delete account -------------------------------------------------------------


def test_the_sixth_account_deletion_attempt_in_a_minute_is_refused_and_the_account_survives(client):
    register(client, "budi")
    assert login(client, "budi").status_code == 200
    for _ in range(5):
        r = delete(client, "salah-salah")
        assert r.status_code == 403 and r.json()["detail"] == "INVALID_PASSWORD"
    assert_limited(delete(client, "rahasia123"))  # right password, but over the limit
    assert users() == 1
    assert login(client, "siti").status_code != 429  # unrelated key, other budgets untouched


def test_deleting_still_needs_the_password(client):
    register(client, "budi")
    login(client, "budi")
    assert delete(client, "salah").status_code == 403
    assert users() == 1
    assert delete(client).status_code == 200
    assert users() == 0


def test_the_deletion_budget_is_per_user(client):
    register(client, "budi")
    register(client, "siti")
    login(client, "budi")
    for _ in range(5):
        delete(client, "salah-salah")
    assert_limited(delete(client))
    client.cookies.clear()
    login(client, "siti")
    assert delete(client, "salah-salah").status_code == 403  # siti has a fresh budget


def test_an_anonymous_delete_is_still_401_and_not_limited(client):
    for _ in range(8):
        assert delete(client).status_code in (401, 403)


# --- the limiter is down: closed ------------------------------------------------


def test_register_login_and_delete_answer_503_when_the_backend_is_down(client):
    register(client, "budi")
    login(client, "budi")
    ratelimit.use_backend(Broken())
    assert_unavailable(register(client, "siti"))
    assert_unavailable(register_alumni(client, "alum"))
    assert_unavailable(login(client, "budi"))
    assert_unavailable(delete(client))
    ratelimit.use_backend(None)
    assert users() == 1  # nothing was created or deleted meanwhile
    assert login(client, "budi").status_code == 200


def test_503_sets_no_session(client):
    register(client, "budi")
    client.cookies.clear()
    ratelimit.use_backend(Broken())
    r = login(client, "budi")
    assert_unavailable(r)
    assert "access_token" not in client.cookies


# --- which address is counted ---------------------------------------------------


def test_forged_forwarded_for_headers_buy_nothing_when_no_proxy_is_trusted(client):
    for i in range(10):
        assert register(client, f"user{i:02d}", headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code == 201
    assert_limited(register(client, "user10", headers={"X-Forwarded-For": "203.0.113.200"}))


def test_behind_a_trusted_proxy_each_real_client_has_its_own_budget(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", (ipaddress.ip_network("172.18.0.0/16"),))
    with from_address("172.18.0.2") as proxy:
        for i in range(10):
            assert register(proxy, f"user{i:02d}", headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 201
        assert_limited(register(proxy, "user10", headers={"X-Forwarded-For": "198.51.100.1"}))
        assert register(proxy, "user10", headers={"X-Forwarded-For": "198.51.100.2"}).status_code == 201


def test_behind_a_trusted_proxy_entries_written_by_the_client_are_ignored(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", (ipaddress.ip_network("172.18.0.0/16"),))
    with from_address("172.18.0.2") as proxy:
        for i in range(10):
            forged = f"10.9.8.{i}, 198.51.100.1"  # the proxy appended the real address on the right
            assert register(proxy, f"user{i:02d}", headers={"X-Forwarded-For": forged}).status_code == 201
        assert_limited(register(proxy, "user10", headers={"X-Forwarded-For": "10.1.1.1, 198.51.100.1"}))


def test_an_untrusted_peer_cannot_borrow_a_proxys_privilege(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", (ipaddress.ip_network("172.18.0.0/16"),))
    with from_address("198.51.100.99") as stranger:
        for i in range(10):
            assert register(stranger, f"user{i:02d}", headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code == 201
        assert_limited(register(stranger, "user10", headers={"X-Forwarded-For": "203.0.113.250"}))