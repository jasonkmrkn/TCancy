import itertools
from datetime import date, timedelta

from sqlalchemy import text

from app.db import engine
from helpers import CONSENTS, CONSENTS_WITH_VIDEO
from test_job import as_user, job_body, login, make_user
from test_document import upload

URL = "/api/v1"
_owners = itertools.count(1)


def make_job(client, **over):
    """Create a job as a fresh alumni, then log out. Returns the job id."""
    name = "owner%d" % next(_owners)
    as_user(client, name, "alumni")
    r = client.post(URL + "/jobs", json=job_body(**over))
    assert r.status_code == 201
    client.post(URL + "/auth/logout")
    return r.json()["id"]


def applicant_with_docs(client, username="budi"):
    as_user(client, username, "applicant")
    cv = upload(client, "cv", "cv.pdf", b"%PDF-1.4 cv").json()["id"]
    video = upload(client, "intro_video", "v.mp4", b"\x00\x00\x00\x18ftypmp42 video").json()["id"]
    return cv, video


def test_apply_success_and_views(client):
    job_id = make_job(client)
    cv, video = applicant_with_docs(client)
    r = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={
            "cv_document_id": cv,
            "intro_video_document_id": video,
            "cover_note": "Hi",
            "consents": CONSENTS_WITH_VIDEO,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "submitted" and body["cover_note"] == "Hi"
    assert body["cv_document_id"] == cv and body["intro_video_document_id"] == video
    assert body["job"]["id"] == job_id
    assert [h["to_status"] for h in body["history"]] == ["submitted"]
    assert body["history"][0]["from_status"] is None

    lst = client.get(URL + "/me/applications").json()
    assert len(lst) == 1 and set(lst[0]) == {"id", "status", "created_at", "job"}
    one = client.get("%s/me/applications/%s" % (URL, body["id"]))
    assert one.status_code == 200 and one.json()["id"] == body["id"]


def test_apply_without_optional_fields(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    r = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={"cv_document_id": cv, "consents": CONSENTS},
    )
    assert r.status_code == 201
    assert r.json()["intro_video_document_id"] is None and r.json()["cover_note"] is None


def test_apply_validation(client):
    job_id = make_job(client)
    cv, video = applicant_with_docs(client)
    path = "%s/jobs/%s/apply" % (URL, job_id)
    assert client.post(path, json={}).status_code == 422
    assert client.post(
        path, json={"cv_document_id": cv, "consents": CONSENTS, "cover_note": "x" * 2001}
    ).status_code == 422
    assert client.post(
        path, json={"cv_document_id": cv, "consents": CONSENTS, "extra": 1}
    ).status_code == 422
    # wrong document type in either slot
    assert client.post(
        path, json={"cv_document_id": video, "consents": CONSENTS}
    ).status_code == 422
    assert client.post(
        path,
        json={"cv_document_id": cv, "intro_video_document_id": cv, "consents": CONSENTS_WITH_VIDEO},
    ).status_code == 422
    # unknown document
    r = client.post(
        path,
        json={"cv_document_id": "00000000-0000-0000-0000-000000000000", "consents": CONSENTS},
    )
    assert r.status_code == 422 and r.json()["detail"] == "invalid document"
    assert client.get(URL + "/me/applications").json() == []


def test_apply_other_users_document_rejected(client):
    job_id = make_job(client)
    other_cv, _ = applicant_with_docs(client, "other")
    client.post(URL + "/auth/logout")
    applicant_with_docs(client, "budi")
    r = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={"cv_document_id": other_cv, "consents": CONSENTS},
    )
    assert r.status_code == 422


def test_apply_job_errors(client):
    cv, _ = applicant_with_docs(client)
    body = {"cv_document_id": cv, "consents": CONSENTS}
    assert client.post(URL + "/jobs/00000000-0000-0000-0000-000000000000/apply", json=body).status_code == 404
    r = client.post(URL + "/jobs/not-a-uuid/apply", json=body)
    assert r.status_code == 404 and r.json()["detail"] == "JOB_NOT_FOUND"

    client.post(URL + "/auth/logout")
    closed = make_job(client)
    expired = make_job(client)
    login(client, "budi")
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET status = 'closed' WHERE id = :i"), {"i": closed})
        conn.execute(
            text("UPDATE jobs SET deadline = :d WHERE id = :i"),
            {"d": date.today() - timedelta(days=1), "i": expired},
        )
    r = client.post("%s/jobs/%s/apply" % (URL, closed), json=body)
    assert r.status_code == 409 and r.json()["detail"] == "JOB_CLOSED"
    r = client.post("%s/jobs/%s/apply" % (URL, expired), json=body)
    assert r.status_code == 409 and r.json()["detail"] == "JOB_EXPIRED"


def test_deadline_today_is_allowed(client):
    job_id = make_job(client, deadline=date.today().isoformat())
    cv, _ = applicant_with_docs(client)
    r = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={"cv_document_id": cv, "consents": CONSENTS},
    )
    assert r.status_code == 201


