import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import consent
from app.db import engine
from test_job import as_user, login
from test_owner import apply_as, new_owner, setup

URL = "/api/v1"

STATUSES = ("submitted", "shortlisted", "accepted", "rejected", "withdrawn")
# The phone number is shown only while the application is shortlisted or accepted.
PHONE_SHOWN = {
    "submitted": False,
    "shortlisted": True,
    "accepted": True,
    "rejected": False,
    "withdrawn": False,
}
REVOKED = (None, "profile", "cv", "video", "all")


def sql(statement, **params):
    with engine.begin() as conn:
        conn.execute(text(statement), params)


def revoke_in_db(app_id, scope):
    sql(
        "UPDATE application_consents SET revoked_at = now() "
        "WHERE application_id = :i AND scope = :s",
        i=app_id,
        s=scope,
    )


def gone_scopes(revoked):
    if revoked == "all":
        return {"profile", "cv", "video"}
    return {revoked} if revoked else set()


@pytest.mark.parametrize("revoked", REVOKED)
@pytest.mark.parametrize("status", STATUSES)
def test_visibility_table(client, status, revoked):
    _, job_id, app_id = setup(client)  # consents: profile, cv, video
    gone = gone_scopes(revoked)
    sql("UPDATE applications SET status = :s WHERE id = :i", s=status, i=app_id)
    for scope in gone:
        revoke_in_db(app_id, scope)

    item = client.get("%s/jobs/%s/applications" % (URL, job_id)).json()["items"][0]
    detail = client.get("%s/applications/%s" % (URL, app_id)).json()
    for view in (item, detail):
        a = view["applicant"]
        if "profile" in gone:
            assert a is None
        else:
            assert a["full_name"] == "Budi Santoso"
            assert ("phone" in a) is PHONE_SHOWN[status]
            if PHONE_SHOWN[status]:
                assert a["phone"] == "+628123456789"
        assert (view["documents"]["cv"] is None) is ("cv" in gone)
        assert (view["documents"]["video"] is None) is ("video" in gone)

    for path, scope, content in (
        ("cv", "cv", b"%PDF cv bytes"),
        ("video", "video", b"video bytes"),
    ):
        r = client.get("%s/applications/%s/%s" % (URL, app_id, path))
        if scope in gone:
            assert r.status_code == 403 and r.json()["detail"] == "NOT_VISIBLE"
        else:
            assert r.status_code == 200 and r.content == content


def test_phone_is_not_shown_for_rejected_or_withdrawn(client):
    owner, job_id = new_owner(client)
    rejected = apply_as(client, job_id, "pel1", with_video=False)
    withdrawn = apply_as(client, job_id, "pel2", with_video=False)
    assert client.delete("%s/me/applications/%s" % (URL, withdrawn)).status_code == 200
    late = apply_as(client, job_id, "pel3", with_video=False)
    client.post(URL + "/auth/logout")
    login(client, owner)

    def move(app_id, to):
        return client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": to})

    # rejected straight from submitted: never shortlisted, no phone
    assert move(rejected, "rejected").status_code == 200
    # shortlisted first: the phone shows, but it goes away once the application is rejected
    shortlisted = move(late, "shortlisted")
    assert shortlisted.json()["applicant"]["phone"] == "+628123456789"
    assert move(late, "rejected").status_code == 200

    items = {i["id"]: i for i in client.get("%s/jobs/%s/applications" % (URL, job_id)).json()["items"]}
    for app_id in (rejected, withdrawn, late):
        a = items[app_id]["applicant"]
        assert a is not None and "phone" not in a


def test_non_owner_gets_404_before_any_visibility_check(client):
    _, job_id, app_id = setup(client)
    revoke_in_db(app_id, "cv")
    client.post(URL + "/auth/logout")
    as_user(client, "admin2", "admin")
    for path in ("", "/cv", "/video"):
        r = client.get("%s/applications/%s%s" % (URL, app_id, path))
        assert r.status_code == 404 and r.json()["detail"] == "APPLICATION_NOT_FOUND"
    r = client.get("%s/jobs/%s/applications" % (URL, job_id))
    assert r.status_code == 403 and r.json()["detail"] == "NOT_JOB_OWNER"


def test_one_page_mixes_visible_and_hidden_applicants(client):
    owner, job_id = new_owner(client)
    hidden = apply_as(client, job_id, "pel1", with_video=False)
    shown = apply_as(client, job_id, "pel2", with_video=False)
    revoke_in_db(hidden, "profile")
    client.post(URL + "/auth/logout")
    login(client, owner)
    items = {i["id"]: i for i in client.get("%s/jobs/%s/applications" % (URL, job_id)).json()["items"]}
    assert items[hidden]["applicant"] is None
    assert items[shown]["applicant"]["full_name"] == "Budi Santoso"


def test_active_scopes_by_application(client):
    _, job_id = new_owner(client)
    first = apply_as(client, job_id, "pel1", with_video=False)
    second = apply_as(client, job_id, "pel2", with_video=False)
    revoke_in_db(first, "cv")
    ids = [uuid.UUID(first), uuid.UUID(second)]
    with Session(engine) as db:
        got = consent.active_scopes(db, ids)
        assert got[ids[0]] == {"profile"}
        assert got[ids[1]] == {"profile", "cv"}
        unknown = uuid.uuid4()
        assert consent.active_scopes(db, [unknown]) == {unknown: set()}
        assert consent.active_scopes(db, []) == {}