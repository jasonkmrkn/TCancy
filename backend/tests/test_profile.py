from datetime import date

import pytest
from sqlalchemy import text

from app.db import engine
from helpers import make_alumni_profile, make_profile, password_hash, skill_ids

AUTH = "/api/v1/auth"


def register(client, username="budi", **over):
    return client.post(
        AUTH + "/register",
        json={"username": username, "password": "rahasia123", "profile": make_profile(**over)},
    )


def login(client, username="budi"):
    r = client.post(AUTH + "/login", json={"username": username, "password": "rahasia123"})
    assert r.status_code == 200
    return r


def register_alumni(client, username="alumna"):
    r = client.post(
        AUTH + "/register/alumni",
        json={"username": username, "password": "rahasia123", "profile": make_alumni_profile()},
    )
    assert r.status_code == 201
    login(client, username)


def test_skills_list(client):
    r = client.get("/api/v1/skills")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 40
    assert set(items[0]) == {"id", "name"}


def test_register_saves_profile_and_reads_back(client):
    ids = skill_ids(3)
    assert register(client, skill_ids=ids, preferred_type=None, preferred_location=None).status_code == 201
    login(client)
    r = client.get("/api/v1/me/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "applicant"
    assert body["full_name"] == "Budi Santoso"
    assert body["birth_date"] == "2000-05-17"
    assert body["angkatan"] == 2019
    assert body["preferred_type"] is None
    assert {s["id"] for s in body["skills"]} == set(ids)
    assert all(s["name"] for s in body["skills"])


def test_put_replaces_profile(client):
    register(client)
    login(client)
    ids = skill_ids(5)[3:]
    new = make_profile(full_name="Budi Baru", skill_ids=ids, preferred_type="fulltime")
    r = client.put("/api/v1/me/profile", json=new)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Budi Baru"
    assert {s["id"] for s in r.json()["skills"]} == set(ids)
    assert client.get("/api/v1/me/profile").json() == r.json()


def test_put_keeping_own_email_and_nik_is_ok(client):
    data = make_profile()
    client.post(AUTH + "/register", json={"username": "budi", "password": "rahasia123", "profile": data})
    login(client)
    assert client.put("/api/v1/me/profile", json=data).status_code == 200


def test_put_unknown_field_422(client):
    register(client)
    login(client)
    r = client.put("/api/v1/me/profile", json=make_profile(role="admin"))
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


def test_register_unknown_field_422(client):
    data = make_profile()
    data["extra"] = 1
    r = client.post(AUTH + "/register", json={"username": "budi", "password": "rahasia123", "profile": data})
    assert r.status_code == 422


def test_register_requires_profile(client):
    r = client.post(AUTH + "/register", json={"username": "budi", "password": "rahasia123"})
    assert r.status_code == 422


def test_duplicate_email_and_nik_409(client):
    first = make_profile()
    client.post(AUTH + "/register", json={"username": "budi", "password": "rahasia123", "profile": first})
    r = register(client, "siti", email=first["email"].upper())
    assert r.status_code == 409 and r.json()["detail"] == "EMAIL_TAKEN"
    r = register(client, "siti", nik=first["nik"])
    assert r.status_code == 409 and r.json()["detail"] == "NIK_TAKEN"
    # the failed registration must not leave a user behind
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users WHERE username='siti'")).scalar() == 0
    assert register(client, "siti").status_code == 201


def test_put_duplicate_email_and_nik_409(client):
    other = make_profile()
    client.post(AUTH + "/register", json={"username": "budi", "password": "rahasia123", "profile": other})
    register(client, "siti")
    login(client, "siti")
    r = client.put("/api/v1/me/profile", json=make_profile(email=other["email"]))
    assert r.status_code == 409 and r.json()["detail"] == "EMAIL_TAKEN"
    r = client.put("/api/v1/me/profile", json=make_profile(nik=other["nik"]))
    assert r.status_code == 409 and r.json()["detail"] == "NIK_TAKEN"


def test_register_unknown_skill_422(client):
    r = register(client, skill_ids=["00000000-0000-0000-0000-000000000001"])
    assert r.status_code == 422
    r = register(client, "siti")
    assert r.status_code == 201


def _age_date(years):
    today = date.today()
    return today.replace(year=today.year - years, day=1).isoformat()


@pytest.mark.parametrize(
    "field,value",
    [
        ("full_name", ""),
        ("full_name", "x" * 201),
        ("email", "not-an-email"),
        ("email", "a" * 250 + "@b.co"),
        ("phone", "1234567"),
        ("phone", "1" * 16),
        ("phone", "0812abc4567"),
        ("nik", "123"),
        ("nik", "1" * 17),
        ("nik", "12345678901234ab"),
        ("address", "x" * 501),
        ("birth_date", _age_date(10)),
        ("birth_date", _age_date(101)),
        ("angkatan", 1989),
        ("angkatan", date.today().year + 1),
        ("skill_ids", []),
        ("skill_ids", "dupe"),
        ("preferred_type", "bogus"),
        ("preferred_location", "x" * 101),
    ],
)
def test_profile_validation(client, field, value):
    if value == "dupe":
        value = skill_ids(1) * 2
    assert register(client, **{field: value}).status_code == 422


def test_skill_count_limit(client):
    assert register(client, skill_ids=skill_ids(31)).status_code == 422
    assert register(client, skill_ids=skill_ids(30)).status_code == 201


def test_phone_boundaries(client):
    assert register(client, "a1a", phone="12345678").status_code == 201
    assert register(client, "a2a", phone="+" + "1" * 15).status_code == 201


def test_profile_requires_login(client):
    assert client.get("/api/v1/me/profile").status_code == 401
    assert client.put("/api/v1/me/profile", json=make_profile()).status_code == 401


def test_admin_forbidden(client):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES ('boss', :h, 'admin')"),
            {"h": password_hash()},
        )
    login(client, "boss")
    assert client.get("/api/v1/me/profile").status_code == 403


def test_inactive_applicant_put_403(client):
    register(client)
    login(client)
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET status='pending' WHERE username='budi'"))
    r = client.put("/api/v1/me/profile", json=make_profile())
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_PENDING"
    assert client.get("/api/v1/me/profile").status_code == 200


def test_alumni_pending_reads_and_updates_profile(client):
    register_alumni(client)
    r = client.get("/api/v1/me/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "alumni"
    assert body["full_name"] == "Sari Alumni"
    assert body["profile_complete"] is True
    assert body["verification"]["state"] == "pending"

    r = client.put(
        "/api/v1/me/profile", json={"full_name": "Ani Alumni", "company": "Globex", "angkatan": 2016}
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Ani Alumni"
    again = client.get("/api/v1/me/profile").json()
    assert again["company"] == "Globex" and again["angkatan"] == 2016

    # An empty body clears the profile: the name reads back as null and it is incomplete.
    assert client.put("/api/v1/me/profile", json={}).status_code == 200
    cleared = client.get("/api/v1/me/profile").json()
    assert cleared["full_name"] is None
    assert cleared["profile_complete"] is False


def test_alumni_profile_validation(client):
    register_alumni(client)
    put = lambda body: client.put("/api/v1/me/profile", json=body).status_code  # noqa: E731
    assert put({"company": "x" * 201}) == 422
    assert put({"angkatan": 1980}) == 422
    assert put({"full_name": "A", "bogus": 1}) == 422
    assert put({"full_name": "A"}) == 200
