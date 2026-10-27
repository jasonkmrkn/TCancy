from datetime import date, timedelta

from sqlalchemy import text

from app.db import engine
from helpers import make_alumni_profile, make_profile, skill_ids

AUTH = "/api/v1/auth"
URL = "/api/v1/jobs"


def make_user(client, username, role, status="active"):
    """Register a user, then force role and status directly in the database."""
    if role == "applicant":
        r = client.post(
            AUTH + "/register",
            json={"username": username, "password": "rahasia123", "profile": make_profile()},
        )
    else:
        r = client.post(
            AUTH + "/register/alumni",
            json={"username": username, "password": "rahasia123", "profile": make_alumni_profile()},
        )
    assert r.status_code == 201
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET role = :r, status = :s WHERE username = :u"),
            {"r": role, "s": status, "u": username},
        )
    return r.json()["id"]


def login(client, username):
    r = client.post(AUTH + "/login", json={"username": username, "password": "rahasia123"})
    assert r.status_code == 200


def as_user(client, username, role="alumni", status="active"):
    make_user(client, username, role, status)
    login(client, username)


def job_body(**over):
    data = {
        "title": "Backend Intern",
        "company": "Acme",
        "type": "internship",
        "work_mode": "remote",
        "location": "Surabaya",
        "description": "Build APIs",
        "requirements": "Python",
        "deadline": None,
        "skill_ids": [],
    }
    data.update(over)
    return data


def post_job(client, **over):
    return client.post(URL, json=job_body(**over))


def test_create_and_get_job(client):
    as_user(client, "alumni1")
    s = skill_ids(2)
    r = post_job(client, skill_ids=s, deadline=(date.today() + timedelta(days=5)).isoformat())
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open" and body["description"] == "Build APIs"
    assert sorted(x["id"] for x in body["skills"]) == sorted(s)
    assert set(body) == {
        "id", "title", "company", "type", "work_mode", "location", "deadline", "status",
        "skills", "created_at", "description", "requirements",
    }

    client.cookies.clear()  # public
    got = client.get("%s/%s" % (URL, body["id"]))
    assert got.status_code == 200 and got.json() == body


def test_get_unknown_job_404(client):
    for ident in ("00000000-0000-0000-0000-000000000000", "not-a-uuid"):
        r = client.get("%s/%s" % (URL, ident))
        assert r.status_code == 404 and r.json()["detail"] == "JOB_NOT_FOUND"


def test_only_active_alumni_or_admin_can_post(client):
    assert post_job(client).status_code == 401

    as_user(client, "pelamar", "applicant")
    assert post_job(client).status_code == 403
    client.post(AUTH + "/logout")

    as_user(client, "alumnibaru", "alumni", "pending")
    r = post_job(client)
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_PENDING"
    client.post(AUTH + "/logout")

    as_user(client, "admin1", "admin")
    assert post_job(client).status_code == 201


def test_validation_errors_422(client):
    as_user(client, "alumni1")
    past = (date.today() - timedelta(days=1)).isoformat()
    bad = [
        {"deadline": past},
        {"type": "volunteer"},
        {"work_mode": "office"},
        {"title": ""},
        {"title": "x" * 201},
        {"company": "x" * 201},
        {"location": "x" * 201},
        {"description": ""},
        {"description": "x" * 10001},
        {"requirements": "x" * 10001},
        {"skill_ids": ["00000000-0000-0000-0000-000000000000"]},
        {"skill_ids": [skill_ids(1)[0]] * 2},
        {"unknown": 1},
    ]
    for over in bad:
        assert post_job(client, **over).status_code == 422, over
    # deadline today is allowed, and 20 skills is the maximum
    assert post_job(client, deadline=date.today().isoformat()).status_code == 201
    assert post_job(client, skill_ids=skill_ids(20)).status_code == 201
    assert post_job(client, skill_ids=skill_ids(21)).status_code == 422


def test_update_only_by_owner(client):
    as_user(client, "alumni1")
    job = post_job(client).json()
    s = skill_ids(3)
    r = client.put("%s/%s" % (URL, job["id"]), json=job_body(title="New", skill_ids=s))
    assert r.status_code == 200
    assert r.json()["title"] == "New" and len(r.json()["skills"]) == 3
    r = client.put("%s/%s" % (URL, job["id"]), json=job_body(skill_ids=s[:1]))
    assert [x["id"] for x in r.json()["skills"]] == s[:1]
    client.post(AUTH + "/logout")

    as_user(client, "alumni2")
    r = client.put("%s/%s" % (URL, job["id"]), json=job_body())
    assert r.status_code == 403 and r.json()["detail"] == "NOT_JOB_OWNER"
    client.post(AUTH + "/logout")

    as_user(client, "admin1", "admin")  # admin is not the owner
    r = client.put("%s/%s" % (URL, job["id"]), json=job_body())
    assert r.status_code == 403 and r.json()["detail"] == "NOT_JOB_OWNER"

    r = client.put("%s/00000000-0000-0000-0000-000000000000" % URL, json=job_body())
    assert r.status_code == 404


def test_update_keeps_old_past_deadline(client):
    as_user(client, "alumni1")
    job = post_job(client).json()
    past = date.today() - timedelta(days=3)
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET deadline = :d"), {"d": past})
    url = "%s/%s" % (URL, job["id"])
    assert client.put(url, json=job_body(deadline=past.isoformat())).status_code == 200
    other = (past - timedelta(days=1)).isoformat()
    assert client.put(url, json=job_body(deadline=other)).status_code == 422


