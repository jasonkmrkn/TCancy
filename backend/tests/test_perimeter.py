import asyncio
import json

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from helpers import login_as, make_profile

AUTH = "/api/v1/auth"
UPLOADS = "/api/v1/me/documents"
MiB = 1024 * 1024
PASSWORD = "SuperRahasia!9"  # distinctive, so a leak is easy to spot in a response body
ORIGIN = config.FRONTEND_ORIGIN
EVIL = "https://evil.example"

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
}


# Routes nobody wrote edge handling for: the middleware must cover them anyway.
@app.get("/_test/boom")
def _boom():
    raise RuntimeError("kaboom")


@app.get("/_test/weak_headers")
def _weak_headers():
    return JSONResponse(
        {"ok": True},
        headers={
            "Cache-Control": "public, max-age=999",
            "X-Frame-Options": "SAMEORIGIN",
            "Referrer-Policy": "unsafe-url",
            "X-Content-Type-Options": "sniff",
        },
    )


@app.post("/_test/echo_len")
async def _echo_len(request: Request):
    return {"n": len(await request.body())}


@app.get("/_test/needs_int")
def _needs_int(n: int):
    return {"n": n}


@pytest.fixture(autouse=True)
def hand_written_headers_only(client):
    client.auto_csrf = False


def assert_secured(response):
    for name, value in SECURITY_HEADERS.items():
        assert response.headers.get_list(name) == [value], name


def register_and_login(client, username="budi"):
    r = client.post(
        AUTH + "/register",
        json={"username": username, "password": "rahasia123", "profile": make_profile()},
    )
    assert r.status_code == 201
    return login_as(client, username, "rahasia123")


# --- ASGI harness ---------------------------------------------------------------


