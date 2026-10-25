import pytest
from fastapi import Depends
from sqlalchemy import select, text

from app.db import SessionLocal, engine
from app.deps import require_role
from app.main import app
from app.models import Session as SessionRow
from app.models import User
from helpers import make_profile

BASE = "/api/v1/auth"


# Probe routes to exercise the role/status dependency (real routes arrive in later stages).
@app.get("/_test/applicant")
def _applicant_only(user: User = Depends(require_role("applicant"))):
    return {"ok": True}


@app.get("/_test/alumni_pending_ok")
def _alumni_pending(user: User = Depends(require_role("alumni", allow_pending=True))):
    return {"ok": True}


def register(client, username="budi", password="rahasia123"):
    return client.post(
        BASE + "/register",
        json={"username": username, "password": password, "profile": make_profile()},
    )


def login(client, username="budi", password="rahasia123"):
    return client.post(BASE + "/login", json={"username": username, "password": password})


def set_sql(sql):
    with engine.begin() as conn:
        conn.execute(text(sql))


def test_register_applicant(client):
    r = register(client, "  Budi  ")
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "budi"
    assert body["role"] == "applicant"
    assert body["status"] == "active"
    assert "password" not in body


def test_register_duplicate(client):
    register(client)
    r = register(client, "BUDI")
    assert r.status_code == 409
    assert r.json()["detail"] == "USERNAME_TAKEN"


@pytest.mark.parametrize(
    "username,password",
    [("ab", "rahasia123"), ("x" * 65, "rahasia123"), ("bu\x07di", "rahasia123"),
     ("budi", "short"), ("budi", "p" * 257)],
)
def test_register_validation(client, username, password):
    assert register(client, username, password).status_code == 422


def test_register_alumni_pending(client):
    r = client.post(BASE + "/register/alumni", json={"username": "alum", "password": "rahasia123"})
    assert r.status_code == 201
    assert r.json()["role"] == "alumni"
    assert r.json()["status"] == "pending"


def test_login_sets_cookie_and_me(client):
    register(client)
    r = login(client)
    assert r.status_code == 200
    assert r.json()["username"] == "budi"
    assert "access_token" in client.cookies
    me = client.get(BASE + "/me")
    assert me.status_code == 200
    assert me.json() == r.json()
    with SessionLocal() as db:
        rows = db.scalars(select(SessionRow)).all()
        assert len(rows) == 1
        assert rows[0].token == client.cookies["access_token"]
        assert db.scalar(select(User.last_login_at)) is not None


def test_login_wrong_credentials(client):
    register(client)
    for u, p in [("budi", "salahsalah"), ("nobody", "rahasia123")]:
        r = login(client, u, p)
        assert r.status_code == 401
        assert r.json()["detail"] == "invalid username or password"
    assert "access_token" not in client.cookies


def test_login_suspended(client):
    register(client)
    set_sql("UPDATE users SET status='suspended'")
    r = login(client)
    assert r.status_code == 403
    assert r.json()["detail"] == "ACCOUNT_SUSPENDED"


def test_suspended_existing_session_blocked(client):
    register(client)
    login(client)
    set_sql("UPDATE users SET status='suspended'")
    r = client.get(BASE + "/me")
    assert r.status_code == 403
    assert r.json()["detail"] == "ACCOUNT_SUSPENDED"


def test_logout_deletes_session(client):
    register(client)
    login(client)
    token = client.cookies["access_token"]
    r = client.post(BASE + "/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    with SessionLocal() as db:
        assert db.scalar(select(SessionRow).where(SessionRow.token == token)) is None
    client.cookies.set("access_token", token)
    assert client.get(BASE + "/me").status_code == 401


def test_not_logged_in(client):
    for method, path in [("get", "/me"), ("post", "/logout")]:
        r = getattr(client, method)(BASE + path)
        assert r.status_code == 401
        assert r.json()["detail"] == "not logged in"
    assert client.get("/_test/applicant").status_code == 401


def test_bogus_token(client):
    client.cookies.set("access_token", "nonsense")
    assert client.get(BASE + "/me").status_code == 401


def test_wrong_role_forbidden(client):
    client.post(BASE + "/register/alumni", json={"username": "alum", "password": "rahasia123"})
    login(client, "alum")
    r = client.get("/_test/applicant")
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden"


def test_pending_status(client):
    client.post(BASE + "/register/alumni", json={"username": "alum", "password": "rahasia123"})
    login(client, "alum")
    assert client.get(BASE + "/me").status_code == 200
    assert client.get("/_test/alumni_pending_ok").status_code == 200
    set_sql("UPDATE users SET role='applicant'")
    r = client.get("/_test/applicant")
    assert r.status_code == 403
    assert r.json()["detail"] == "ACCOUNT_PENDING"
