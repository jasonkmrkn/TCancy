import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import config
from app.db import SessionLocal, engine
from app.main import app
from app.models import RefreshToken
from helpers import login_as, make_alumni_profile, make_profile

AUTH = "/api/v1/auth"
PASSWORD = "rahasia123"
CSRF_FAILED = {"detail": "CSRF_FAILED"}


@app.post("/_test/csrf_probe")
def _csrf_probe():
    return {"ok": True}


@pytest.fixture(autouse=True)
def hand_written_headers_only(client):
    client.auto_csrf = False


def register(client, username="budi"):
    r = client.post(
        AUTH + "/register",
        json={"username": username, "password": PASSWORD, "profile": make_profile()},
    )
    assert r.status_code == 201


def logged_in(client, username="budi"):
    """Register + log in. Returns the header a front end would send from now on."""
    register(client, username)
    return login_as(client, username, PASSWORD)


def set_cookie_headers(response):
    return {h.split("=", 1)[0]: h for h in response.headers.get_list("set-cookie")}


def revoked_flags():
    with SessionLocal() as db:
        return [r.revoked_at is not None for r in db.scalars(select(RefreshToken)).all()]


def count_users():
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM users")).scalar()


# --- the cookie ----------------------------------------------------------------


def test_login_sets_a_script_readable_csrf_cookie(client):
    register(client)
    r = client.post(AUTH + "/login", json={"username": "budi", "password": PASSWORD})
    header = set_cookie_headers(r)["csrf_token"]
    assert "HttpOnly" not in header  # the front end has to read it
    assert "Path=/;" in header + ";"
    assert "SameSite=lax" in header
    assert "Max-Age=604800" in header  # 7 days: as long as the refresh cookie
    assert "Secure" not in header  # tests run with COOKIE_SECURE=false
    assert len(client.cookies["csrf_token"]) >= 43


def test_login_as_returns_the_cookie_value_in_the_agreed_shape(client):
    register(client)
    headers = login_as(client, "budi", PASSWORD)
    assert list(headers) == ["X-CSRF-Token"]
    assert headers["X-CSRF-Token"] == client.cookies["csrf_token"]


def test_every_login_gets_a_new_token(client):
    first = logged_in(client)["X-CSRF-Token"]
    second = login_as(client, "budi", PASSWORD)["X-CSRF-Token"]
    assert first != second


