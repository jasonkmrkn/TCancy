import asyncio

import pytest
from sqlalchemy import select

from app import config
from app.db import SessionLocal
from app.main import app
from app.models import RefreshToken
from app.origin import OriginCheckMiddleware
from helpers import login_as, make_profile

AUTH = "/api/v1/auth"
PASSWORD = "rahasia123"
ORIGIN = config.FRONTEND_ORIGIN
REFUSED = {"detail": "CSRF_FAILED"}
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
}


@pytest.fixture(autouse=True)
def hand_written_headers_only(client):
    client.auto_csrf = False


def register(client, username="budi"):
    r = client.post(
        AUTH + "/register",
        json={"username": username, "password": PASSWORD, "profile": make_profile()},
    )
    assert r.status_code == 201


def login(client, origin=None, username="budi"):
    headers = {} if origin is None else {"Origin": origin}
    return client.post(AUTH + "/login", json={"username": username, "password": PASSWORD}, headers=headers)


def refresh_rows():
    with SessionLocal() as db:
        return len(db.scalars(select(RefreshToken)).all())


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "null", "http://localhost:3001", "https://localhost:3000",
     ORIGIN + "/", ORIGIN.upper(), ORIGIN + ".evil.example", ""],
    ids=["other-site", "null", "other-port", "other-scheme", "trailing-slash", "upper-case",
         "suffix-trick", "empty"],
)
def test_login_from_another_origin_is_refused_and_leaves_no_session(client, origin):
    register(client)
    r = login(client, origin)
    assert r.status_code == 403 and r.json() == REFUSED
    assert "set-cookie" not in r.headers
    assert refresh_rows() == 0
    assert "access_token" not in client.cookies


def test_login_from_the_frontend_works(client):
    register(client)
    r = login(client, ORIGIN)
    assert r.status_code == 200
    assert "csrf_token" in client.cookies


def test_a_request_without_origin_passes(client):
    register(client)
    assert login(client).status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_unsafe_method_is_checked(client, method):
    r = client.request(method, "/_test/anything", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json() == REFUSED


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_are_not_checked(client, method):
    r = client.request(method, "/healthz", headers={"Origin": "https://evil.example"})
    assert r.status_code != 403


def test_logged_in_requests_are_checked_too(client):
    register(client)
    headers = login_as(client, "budi", PASSWORD)
    bad = client.post(AUTH + "/logout", headers={**headers, "Origin": "https://evil.example"})
    assert bad.status_code == 403 and bad.json() == REFUSED
    assert client.post(AUTH + "/logout", headers={**headers, "Origin": ORIGIN}).status_code == 200


def test_register_is_checked_as_well(client):
    r = client.post(
        AUTH + "/register/alumni",
        json={"username": "alum", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403 and r.json() == REFUSED


def test_two_origin_headers_need_both_to_be_right(client):
    register(client)
    body = {"username": "budi", "password": PASSWORD}
    ok = client.post(AUTH + "/login", json=body, headers=[("origin", ORIGIN), ("origin", ORIGIN)])
    assert ok.status_code == 200
    bad = client.post(AUTH + "/login", json=body, headers=[("origin", ORIGIN), ("origin", "https://evil.example")])
    assert bad.status_code == 403


def test_the_refusal_carries_the_four_headers_and_the_cors_headers_for_the_frontend_only(client):
    r = client.post(AUTH + "/login", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    for name, value in SECURITY_HEADERS.items():
        assert r.headers.get_list(name) == [value]
    assert "access-control-allow-origin" not in r.headers


def test_a_preflight_is_still_answered_by_cors(client):
    r = client.options(
        AUTH + "/login",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 200
    r = client.options(
        AUTH + "/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 400  # CORS' own refusal, not ours


def test_the_check_is_part_of_the_app_in_the_right_place():
    names = [m.cls.__name__ for m in app.user_middleware]
    assert names == ["SecurityHeadersMiddleware", "CORSMiddleware", "OriginCheckMiddleware", "BodySizeLimitMiddleware"]


def test_the_allowed_origin_is_whatever_it_is_configured_with():
    seen = []

    async def inner(scope, receive, send):
        seen.append("reached")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    def call(wrapped, origin):
        out = {}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]

        scope = {"type": "http", "method": "POST", "path": "/", "headers": [(b"origin", origin.encode())]}
        asyncio.run(wrapped(scope, None, send))
        return out["status"]

    wrapped = OriginCheckMiddleware(inner, allowed_origin="https://tcancy.example.com")
    assert call(wrapped, "https://tcancy.example.com") == 200
    assert call(wrapped, "http://localhost:3000") == 403
    assert seen == ["reached"]


def test_non_http_scopes_pass():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(OriginCheckMiddleware(inner, allowed_origin="https://x.example")({"type": "websocket"}, None, None))
    assert seen == ["websocket"]