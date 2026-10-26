from sqlalchemy import text

from app.db import engine
from helpers import skill_ids, CONSENTS
from test_document import upload
from test_job import as_user, job_body, login, make_user
from test_owner import apply_as, new_owner

URL = "/api/v1"


def post_job(client, skills, **over):
    r = client.post(URL + "/jobs", json=job_body(skill_ids=skills, **over))
    assert r.status_code == 201
    return r.json()["id"]


def sql(query, **params):
    with engine.begin() as conn:
        conn.execute(text(query), params)


def alumni_with_jobs(client, specs):
    """Log in as alumni, create jobs for each skill list, log out. Returns the job ids."""
    as_user(client, "boss", "alumni")
    ids = [post_job(client, s, title="Job %d" % i) for i, s in enumerate(specs)]
    client.post(URL + "/auth/logout")
    return ids


def test_matches_require_applicant(client):
    assert client.get(URL + "/me/matches").status_code == 401
    assert client.get(URL + "/me/dashboard").status_code == 401
    as_user(client, "alum", "alumni")
    assert client.get(URL + "/me/matches").status_code == 403
    assert client.get(URL + "/me/dashboard").status_code == 403


def test_matches_score_order_and_filters(client):
    a, b, c = skill_ids(3)
    both, one, none, closed, expired, applied = alumni_with_jobs(
        client, [[a, b], [a], [c], [a, b], [a, b], [a, b]]
    )
    sql("UPDATE jobs SET status = 'closed' WHERE id = :i", i=closed)
    sql("UPDATE jobs SET deadline = current_date - 1 WHERE id = :i", i=expired)

    as_user(client, "budi", "applicant")  # profile skills are the first two: a and b
    cv = upload(client, "cv", "cv.pdf", b"%PDF-1.4").json()["id"]
    r = client.post("%s/jobs/%s/apply" % (URL, applied), json={"cv_document_id": cv, "consents": CONSENTS})
    assert r.status_code == 201

    r = client.get(URL + "/me/matches")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["job"]["id"] for i in items] == [both, one]
    assert [i["score"] for i in items] == [2, 1]
    assert {s["id"] for s in items[0]["matched_skills"]} == {a, b}
    assert [s["id"] for s in items[1]["matched_skills"]] == [a]
    assert set(items[0]) == {"job", "score", "matched_skills"}
    assert none not in [i["job"]["id"] for i in items]


def test_matches_equal_score_newest_first_and_limit(client):
    a = skill_ids(1)[0]
    first, second, third = alumni_with_jobs(client, [[a], [a], [a]])
    as_user(client, "budi", "applicant")
    items = client.get(URL + "/me/matches").json()["items"]
    assert [i["job"]["id"] for i in items] == [third, second, first]
    items = client.get(URL + "/me/matches?limit=2").json()["items"]
    assert [i["job"]["id"] for i in items] == [third, second]
    assert client.get(URL + "/me/matches?limit=0").status_code == 422
    assert client.get(URL + "/me/matches?limit=51").status_code == 422


def test_matches_empty_when_nothing_shared(client):
    alumni_with_jobs(client, [[skill_ids(3)[2]], []])
    as_user(client, "budi", "applicant")
    assert client.get(URL + "/me/matches").json() == {"items": []}


def test_withdrawn_application_still_excluded(client):
    a = skill_ids(1)[0]
    (job,) = alumni_with_jobs(client, [[a]])
    as_user(client, "budi", "applicant")
    cv = upload(client, "cv", "cv.pdf", b"%PDF-1.4").json()["id"]
    app_id = client.post("%s/jobs/%s/apply" % (URL, job), json={"cv_document_id": cv, "consents": CONSENTS}).json()["id"]
    assert len(client.get(URL + "/me/matches").json()["items"]) == 0
    client.delete("%s/me/applications/%s" % (URL, app_id))
    assert client.get(URL + "/me/matches").json()["items"] == []


