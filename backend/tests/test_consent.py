import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import consent
from app.db import engine
from helpers import CONSENTS, CONSENTS_WITH_VIDEO
from test_application import applicant_with_docs, make_job
from test_job import as_user

URL = "/api/v1"
NO_SUCH_APP = "00000000-0000-0000-0000-000000000000"


def apply_to(client, job_id, cv, **extra):
    body = {"cv_document_id": cv}
    body.update(extra)
    return client.post("%s/jobs/%s/apply" % (URL, job_id), json=body)


def patch_revoke(client, app_id, scopes):
    return client.patch(
        "%s/me/applications/%s/consents" % (URL, app_id), json={"revoke": scopes}
    )


def count(table):
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM %s" % table)).scalar()


def by_scope(body):
    return {c["scope"]: c for c in body["consents"]}


def applied(client, consents=CONSENTS, video=False):
    """Apply as a fresh applicant and return the application detail."""
    job_id = make_job(client)
    cv, video_id = applicant_with_docs(client)
    extra = {"consents": consents}
    if video:
        extra["intro_video_document_id"] = video_id
    r = apply_to(client, job_id, cv, **extra)
    assert r.status_code == 201
    return r.json()


# ---- texts -----------------------------------------------------------------


def test_consent_texts_are_public(client):
    r = client.get("%s/consent-texts" % URL)
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "v2"
    assert list(body["scopes"]) == ["profile", "cv", "video", "identity"]
    assert body["scopes"] == consent.TEXTS
    assert body["scopes"]["cv"] == "Allow the job owner to open my CV."


# ---- applying --------------------------------------------------------------


def test_apply_records_consents_in_detail(client):
    body = applied(client, CONSENTS_WITH_VIDEO + ["identity"], video=True)
    got = by_scope(body)
    assert list(got) == ["profile", "cv", "video", "identity"]
    for c in got.values():
        assert c["version"] == "v2" and c["granted_at"] and c["revoked_at"] is None
    assert body["identity_access_expires_at"] is None
    again = client.get("%s/me/applications/%s" % (URL, body["id"])).json()
    assert again["consents"] == body["consents"]


def test_identity_consent_is_optional(client):
    body = applied(client)
    assert list(by_scope(body)) == ["profile", "cv"]