def test_csrf_cookie_gets_the_secure_flag_from_config(client, monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    register(client)
    r = client.post(AUTH + "/login", json={"username": "budi", "password": PASSWORD})
    assert "Secure" in set_cookie_headers(r)["csrf_token"]


# --- enforcement ---------------------------------------------------------------

CHANGING_REQUESTS = [
    ("PUT", "/api/v1/me/profile", {"json": {}}),
    ("POST", AUTH + "/logout", {}),
    ("POST", AUTH + "/refresh", {}),
    ("DELETE", "/api/v1/me/account", {"json": {"password": PASSWORD}}),
    ("POST", "/api/v1/jobs/00000000-0000-0000-0000-000000000000/apply", {}),
]
IDS = ["profile", "logout", "refresh", "delete-account", "apply"]


@pytest.mark.parametrize("method,url,kwargs", CHANGING_REQUESTS, ids=IDS)
@pytest.mark.parametrize("sent", [None, "", "wrong-value"], ids=["no-header", "empty", "wrong"])
def test_changing_request_without_a_matching_header_is_refused(client, method, url, kwargs, sent):
    logged_in(client)
    headers = {} if sent is None else {"X-CSRF-Token": sent}
    r = client.request(method, url, headers=headers, **kwargs)
    assert r.status_code == 403
    assert r.json() == CSRF_FAILED


@pytest.mark.parametrize("method,url,kwargs", CHANGING_REQUESTS, ids=IDS)
def test_changing_request_with_the_right_header_reaches_the_endpoint(client, method, url, kwargs):
    headers = logged_in(client)
    r = client.request(method, url, headers=headers, **kwargs)
    assert r.json() != CSRF_FAILED


def test_refused_requests_have_no_side_effects(client):
    logged_in(client)
    assert client.request("DELETE", "/api/v1/me/account", json={"password": PASSWORD}).status_code == 403
    assert client.post(AUTH + "/logout").status_code == 403
    assert count_users() == 1
    assert revoked_flags() == [False]


def test_right_header_makes_logout_and_delete_work(client):
    headers = logged_in(client)
    assert client.post(AUTH + "/logout", headers=headers).status_code == 200
    assert revoked_flags() == [True]

    headers = login_as(client, "budi", PASSWORD)
    r = client.request("DELETE", "/api/v1/me/account", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 200
    assert count_users() == 0


def test_a_form_post_from_another_site_is_refused(client):
    logged_in(client)
    r = client.post("/api/v1/jobs/00000000-0000-0000-0000-000000000000/apply", data={"x": "1"})
    assert r.status_code == 403 and r.json() == CSRF_FAILED


def test_token_from_another_session_does_not_match(client):
    logged_in(client, "budi")
    with TestClient(app) as other:
        other.auto_csrf = False
        theirs = logged_in(other, "siti")
    r = client.post(AUTH + "/logout", headers=theirs)
    assert r.status_code == 403 and r.json() == CSRF_FAILED


def test_header_without_the_cookie_is_refused(client):
    headers = logged_in(client)
    client.cookies.delete("csrf_token")
    r = client.post(AUTH + "/logout", headers=headers)
    assert r.status_code == 403 and r.json() == CSRF_FAILED


@pytest.mark.parametrize("mangle", [str.upper, lambda v: v + " ", lambda v: v[:-1], lambda v: v * 50])
def test_the_match_is_exact(client, mangle):
    headers = logged_in(client)
    r = client.post(AUTH + "/logout", headers={"X-CSRF-Token": mangle(headers["X-CSRF-Token"])})
    assert r.status_code == 403 and r.json() == CSRF_FAILED


def test_refresh_needs_the_header_even_when_the_access_cookie_is_gone(client):
    headers = logged_in(client)
    client.cookies.delete("access_token") 
    assert client.post(AUTH + "/refresh").status_code == 403
    assert client.post(AUTH + "/refresh", headers=headers).status_code == 200


# --- what is not checked -------------------------------------------------------


def test_safe_methods_need_no_header(client):
    logged_in(client)
    assert client.get(AUTH + "/me").status_code == 200
    assert client.get("/api/v1/jobs").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_register_and_login_need_no_header_even_with_old_cookies_around(client):
    logged_in(client, "budi")  
    r = client.post(
        AUTH + "/register",
        json={"username": "siti", "password": PASSWORD, "profile": make_profile()},
    )
    assert r.status_code == 201
    r = client.post(
        AUTH + "/register/alumni",
        json={"username": "alum", "password": PASSWORD, "profile": make_alumni_profile()},
    )
    assert r.status_code == 201
    r = client.post(AUTH + "/login", json={"username": "siti", "password": PASSWORD})
    assert r.status_code == 200
    assert "csrf_token" in set_cookie_headers(r)


def test_requests_without_auth_cookies_are_not_checked(client):
    assert client.post(AUTH + "/logout").status_code == 200
    r = client.post(AUTH + "/refresh")
    assert r.status_code == 401 and r.json() == {"detail": "invalid refresh token"}
    r = client.request("DELETE", "/api/v1/me/account", json={"password": PASSWORD})
    assert r.status_code == 401 and r.json() == {"detail": "not logged in"}
    r = client.put("/api/v1/me/profile", json={})
    assert r.status_code == 401


def test_a_lone_csrf_cookie_does_not_count_as_a_login(client):
    client.cookies.set("csrf_token", "something")
    assert client.post(AUTH + "/logout").status_code == 200
    assert client.put("/api/v1/me/profile", json={}).status_code == 401


def test_a_route_added_later_is_covered_without_asking(client):
    url = "/_test/csrf_probe"
    assert client.post(url).status_code == 200 
    headers = logged_in(client)
    r = client.post(url)
    assert r.status_code == 403 and r.json() == CSRF_FAILED
    assert client.post(url, headers=headers).status_code == 200


# --- lifecycle -----------------------------------------------------------------


def test_refresh_keeps_the_same_token_and_extends_its_life(client):
    headers = logged_in(client)
    r = client.post(AUTH + "/refresh", headers=headers)
    assert r.status_code == 200
    csrf_cookie = set_cookie_headers(r)["csrf_token"]
    assert csrf_cookie.startswith("csrf_token=" + headers["X-CSRF-Token"] + ";")
    assert "Max-Age=604800" in csrf_cookie and "HttpOnly" not in csrf_cookie
    # the old header still works, so a request already in flight is not caught out
    assert client.post(AUTH + "/refresh", headers=headers).status_code == 200


def test_failed_refresh_clears_the_csrf_cookie_too(client):
    headers = logged_in(client)
    client.cookies.delete("refresh_token")
    client.cookies.set("refresh_token", "nonsense", path="/api/v1/auth")
    r = client.post(AUTH + "/refresh", headers=headers)
    assert r.status_code == 401
    cleared = [h for h in r.headers.get_list("set-cookie") if "Max-Age=0" in h]
    assert {h.split("=", 1)[0] for h in cleared} == {"access_token", "refresh_token", "csrf_token"}


def test_logout_and_account_deletion_clear_the_csrf_cookie(client):
    headers = logged_in(client)
    out = client.post(AUTH + "/logout", headers=headers)
    assert "csrf_token" not in client.cookies
    assert any(h.startswith("csrf_token=") and "Max-Age=0" in h for h in out.headers.get_list("set-cookie"))

    headers = login_as(client, "budi", PASSWORD)
    out = client.request("DELETE", "/api/v1/me/account", json={"password": PASSWORD}, headers=headers)
    assert out.status_code == 200
    assert "csrf_token" not in client.cookies