def test_already_applied(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    path = "%s/jobs/%s/apply" % (URL, job_id)
    body = {"cv_document_id": cv, "consents": CONSENTS}
    assert client.post(path, json=body).status_code == 201
    r = client.post(path, json=body)
    assert r.status_code == 409 and r.json()["detail"] == "ALREADY_APPLIED"
    # also after withdrawing: one application per job per applicant
    app_id = client.get(URL + "/me/applications").json()[0]["id"]
    client.delete("%s/me/applications/%s" % (URL, app_id))
    assert client.post(path, json=body).status_code == 409


def test_roles_and_auth(client):
    job_id = make_job(client)
    path = "%s/jobs/%s/apply" % (URL, job_id)
    body = {"cv_document_id": "00000000-0000-0000-0000-000000000000"}
    assert client.post(path, json=body).status_code == 401
    assert client.get(URL + "/me/applications").status_code == 401
    as_user(client, "alum", "alumni")
    assert client.post(path, json=body).status_code == 403
    assert client.get(URL + "/me/applications").status_code == 403
    client.post(URL + "/auth/logout")
    as_user(client, "pend", "applicant", status="pending")
    r = client.post(path, json=body)
    assert r.status_code == 403 and r.json()["detail"] == "ACCOUNT_PENDING"


def test_other_users_application_is_404(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client, "budi")
    app_id = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={"cv_document_id": cv, "consents": CONSENTS},
    ).json()["id"]
    client.post(URL + "/auth/logout")
    as_user(client, "siti", "applicant")
    for r in (
        client.get("%s/me/applications/%s" % (URL, app_id)),
        client.delete("%s/me/applications/%s" % (URL, app_id)),
        client.get(URL + "/me/applications/not-a-uuid"),
    ):
        assert r.status_code == 404 and r.json()["detail"] == "APPLICATION_NOT_FOUND"
    assert client.get(URL + "/me/applications").json() == []


def test_withdraw_records_history_and_is_final(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    app_id = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={"cv_document_id": cv, "consents": CONSENTS},
    ).json()["id"]
    r = client.delete("%s/me/applications/%s" % (URL, app_id))
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    hist = r.json()["history"]
    assert [(h["from_status"], h["to_status"]) for h in hist] == [
        (None, "submitted"), ("submitted", "withdrawn"),
    ]
    r = client.delete("%s/me/applications/%s" % (URL, app_id))
    assert r.status_code == 409 and r.json()["detail"] == "INVALID_STATUS"


def test_withdraw_rejected_is_invalid(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    app_id = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={"cv_document_id": cv, "consents": CONSENTS},
    ).json()["id"]
    with engine.begin() as conn:
        conn.execute(text("UPDATE applications SET status = 'rejected'"))
    r = client.delete("%s/me/applications/%s" % (URL, app_id))
    assert r.status_code == 409 and r.json()["detail"] == "INVALID_STATUS"


def test_withdraw_shortlisted_allowed(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    app_id = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={"cv_document_id": cv, "consents": CONSENTS},
    ).json()["id"]
    with engine.begin() as conn:
        conn.execute(text("UPDATE applications SET status = 'shortlisted'"))
    r = client.delete("%s/me/applications/%s" % (URL, app_id))
    assert r.status_code == 200
    assert r.json()["history"][-1]["from_status"] == "shortlisted"


def test_document_in_use_until_application_is_inactive(client):
    job_id = make_job(client)
    cv, video = applicant_with_docs(client)
    app_id = client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={
            "cv_document_id": cv,
            "intro_video_document_id": video,
            "consents": CONSENTS_WITH_VIDEO,
        },
    ).json()["id"]
    for doc in (cv, video):
        r = client.delete("%s/me/documents/%s" % (URL, doc))
        assert r.status_code == 409 and r.json()["detail"] == "DOCUMENT_IN_USE"

    client.delete("%s/me/applications/%s" % (URL, app_id))
    assert client.delete("%s/me/documents/%s" % (URL, cv)).status_code == 204
    assert client.delete("%s/me/documents/%s" % (URL, video)).status_code == 204
    # the reference is cleared, the application remains
    one = client.get("%s/me/applications/%s" % (URL, app_id)).json()
    assert one["cv_document_id"] is None and one["intro_video_document_id"] is None


def test_deleting_account_removes_applications(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    client.post(
        "%s/jobs/%s/apply" % (URL, job_id),
        json={"cv_document_id": cv, "consents": CONSENTS},
    )
    r = client.request("DELETE", URL + "/me/account", json={"password": "rahasia123"})
    assert r.status_code == 200
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM applications")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM application_status_history")).scalar() == 0


def test_list_is_newest_first(client):
    j1 = make_job(client, title="First")
    j2 = make_job(client, title="Second")
    cv, _ = applicant_with_docs(client)
    for j in (j1, j2):
        r = client.post(
            "%s/jobs/%s/apply" % (URL, j),
            json={"cv_document_id": cv, "consents": CONSENTS},
        )
        assert r.status_code == 201
    titles = [a["job"]["title"] for a in client.get(URL + "/me/applications").json()]
    assert titles == ["Second", "First"]