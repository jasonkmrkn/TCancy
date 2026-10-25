from sqlalchemy import text

from app.db import engine
from helpers import make_profile

AUTH = "/api/v1/auth"
URL = "/api/v1/me/account"


def register_applicant(client, username="budi"):
    r = client.post(
        AUTH + "/register",
        json={"username": username, "password": "rahasia123", "profile": make_profile()},
    )
    assert r.status_code == 201
    return r.json()["id"]


def register_alumni(client, username="alumna"):
    r = client.post(AUTH + "/register/alumni", json={"username": username, "password": "rahasia123"})
    assert r.status_code == 201
    return r.json()["id"]


def login(client, username):
    r = client.post(AUTH + "/login", json={"username": username, "password": "rahasia123"})
    assert r.status_code == 200


def delete(client, password="rahasia123"):
    return client.request("DELETE", URL, json={"password": password})


def count(sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def test_delete_applicant_removes_related_rows(client):
    uid = register_applicant(client)
    other = register_applicant(client, "siti")
    login(client, "budi")
    assert count("SELECT count(*) FROM applicant_skills WHERE user_id = :u", u=uid) == 2

    r = delete(client)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    for table, col in [
        ("users", "id"),
        ("applicant_profiles", "user_id"),
        ("applicant_skills", "user_id"),
        ("sessions", "user_id"),
    ]:
        assert count("SELECT count(*) FROM %s WHERE %s = :u" % (table, col), u=uid) == 0
    # the other user is untouched
    assert count("SELECT count(*) FROM applicant_profiles WHERE user_id = :u", u=other) == 1
    assert count("SELECT count(*) FROM applicant_skills WHERE user_id = :u", u=other) == 2


def test_session_is_gone_after_delete(client):
    register_applicant(client)
    login(client, "budi")
    assert delete(client).status_code == 200
    assert client.get(AUTH + "/me").status_code == 401


def test_username_can_be_reused_after_delete(client):
    register_applicant(client)
    login(client, "budi")
    assert delete(client).status_code == 200
    register_applicant(client)


def test_wrong_password_403_and_nothing_deleted(client):
    uid = register_applicant(client)
    login(client, "budi")
    r = delete(client, "salah-salah")
    assert r.status_code == 403
    assert r.json() == {"detail": "INVALID_PASSWORD"}
    assert count("SELECT count(*) FROM users WHERE id = :u", u=uid) == 1
    assert client.get(AUTH + "/me").status_code == 200


def test_missing_or_unknown_body_fields_422(client):
    register_applicant(client)
    login(client, "budi")
    assert client.request("DELETE", URL).status_code == 422
    assert client.request("DELETE", URL, json={}).status_code == 422
    assert client.request("DELETE", URL, json={"password": "rahasia123", "x": 1}).status_code == 422
    assert count("SELECT count(*) FROM users") == 1


def test_not_logged_in_401(client):
    assert delete(client).status_code == 401


def test_pending_alumni_can_delete(client):
    uid = register_alumni(client)
    login(client, "alumna")
    assert count("SELECT count(*) FROM alumni_profiles WHERE user_id = :u", u=uid) == 1
    assert delete(client).status_code == 200
    assert count("SELECT count(*) FROM users WHERE id = :u", u=uid) == 0
    assert count("SELECT count(*) FROM alumni_profiles WHERE user_id = :u", u=uid) == 0


def test_admin_forbidden(client):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (username, password, role) VALUES ('root', 'rahasia123', 'admin')")
        )
    login(client, "root")
    r = delete(client)
    assert r.status_code == 403
    assert r.json() == {"detail": "forbidden"}
    assert count("SELECT count(*) FROM users WHERE username = 'root'") == 1


def test_suspended_user_cannot_delete(client):
    uid = register_applicant(client)
    login(client, "budi")
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET status = 'suspended' WHERE id = :u"), {"u": uid})
    r = delete(client)
    assert r.status_code == 403
    assert r.json() == {"detail": "ACCOUNT_SUSPENDED"}