def test_close_job(client):
    as_user(client, "alumni1")
    job = post_job(client).json()
    url = "%s/%s" % (URL, job["id"])
    client.post(AUTH + "/logout")

    as_user(client, "alumni2")
    r = client.post(url + "/close")
    assert r.status_code == 403 and r.json()["detail"] == "NOT_JOB_OWNER"
    client.post(AUTH + "/logout")

    as_user(client, "admin1", "admin")  # admin may close any job
    r = client.post(url + "/close")
    assert r.status_code == 200 and r.json()["status"] == "closed"
    r = client.post(url + "/close")
    assert r.status_code == 409 and r.json()["detail"] == "JOB_CLOSED"
    client.post(AUTH + "/logout")

    login(client, "alumni1")
    r = client.put(url, json=job_body())
    assert r.status_code == 409 and r.json()["detail"] == "JOB_CLOSED"
    # closed jobs are still readable
    assert client.get(url).json()["status"] == "closed"
    assert client.post("%s/00000000-0000-0000-0000-000000000000/close" % URL).status_code == 404


def test_owner_closes_own_job(client):
    as_user(client, "alumni1")
    job = post_job(client).json()
    r = client.post("%s/%s/close" % (URL, job["id"]))
    assert r.status_code == 200 and r.json()["status"] == "closed"


def test_my_jobs(client):
    as_user(client, "alumni1")
    a = post_job(client, title="A").json()
    b = post_job(client, title="B").json()
    client.post(AUTH + "/logout")
    as_user(client, "alumni2")
    post_job(client, title="C")
    client.post(AUTH + "/logout")

    login(client, "alumni1")
    got = client.get("/api/v1/me/jobs")
    assert got.status_code == 200
    assert [j["id"] for j in got.json()] == [b["id"], a["id"]]
    assert "description" not in got.json()[0]
    client.post(AUTH + "/logout")

    as_user(client, "pelamar", "applicant")
    assert client.get("/api/v1/me/jobs").status_code == 403
    client.post(AUTH + "/logout")
    assert client.get("/api/v1/me/jobs").status_code == 401


def test_filters(client):
    as_user(client, "alumni1")
    s = skill_ids(3)
    post_job(client, title="Python Dev", company="Alpha", type="fulltime", work_mode="onsite",
             location="Jakarta", skill_ids=[s[0]])
    post_job(client, title="Data Intern", company="Beta", type="internship", work_mode="remote",
             location="Surabaya", skill_ids=[s[1]], description="100% growth_x")
    post_job(client, title="Designer", company="Gamma", type="internship", work_mode="hybrid",
             location=None, skill_ids=[s[0], s[1]])
    client.cookies.clear()

    def titles(**params):
        r = client.get(URL, params=params)
        assert r.status_code == 200, r.text
        return sorted(j["title"] for j in r.json()["items"])

    assert titles() == ["Data Intern", "Designer", "Python Dev"]
    assert titles(type="internship") == ["Data Intern", "Designer"]
    assert titles(work_mode="remote") == ["Data Intern"]
    assert titles(type="internship", work_mode="hybrid") == ["Designer"]
    assert titles(q="python") == ["Python Dev"]
    assert titles(q="GAMMA") == ["Designer"]
    assert titles(q="growth_x") == ["Data Intern"]
    assert titles(q="100%") == ["Data Intern"]
    assert titles(q="%") == ["Data Intern"]
    assert titles(location="jakar") == ["Python Dev"]
    assert titles(skill=[s[0]]) == ["Designer", "Python Dev"]
    assert titles(skill=[s[1], s[2]]) == ["Data Intern", "Designer"]
    assert titles(q="nothing-matches") == []


def test_filter_validation(client):
    assert client.get(URL, params={"q": "x" * 101}).status_code == 422
    assert client.get(URL, params={"location": "x" * 101}).status_code == 422
    assert client.get(URL, params={"limit": 0}).status_code == 422
    assert client.get(URL, params={"limit": 51}).status_code == 422
    assert client.get(URL, params={"skill": "nope"}).status_code == 422
    assert client.get(URL, params={"skill": skill_ids(21)}).status_code == 422
    assert client.get(URL, params={"skill": skill_ids(20)}).status_code == 200
    assert client.get(URL, params={"cursor": "garbage"}).status_code == 422


def test_cursor_pagination(client):
    as_user(client, "alumni1")
    ids = [post_job(client, title="J%d" % i).json()["id"] for i in range(5)]
    client.cookies.clear()
    expected = list(reversed(ids))

    seen = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get(URL, params=params).json()
        assert set(body) == {"items", "next_cursor"}
        seen += [j["id"] for j in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert pages == 3 and seen == expected

    exact = client.get(URL, params={"limit": 5}).json()
    assert exact["next_cursor"] is None and len(exact["items"]) == 5
    assert len(client.get(URL).json()["items"]) == 5


def test_cursor_with_filter_and_equal_timestamps(client):
    as_user(client, "alumni1")
    for i in range(4):
        post_job(client, title="J%d" % i)
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET created_at = now()"))  # identical timestamps
    client.cookies.clear()
    seen = []
    cursor = None
    while True:
        params = {"limit": 3, "type": "internship"}
        if cursor:
            params["cursor"] = cursor
        body = client.get(URL, params=params).json()
        seen += [j["id"] for j in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 4 and len(set(seen)) == 4


def test_deleting_owner_removes_jobs(client):
    uid = make_user(client, "alumni1", "alumni")
    login(client, "alumni1")
    job = post_job(client).json()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})
    assert client.get("%s/%s" % (URL, job["id"])).status_code == 404