def test_apply_requires_profile_and_cv_consent(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    for extra in (
        {},
        {"consents": []},
        {"consents": ["profile"]},
        {"consents": ["cv"]},
        {"consents": ["identity"]},
    ):
        r = apply_to(client, job_id, cv, **extra)
        assert r.status_code == 422 and r.json()["detail"] == "CONSENT_REQUIRED", extra
    # nothing was saved, so the same job can still be applied to
    assert apply_to(client, job_id, cv, consents=CONSENTS).status_code == 201


def test_attached_video_requires_video_consent(client):
    job_id = make_job(client)
    cv, video = applicant_with_docs(client)
    r = apply_to(
        client, job_id, cv, intro_video_document_id=video, consents=CONSENTS
    )
    assert r.status_code == 422 and r.json()["detail"] == "CONSENT_REQUIRED"
    r = apply_to(
        client, job_id, cv, intro_video_document_id=video, consents=CONSENTS_WITH_VIDEO
    )
    assert r.status_code == 201


def test_unknown_or_duplicate_scope_is_rejected(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    for consents in (
        CONSENTS + ["selfie"],
        ["profile", "cv", "cv"],
        ["PROFILE", "cv"],
    ):
        r = apply_to(client, job_id, cv, consents=consents)
        assert r.status_code == 422 and r.json()["detail"] == "INVALID_CONSENT", consents


def test_failed_application_leaves_no_rows(client):
    job_id = make_job(client)
    cv, _ = applicant_with_docs(client)
    assert apply_to(client, job_id, cv).status_code == 422
    assert apply_to(client, job_id, cv, consents=CONSENTS + ["selfie"]).status_code == 422
    assert count("applications") == 0
    assert count("application_consents") == 0
    assert count("application_status_history") == 0


def test_consent_is_checked_after_the_other_checks(client):
    closed = make_job(client)
    open_job = make_job(client)
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET status = 'closed' WHERE id = :i"), {"i": closed})
    cv, video = applicant_with_docs(client)

    r = apply_to(client, closed, cv)
    assert r.status_code == 409 and r.json()["detail"] == "JOB_CLOSED"

    # a wrong document type is reported before the missing consent
    r = apply_to(client, open_job, video)
    assert r.status_code == 422 and r.json()["detail"] == "invalid document"

    assert apply_to(client, open_job, cv, consents=CONSENTS).status_code == 201
    r = apply_to(client, open_job, cv)
    assert r.status_code == 409 and r.json()["detail"] == "ALREADY_APPLIED"


# ---- revoking --------------------------------------------------------------


def test_revoke_is_idempotent_and_permanent(client):
    body = applied(client, CONSENTS_WITH_VIDEO + ["identity"], video=True)
    app_id = body["id"]
    path = "%s/me/applications/%s" % (URL, app_id)

    r = patch_revoke(client, app_id, ["cv"])
    assert r.status_code == 200
    got = by_scope(r.json())
    first = got["cv"]["revoked_at"]
    assert first is not None
    for scope in ("profile", "video", "identity"):
        assert got[scope]["revoked_at"] is None

    # revoking again changes nothing
    r = patch_revoke(client, app_id, ["cv"])
    assert r.status_code == 200 and by_scope(r.json())["cv"]["revoked_at"] == first

    # revoking another scope never clears an earlier revocation
    r = patch_revoke(client, app_id, ["profile"])
    got = by_scope(r.json())
    assert got["cv"]["revoked_at"] == first and got["profile"]["revoked_at"] is not None

    # there is no way to grant again
    r = client.patch(
        path + "/consents", json={"revoke": [], "grant": ["cv"]}
    )
    assert r.status_code == 422

    stored = by_scope(client.get(path).json())
    assert stored["cv"]["revoked_at"] == first


def test_is_active_follows_revocation(client):
    body = applied(client, CONSENTS_WITH_VIDEO, video=True)
    app_id = body["id"]
    patch_revoke(client, app_id, ["cv"])
    with Session(engine) as db:
        aid = uuid.UUID(app_id)
        assert consent.is_active(db, aid, "profile") is True
        assert consent.is_active(db, aid, "video") is True
        assert consent.is_active(db, aid, "cv") is False
        assert consent.is_active(db, aid, "identity") is False  # never granted


def test_all_four_scopes_can_be_revoked(client):
    body = applied(client, CONSENTS_WITH_VIDEO + ["identity"], video=True)
    r = patch_revoke(client, body["id"], ["profile", "cv", "video", "identity"])
    assert r.status_code == 200
    assert all(c["revoked_at"] for c in r.json()["consents"])


def test_revoking_a_never_granted_scope_does_nothing(client):
    body = applied(client)  # profile + cv only: no video, no identity
    r = patch_revoke(client, body["id"], ["video", "identity"])
    assert r.status_code == 200
    got = by_scope(r.json())
    assert list(got) == ["profile", "cv"]
    assert all(c["revoked_at"] is None for c in got.values())
    assert count("application_consents") == 2
    # an empty list is also fine
    assert patch_revoke(client, body["id"], []).status_code == 200


def test_revoke_rejects_unknown_scope_and_bad_body(client):
    body = applied(client)
    app_id = body["id"]
    r = patch_revoke(client, app_id, ["selfie"])
    assert r.status_code == 422 and r.json()["detail"] == "INVALID_CONSENT"
    # one unknown scope means nothing is revoked at all
    r = patch_revoke(client, app_id, ["cv", "selfie"])
    assert r.status_code == 422
    url = "%s/me/applications/%s/consents" % (URL, app_id)
    assert client.patch(url, json={}).status_code == 422
    assert client.patch(url, json={"revoke": "cv"}).status_code == 422
    assert client.patch(url, json={"revoke": ["cv"], "extra": 1}).status_code == 422
    got = by_scope(client.get("%s/me/applications/%s" % (URL, app_id)).json())
    assert all(c["revoked_at"] is None for c in got.values())


def test_other_applicant_cannot_revoke(client):
    body = applied(client)
    client.post(URL + "/auth/logout")
    as_user(client, "siti", "applicant")
    r = patch_revoke(client, body["id"], ["cv"])
    assert r.status_code == 404 and r.json()["detail"] == "APPLICATION_NOT_FOUND"
    r = patch_revoke(client, "not-a-uuid", ["cv"])
    assert r.status_code == 404 and r.json()["detail"] == "APPLICATION_NOT_FOUND"
    with engine.connect() as conn:
        revoked = conn.execute(
            text("SELECT count(*) FROM application_consents WHERE revoked_at IS NOT NULL")
        ).scalar()
    assert revoked == 0


def test_revoke_needs_an_applicant_login(client):
    assert patch_revoke(client, NO_SUCH_APP, ["cv"]).status_code == 401
    as_user(client, "alum", "alumni")
    assert patch_revoke(client, NO_SUCH_APP, ["cv"]).status_code == 403


def test_withdrawn_application_can_still_revoke(client):
    body = applied(client)
    app_id = body["id"]
    assert client.delete("%s/me/applications/%s" % (URL, app_id)).status_code == 200
    r = patch_revoke(client, app_id, ["profile"])
    assert r.status_code == 200 and by_scope(r.json())["profile"]["revoked_at"]


def test_deleting_account_removes_consents(client):
    applied(client)
    assert count("application_consents") == 2
    r = client.request("DELETE", URL + "/me/account", json={"password": "rahasia123"})
    assert r.status_code == 200
    assert count("application_consents") == 0