def asgi_call(asgi_app, method, path, chunks, headers=(), content_length="auto"):
    """One request through an ASGI app. Returns (status, headers dict, body, chunks the app read).

    `chunks` is the list of body pieces. content_length "auto" declares the true total,
    None sends no Content-Length (a chunked body), anything else is sent as given (a lie).
    """
    state = {"read": 0, "status": None, "headers": {}, "body": b""}
    head = [(b"host", b"testserver")] + [(k.encode(), v.encode()) for k, v in headers]
    if content_length == "auto":
        head.append((b"content-length", str(sum(len(c) for c in chunks)).encode()))
    elif content_length is not None:
        head.append((b"content-length", str(content_length).encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
        "root_path": "", "server": ("testserver", 80), "client": ("1.2.3.4", 1), "headers": head,
    }
    pieces = list(chunks) or [b""]

    async def receive():
        i = state["read"]
        if i >= len(pieces):
            await asyncio.sleep(0)
            return {"type": "http.disconnect"}
        state["read"] += 1
        return {"type": "http.request", "body": pieces[i], "more_body": i < len(pieces) - 1}

    async def send(message):
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
            state["headers"] = {k.decode(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            state["body"] += message.get("body", b"")

    asyncio.run(asgi_app(scope, receive, send))
    return state["status"], state["headers"], state["body"], state["read"]


async def reads_everything(scope, receive, send):
    total = 0
    while True:
        message = await receive()
        total += len(message.get("body", b""))
        if not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(total).encode()})


async def swallows_read_errors(scope, receive, send):
    """What FastAPI does: any error while reading the body becomes a 400."""
    try:
        while (await receive()).get("more_body"):
            pass
    except Exception:
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send({"type": "http.response.body", "body": b"There was an error parsing the body"})
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def answers_before_reading(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    while (await receive()).get("more_body"):
        pass
    await send({"type": "http.response.body", "body": b"late"})


async def unexpected_error_on_read(scope, receive, send):
    try:
        while (await receive()).get("more_body"):
            pass
    except Exception as exc:
        raise RuntimeError("something else") from exc


def limited(inner, limit=1000, limits=None):
    return BodySizeLimitMiddleware(inner, default_limit=limit, limits=limits)


# --- the four headers -----------------------------------------------------------

ANSWERS = [
    ("ok", lambda c: c.get("/healthz")),
    ("not-logged-in-401", lambda c: c.get(AUTH + "/me")),
    ("unknown-path-404", lambda c: c.get("/nope")),
    ("wrong-method-405", lambda c: c.get(AUTH + "/login")),
    ("validation-422", lambda c: c.post(AUTH + "/login", json={"username": 5})),
    ("too-large-by-header-413", lambda c: c.post(AUTH + "/login", content=b"x" * (MiB + 1))),
    ("too-large-by-count-413", lambda c: c.post("/_test/echo_len", content=iter([b"x" * MiB, b"x"]))),
    ("bad-content-length-400", lambda c: c.post("/_test/echo_len", content=b"x", headers={"content-length": "abc"})),
    ("preflight-allowed", lambda c: c.options(
        "/api/v1/jobs",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type,x-csrf-token"})),
    ("preflight-refused", lambda c: c.options(
        "/api/v1/jobs", headers={"Origin": EVIL, "Access-Control-Request-Method": "POST"})),
    ("preflight-without-origin", lambda c: c.options("/api/v1/jobs")),
]


@pytest.mark.parametrize("make_request", [a[1] for a in ANSWERS], ids=[a[0] for a in ANSWERS])
def test_every_kind_of_answer_carries_the_four_headers(client, make_request):
    r = make_request(client)
    assert_secured(r)


def test_csrf_refusal_carries_the_headers(client):
    register_and_login(client)
    r = client.post(AUTH + "/logout")  # logged in, header missing
    assert r.status_code == 403 and r.json() == {"detail": "CSRF_FAILED"}
    assert_secured(r)


def test_the_503_from_the_rate_limiter_carries_the_headers(client):
    from app.ratelimit import RateLimitUnavailable

    @app.get("/_test/limiter_down")
    def _limiter_down():
        raise RateLimitUnavailable()

    r = client.get("/_test/limiter_down")
    assert r.status_code == 503
    assert_secured(r)


def test_a_route_cannot_weaken_the_headers(client):
    r = client.get("/_test/weak_headers")
    assert r.json() == {"ok": True}
    assert_secured(r)  # exactly one value each, and it is ours


def test_unhandled_error_is_a_500_with_the_headers_and_the_usual_body():
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/_test/boom")
    assert r.status_code == 500
    assert r.text == "Internal Server Error"
    assert_secured(r)


def test_unhandled_error_is_still_raised_so_the_server_can_log_it(client):
    with pytest.raises(RuntimeError, match="kaboom"):
        client.get("/_test/boom")


def test_the_middleware_ignores_non_http_scopes():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(SecurityHeadersMiddleware(inner)({"type": "lifespan"}, None, None))
    asyncio.run(BodySizeLimitMiddleware(inner, default_limit=1)({"type": "websocket"}, None, None))
    assert seen == ["lifespan", "websocket"]


# --- CORS -----------------------------------------------------------------------


def preflight(client, origin, method="POST", headers="content-type,x-csrf-token"):
    return client.options(
        "/api/v1/jobs",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


def test_the_configured_origin_is_the_only_one_cors_knows():
    cors = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert len(cors) == 1
    assert cors[0].kwargs["allow_origins"] == [config.FRONTEND_ORIGIN]
    assert cors[0].kwargs["allow_credentials"] is True
    assert "*" not in cors[0].kwargs["allow_headers"] and "*" not in cors[0].kwargs["allow_methods"]
    assert not cors[0].kwargs.get("allow_origin_regex")


def test_preflight_from_the_frontend_is_allowed_with_credentials(client):
    r = preflight(client, ORIGIN)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"
    assert "POST" in r.headers["access-control-allow-methods"]
    assert "x-csrf-token" in r.headers["access-control-allow-headers"].lower()
    assert r.headers["access-control-max-age"] == "600"


@pytest.mark.parametrize("origin", [EVIL, "null", ORIGIN + ".evil.example", "http://localhost:3001"])
def test_preflight_from_any_other_origin_is_refused(client, origin):
    r = preflight(client, origin)
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers  # the one header a browser needs to say yes


def test_preflight_for_an_unlisted_method_or_header_is_refused(client):
    assert preflight(client, ORIGIN, method="TRACE").status_code == 400
    assert preflight(client, ORIGIN, headers="x-evil").status_code == 400


def test_real_responses_name_the_frontend_and_never_a_wildcard(client):
    r = client.get("/healthz", headers={"Origin": ORIGIN})
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"
    assert "origin" in r.headers["vary"].lower()


def test_other_origins_get_no_cors_headers_so_the_browser_hides_the_answer(client):
    for origin in (EVIL, "null"):
        r = client.get("/healthz", headers={"Origin": origin})
        assert "access-control-allow-origin" not in r.headers


def test_a_413_still_carries_the_cors_headers(client):
    r = client.post("/_test/echo_len", content=b"x" * (MiB + 1), headers={"Origin": ORIGIN})
    assert r.status_code == 413
    assert r.headers["access-control-allow-origin"] == ORIGIN


# --- FRONTEND_ORIGIN is checked when the app starts -----------------------------

VALID_ORIGINS = [
    ("http://localhost:3000", "http://localhost:3000"),
    ("https://tcancy.example.com", "https://tcancy.example.com"),
    ("HTTPS://TCancy.Example.COM", "https://tcancy.example.com"),
    ("https://tcancy.example.com:443", "https://tcancy.example.com"),
    ("http://localhost:80", "http://localhost"),
    ("http://127.0.0.1:3000", "http://127.0.0.1:3000"),
    ("http://[::1]:3000", "http://[::1]:3000"),
    ("  https://tcancy.example.com  ", "https://tcancy.example.com"),
    ("http://front_end:3000", "http://front_end:3000"),
]

INVALID_ORIGINS = [
    "*", "null", "localhost:3000", "http://", "ftp://tcancy.example.com",
    "http://localhost:3000/", "https://tcancy.example.com/app",
    "https://tcancy.example.com?x=1", "https://tcancy.example.com#top",
    "https://a.example.com,https://b.example.com", "https://a.example.com https://b.example.com",
    "https://user:secret@tcancy.example.com", "https://*.example.com",
    "http://localhost:99999", "http://localhost:abc",
]


@pytest.mark.parametrize("raw,expected", VALID_ORIGINS)
def test_frontend_origin_is_normalised_to_what_browsers_send(monkeypatch, raw, expected):
    monkeypatch.setenv("FRONTEND_ORIGIN", raw)
    assert config._origin_env("FRONTEND_ORIGIN", "http://localhost:3000") == expected


@pytest.mark.parametrize("raw", INVALID_ORIGINS)
def test_a_bad_frontend_origin_stops_the_app_from_starting(monkeypatch, raw):
    monkeypatch.setenv("FRONTEND_ORIGIN", raw)
    with pytest.raises(ValueError, match="FRONTEND_ORIGIN"):
        config._origin_env("FRONTEND_ORIGIN", "http://localhost:3000")


def test_frontend_origin_defaults_to_the_local_frontend(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    assert config._origin_env("FRONTEND_ORIGIN", "http://localhost:3000") == "http://localhost:3000"
    monkeypatch.setenv("FRONTEND_ORIGIN", "   ")
    assert config._origin_env("FRONTEND_ORIGIN", "http://localhost:3000") == "http://localhost:3000"


def test_importing_the_app_with_a_wildcard_origin_fails(monkeypatch):
    import subprocess
    import sys

    env = {**__import__("os").environ, "FRONTEND_ORIGIN": "*"}
    done = subprocess.run(
        [sys.executable, "-c", "import app.main"], env=env, capture_output=True, text=True
    )
    assert done.returncode != 0
    assert "FRONTEND_ORIGIN must be a single origin" in done.stderr


# --- request size limit ---------------------------------------------------------


def test_default_limit_is_one_mib_exactly(client):
    ok = client.post("/_test/echo_len", content=b"x" * MiB)
    assert ok.status_code == 200 and ok.json() == {"n": MiB}
    r = client.post("/_test/echo_len", content=b"x" * (MiB + 1))
    assert r.status_code == 413
    assert r.json() == {"detail": "REQUEST_TOO_LARGE"}
    assert r.headers["connection"] == "close"


def test_the_upload_route_has_its_own_larger_limit(client):
    big = b"%PDF-1.4 " + b"x" * (2 * MiB)  # over the default limit, under every file rule
    register_and_login(client)
    r = client.post(UPLOADS, data={"type": "cv"}, files={"file": ("cv.pdf", big)},
                    headers={"X-CSRF-Token": client.cookies["csrf_token"]})
    assert r.status_code == 201


def test_the_file_rules_keep_answering_their_own_413(client):
    headers = register_and_login(client)
    too_big_for_a_cv = b"%PDF-1.4 " + b"x" * (6 * MiB)
    r = client.post(UPLOADS, data={"type": "cv"}, files={"file": ("cv.pdf", too_big_for_a_cv)}, headers=headers)
    assert r.status_code == 413
    assert r.json() != {"detail": "REQUEST_TOO_LARGE"}


def test_the_upload_limit_is_for_that_route_and_method_only(client):
    # same size, other route; same route, other method
    assert client.post(AUTH + "/login", content=b"x" * (2 * MiB)).status_code == 413
    assert client.put(UPLOADS, content=b"x" * (2 * MiB)).status_code == 413


def test_a_request_over_the_upload_limit_is_refused_without_reading_it():
    status, headers, body, read = asgi_call(
        app, "POST", UPLOADS, [b"x"],
        headers=[("content-type", "multipart/form-data; boundary=b")],
        content_length=51 * MiB + 1,
    )
    assert status == 413 and json.loads(body) == {"detail": "REQUEST_TOO_LARGE"}
    assert read == 0


def test_a_chunked_upload_to_the_real_app_is_cut_off_at_the_limit():
    # No Content-Length and nobody logged in: FastAPI starts reading the multipart body
    # before it checks who is asking (and turns a read error into a 400).
    opening = (
        b"--XBOUNDARYX\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ncv\r\n"
        b"--XBOUNDARYX\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.pdf\"\r\n"
        b"Content-Type: application/pdf\r\n\r\n"
    )
    status, headers, body, read = asgi_call(
        app, "POST", UPLOADS, [opening] + [b"a" * MiB] * 60,
        headers=[("content-type", "multipart/form-data; boundary=XBOUNDARYX")],
        content_length=None,
    )
    assert status == 413 and json.loads(body) == {"detail": "REQUEST_TOO_LARGE"}
    assert read <= 53  # stopped at the limit instead of taking all 60 MiB


def test_chunked_body_without_content_length_is_counted():
    status, _, body, read = asgi_call(
        limited(reads_everything), "POST", "/x", [b"a" * 400] * 5, content_length=None
    )
    assert status == 413 and json.loads(body) == {"detail": "REQUEST_TOO_LARGE"}
    assert read == 3  # 400, 800, 1200 > 1000: the fourth and fifth chunk are never read


def test_a_lying_content_length_does_not_help():
    status, _, body, _ = asgi_call(
        limited(reads_everything), "POST", "/x", [b"a" * 600, b"a" * 600], content_length=10
    )
    assert status == 413


@pytest.mark.parametrize("size,status", [(1000, 200), (1001, 413)])
def test_the_boundary_is_exact_for_counted_bodies_too(size, status):
    got, *_ = asgi_call(
        limited(reads_everything), "POST", "/x", [b"a" * 500, b"a" * (size - 500)], content_length=None
    )
    assert got == status


def test_the_413_replaces_the_400_an_app_makes_of_a_failed_read():
    status, _, body, _ = asgi_call(
        limited(swallows_read_errors), "POST", "/x", [b"a" * 2000], content_length=None
    )
    assert status == 413 and json.loads(body) == {"detail": "REQUEST_TOO_LARGE"}


def test_the_413_replaces_a_crash_caused_by_the_failed_read():
    status, _, body, _ = asgi_call(
        limited(unexpected_error_on_read), "POST", "/x", [b"a" * 2000], content_length=None
    )
    assert status == 413


def test_an_unrelated_crash_is_not_turned_into_a_413():
    async def crashes(scope, receive, send):
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError, match="bug"):
        asgi_call(limited(crashes), "POST", "/x", [b"a"], content_length=None)


def test_when_the_answer_is_already_half_sent_the_error_is_not_hidden():
    with pytest.raises(Exception):
        asgi_call(limited(answers_before_reading), "POST", "/x", [b"a" * 2000], content_length=None)


def test_per_route_limits_are_matched_on_method_and_path():
    wrapped = limited(reads_everything, limit=10, limits={("POST", "/big"): 100})
    assert asgi_call(wrapped, "POST", "/big", [b"a" * 100])[0] == 200
    assert asgi_call(wrapped, "POST", "/big", [b"a" * 101])[0] == 413
    assert asgi_call(wrapped, "POST", "/small", [b"a" * 11])[0] == 413
    assert asgi_call(wrapped, "PUT", "/big", [b"a" * 11])[0] == 413
    assert asgi_call(wrapped, "POST", "/big/", [b"a" * 11])[0] == 413  # no loose matching


@pytest.mark.parametrize("value", ["abc", "-5", "1e3", "", "10 ", "+10"])
def test_a_malformed_content_length_is_refused(value):
    status, _, body, read = asgi_call(
        limited(reads_everything), "POST", "/x", [b"a"], content_length=value
    )
    assert status == 400 and json.loads(body) == {"detail": "INVALID_CONTENT_LENGTH"}
    assert read == 0


def test_two_different_content_lengths_are_refused():
    status, _, body, _ = asgi_call(
        limited(reads_everything), "POST", "/x", [b"a"],
        headers=[("content-length", "1"), ("content-length", "2")], content_length=None,
    )
    assert status == 400


def test_requests_without_a_body_are_untouched(client):
    assert client.get("/healthz").status_code == 200
    assert asgi_call(limited(reads_everything), "GET", "/x", [])[0] == 200


def test_the_size_check_comes_before_the_csrf_check(client):
    register_and_login(client)  # cookies in the jar, but no X-CSRF-Token below
    small = client.post("/_test/echo_len", content=b"x")
    assert small.status_code == 403 and small.json() == {"detail": "CSRF_FAILED"}
    big = client.post("/_test/echo_len", content=b"x" * (MiB + 1))
    assert big.status_code == 413


def test_an_oversized_login_is_refused_before_it_is_parsed(client):
    r = client.post(AUTH + "/login", json={"username": "budi", "password": "x" * (MiB + 10)})
    assert r.status_code == 413 and r.json() == {"detail": "REQUEST_TOO_LARGE"}


# --- the 422 body does not echo what was sent ----------------------------------


def only_public_keys(response):
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail
    for item in detail:
        assert set(item) <= {"type", "loc", "msg"}
        assert isinstance(item["loc"], list) and isinstance(item["msg"], str)
        assert isinstance(item["type"], str)
    assert PASSWORD not in response.text


@pytest.mark.parametrize(
    "send",
    [
        lambda c: c.post(AUTH + "/login", json={"username": "budi", "password": PASSWORD, "extra": PASSWORD}),
        lambda c: c.post(AUTH + "/login", json={"username": 7, "password": PASSWORD}),
        lambda c: c.post(AUTH + "/login", json={"username": "ab", "password": PASSWORD}),
        lambda c: c.post(AUTH + "/login", json=[PASSWORD]),
        lambda c: c.post(AUTH + "/login", content=('{"username": "budi", "password": "%s' % PASSWORD).encode(),
                         headers={"content-type": "application/json"}),
        lambda c: c.post(AUTH + "/register/alumni", json={"username": "budi", "password": PASSWORD[:7]}),
        lambda c: c.post(AUTH + "/register", json={
            "username": "budi", "password": PASSWORD, "profile": make_profile(nik="12345"),
        }),
        lambda c: c.post(AUTH + "/register", json={
            "username": "budi", "password": PASSWORD, "profile": {**make_profile(), "password": PASSWORD},
        }),
    ],
    ids=["extra-field", "wrong-type", "short-username", "array-body", "broken-json",
         "short-password", "bad-nik-in-profile", "extra-field-in-profile"],
)
def test_the_password_never_comes_back(client, send):
    r = send(client)
    assert r.status_code == 422
    only_public_keys(r)


def test_the_nik_and_email_of_a_rejected_profile_do_not_come_back(client):
    profile = make_profile(nik="31740000000000XY", email="rahasia-orang@example.com", phone="x")
    r = client.post(AUTH + "/register", json={"username": "budi", "password": "rahasia123", "profile": profile})
    assert r.status_code == 422
    assert "31740000000000XY" not in r.text and "rahasia-orang" not in r.text


def test_the_shape_the_front_end_reads_is_unchanged(client):
    r = client.post(AUTH + "/register/alumni", json={"username": "budi", "password": "pw"})
    assert r.status_code == 422
    assert r.json() == {
        "detail": [
            {"type": "value_error", "loc": ["body", "password"],
             "msg": "Value error, password must be 8-256 characters"}
        ]
    }


def test_loc_keeps_its_integers_and_query_parameters_are_covered(client):
    r = client.post(AUTH + "/login", content=b'{"username": "budi", "pass', headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "json_invalid"
    assert isinstance(r.json()["detail"][0]["loc"][1], int)
    r = client.get("/_test/needs_int", params={"n": PASSWORD})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["query", "n"]
    only_public_keys(r)


def test_the_422_raised_by_hand_in_the_profile_route_has_the_same_shape(client):
    headers = register_and_login(client)
    r = client.put("/api/v1/me/profile", json=make_profile(nik="SECRETNIK123456", full_name=""), headers=headers)
    assert r.status_code == 422
    only_public_keys(r)
    assert "SECRETNIK123456" not in r.text
    assert {tuple(i["loc"]) for i in r.json()["detail"]} >= {("body", "nik"), ("body", "full_name")}


def test_the_422_carries_the_four_headers_and_keeps_its_status(client):
    r = client.post(AUTH + "/login", json={})
    assert r.status_code == 422
    assert_secured(r)