def test_applicant_dashboard_empty(client):
    as_user(client, "budi", "applicant")
    r = client.get(URL + "/me/dashboard")
    assert r.status_code == 200
    assert r.json() == {
        "applications": {"submitted": 0, "shortlisted": 0, "accepted": 0, "rejected": 0, "withdrawn": 0},
        "documents": {"cv": 0, "ktp": 0, "intro_video": 0},
        "recent_applications": [],
        "matches": [],
    }


def test_applicant_dashboard_counts(client):
    a = skill_ids(1)[0]
    jobs = alumni_with_jobs(client, [[a]] * 7)
    as_user(client, "budi", "applicant")
    cv = upload(client, "cv", "cv.pdf", b"%PDF-1.4").json()["id"]
    upload(client, "ktp", "ktp.png", b"\x89PNG\r\n\x1a\n")
    app_ids = []
    for job in jobs[:6]:
        r = client.post("%s/jobs/%s/apply" % (URL, job), json={"cv_document_id": cv, "consents": CONSENTS})
        app_ids.append(r.json()["id"])
    client.delete("%s/me/applications/%s" % (URL, app_ids[0]))
    sql("UPDATE applications SET status = 'accepted' WHERE id = :i", i=app_ids[1])

    body = client.get(URL + "/me/dashboard").json()
    assert body["applications"] == {
        "submitted": 4, "shortlisted": 0, "accepted": 1, "rejected": 0, "withdrawn": 1,
    }
    assert body["documents"] == {"cv": 1, "ktp": 1, "intro_video": 0}
    assert len(body["recent_applications"]) == 5
    assert body["recent_applications"][0]["id"] == app_ids[5]
    assert set(body["recent_applications"][0]) == {"id", "status", "created_at", "job"}
    assert [m["job"]["id"] for m in body["matches"]] == [jobs[6]]


def test_dashboard_matches_top_three(client):
    a = skill_ids(1)[0]
    jobs = alumni_with_jobs(client, [[a]] * 5)
    as_user(client, "budi", "applicant")
    body = client.get(URL + "/me/dashboard").json()
    assert [m["job"]["id"] for m in body["matches"]] == [jobs[4], jobs[3], jobs[2]]


def test_owner_dashboard_access(client):
    assert client.get(URL + "/owner/dashboard").status_code == 401
    as_user(client, "budi", "applicant")
    assert client.get(URL + "/owner/dashboard").status_code == 403
    client.post(URL + "/auth/logout")
    make_user(client, "pend", "alumni", "pending")
    login(client, "pend")
    r = client.get(URL + "/owner/dashboard")
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_PENDING"


def test_owner_dashboard_empty_for_admin(client):
    as_user(client, "root", "admin")
    assert client.get(URL + "/owner/dashboard").json() == {
        "jobs": {"open": 0, "closed": 0},
        "applications": {"submitted": 0, "shortlisted": 0, "accepted": 0, "rejected": 0, "withdrawn": 0},
        "new_applications": 0,
    }


def test_owner_dashboard_counts_only_own_jobs(client):
    owner, job_id = new_owner(client)
    _, other_job = new_owner(client)
    first = apply_as(client, job_id, "budi")
    apply_as(client, other_job, "sari")
    client.post(URL + "/auth/logout")
    apply_as(client, job_id, "andi")
    client.post(URL + "/auth/logout")
    login(client, owner)
    second_job = post_job(client, [])
    client.post("%s/jobs/%s/close" % (URL, second_job))

    body = client.get(URL + "/owner/dashboard").json()
    assert body["jobs"] == {"open": 1, "closed": 1}
    assert body["applications"]["submitted"] == 2
    assert body["new_applications"] == 2

    r = client.patch("%s/applications/%s/status" % (URL, first), json={"status": "shortlisted"})
    assert r.status_code == 200
    body = client.get(URL + "/owner/dashboard").json()
    assert body["applications"]["shortlisted"] == 1
    assert body["applications"]["submitted"] == 1
    assert body["new_applications"] == 1

    sql("UPDATE applications SET created_at = now() - interval '10 days'")
    assert client.get(URL + "/owner/dashboard").json()["new_applications"] == 0
