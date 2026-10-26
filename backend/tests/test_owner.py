import itertools
from datetime import datetime, timedelta, timezone

from test_document import upload
from test_job import as_user, job_body, login, make_user
from helpers import CONSENTS, CONSENTS_WITH_VIDEO

from sqlalchemy import text

from app import config, storage
from app.db import engine

URL = "/api/v1"
_names = itertools.count(1)

# Uploads are typed by their content, so these start with real magic bytes.
CV_BYTES = b"%PDF-1.4 cv bytes"
VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42 video bytes"
KTP_BYTES = b"\x89PNG\r\n\x1a\n png bytes"


def new_owner(client, role="alumni"):
    name = "boss%d" % next(_names)
    as_user(client, name, role)
    job_id = client.post(URL + "/jobs", json=job_body()).json()["id"]
    client.post(URL + "/auth/logout")
    return name, job_id


def apply_as(client, job_id, username, with_video=True, identity=False):
    """Register an applicant, upload documents, apply. Returns the application id."""
    as_user(client, username, "applicant")
    cv = upload(client, "cv", "cv.pdf", CV_BYTES).json()["id"]
    body = {"cv_document_id": cv, "cover_note": "Hello", "consents": list(CONSENTS)}
    if with_video:
        body["intro_video_document_id"] = upload(client, "intro_video", "v.mp4", VIDEO_BYTES).json()["id"]
        body["consents"] = list(CONSENTS_WITH_VIDEO)
    if identity:
        body["consents"].append("identity")
    r = client.post("%s/jobs/%s/apply" % (URL, job_id), json=body)
    assert r.status_code == 201
    return r.json()["id"]


def setup(client, **kw):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, "budi", **kw)
    client.post(URL + "/auth/logout")
    login(client, owner)
    return owner, job_id, app_id


def test_list_applicants_full_data(client):
    _, job_id, app_id = setup(client)
    r = client.get("%s/jobs/%s/applications" % (URL, job_id))
    assert r.status_code == 200
    body = r.json()
    assert body["next_cursor"] is None and len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == app_id and item["status"] == "submitted"
    a = item["applicant"]
    assert a["full_name"] == "Budi Santoso" and "phone" not in a  # not shortlisted yet
    assert a["email"].endswith("@example.com") and a["angkatan"] == 2019
    assert len(a["skills"]) == 2 and set(a["skills"][0]) == {"id", "name"}
    assert item["documents"]["cv"]["ext"] == "pdf"
    assert item["documents"]["video"]["ext"] == "mp4"


def test_list_without_video(client):
    _, job_id, _ = setup(client, with_video=False)
    item = client.get("%s/jobs/%s/applications" % (URL, job_id)).json()["items"][0]
    assert item["documents"]["video"] is None and item["documents"]["cv"] is not None


def test_list_pagination(client):
    owner, job_id = new_owner(client)
    ids = [apply_as(client, job_id, "pel%d" % i, with_video=False) for i in range(3)]
    client.post(URL + "/auth/logout")
    login(client, owner)
    first = client.get("%s/jobs/%s/applications?limit=2" % (URL, job_id)).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = client.get(
        "%s/jobs/%s/applications?limit=2&cursor=%s" % (URL, job_id, first["next_cursor"])
    ).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    got = [i["id"] for i in first["items"] + second["items"]]
    assert sorted(got) == sorted(ids)
    assert client.get("%s/jobs/%s/applications?cursor=zzz" % (URL, job_id)).status_code == 422
    assert client.get("%s/jobs/%s/applications?limit=101" % (URL, job_id)).status_code == 422


def test_other_owner_and_roles(client):
    _, job_id, app_id = setup(client)
    client.post(URL + "/auth/logout")
    as_user(client, "other", "alumni")
    r = client.get("%s/jobs/%s/applications" % (URL, job_id))
    assert r.status_code == 403 and r.json()["detail"] == "NOT_JOB_OWNER"
    for path in ("", "/cv", "/video", "/identity", "/identity/ktp"):
        r = client.get("%s/applications/%s%s" % (URL, app_id, path))
        assert r.status_code == 404 and r.json()["detail"] == "APPLICATION_NOT_FOUND"
    r = client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"})
    assert r.status_code == 404
    assert client.get("%s/jobs/00000000-0000-0000-0000-000000000000/applications" % URL).status_code == 404
    assert client.get("%s/applications/not-a-uuid" % URL).status_code == 404

    client.post(URL + "/auth/logout")
    login(client, "budi")
    assert client.get("%s/jobs/%s/applications" % (URL, job_id)).status_code == 403
    assert client.get("%s/applications/%s" % (URL, app_id)).status_code == 403
    client.post(URL + "/auth/logout")
    assert client.get("%s/applications/%s" % (URL, app_id)).status_code == 401

    make_user(client, "pend", "alumni", "pending")
    login(client, "pend")
    assert client.get("%s/jobs/%s/applications" % (URL, job_id)).json()["detail"] == "ACCOUNT_PENDING"


def test_admin_owner_can_manage_but_other_admin_cannot(client):
    owner, job_id = new_owner(client, "admin")
    apply_as(client, job_id, "budi", with_video=False)
    client.post(URL + "/auth/logout")
    login(client, owner)
    assert client.get("%s/jobs/%s/applications" % (URL, job_id)).status_code == 200
    client.post(URL + "/auth/logout")
    as_user(client, "admin2", "admin")
    assert client.get("%s/jobs/%s/applications" % (URL, job_id)).status_code == 403


def test_detail(client):
    _, job_id, app_id = setup(client)
    r = client.get("%s/applications/%s" % (URL, app_id))
    assert r.status_code == 200
    d = r.json()
    assert d["job"]["id"] == job_id and d["cover_note"] == "Hello"
    assert d["identity"] == {"state": "locked", "expires_at": None}  # submitted
    assert "phone" not in d["applicant"] and d["documents"]["cv"]["id"]
    assert [h["to_status"] for h in d["history"]] == ["submitted"]


def test_status_transitions_and_history(client):
    _, _, app_id = setup(client)
    path = "%s/applications/%s/status" % (URL, app_id)

    r = client.patch(path, json={"status": "shortlisted", "note": "Looks good"})
    assert r.status_code == 200 and r.json()["status"] == "shortlisted"
    assert client.patch(path, json={"status": "accepted"}).json()["status"] == "accepted"
    assert client.patch(path, json={"status": "shortlisted"}).json()["status"] == "shortlisted"
    hist = client.get("%s/applications/%s" % (URL, app_id)).json()["history"]
    assert [(h["from_status"], h["to_status"]) for h in hist] == [
        (None, "submitted"), ("submitted", "shortlisted"),
        ("shortlisted", "accepted"), ("accepted", "shortlisted"),
    ]
    assert hist[1]["note"] == "Looks good"

    # Not allowed: same status, back to submitted, anything out of a final state.
    r = client.patch(path, json={"status": "shortlisted"})
    assert r.status_code == 409 and r.json()["detail"] == "INVALID_TRANSITION"
    assert client.patch(path, json={"status": "rejected"}).status_code == 200
    for s in ("shortlisted", "accepted", "rejected"):
        assert client.patch(path, json={"status": s}).status_code == 409


def test_status_validation(client):
    _, _, app_id = setup(client)
    path = "%s/applications/%s/status" % (URL, app_id)
    assert client.patch(path, json={"status": "submitted"}).status_code == 422
    assert client.patch(path, json={"status": "withdrawn"}).status_code == 422
    assert client.patch(path, json={}).status_code == 422
    assert client.patch(path, json={"status": "accepted", "note": "x" * 501}).status_code == 422
    assert client.patch(path, json={"status": "accepted", "extra": 1}).status_code == 422


def test_withdrawn_is_final_for_owner(client):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, "budi", with_video=False)
    assert client.delete("%s/me/applications/%s" % (URL, app_id)).status_code == 200
    client.post(URL + "/auth/logout")
    login(client, owner)
    r = client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"})
    assert r.status_code == 409 and r.json()["detail"] == "INVALID_TRANSITION"


def test_status_visible_to_applicant(client):
    owner, job_id, app_id = setup(client)
    client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"})
    client.post(URL + "/auth/logout")
    login(client, "budi")
    assert client.get("%s/me/applications/%s" % (URL, app_id)).json()["status"] == "accepted"


def test_download_cv_and_video(client):
    _, _, app_id = setup(client)
    r = client.get("%s/applications/%s/cv" % (URL, app_id))
    assert r.status_code == 200 and r.content == CV_BYTES
    assert "attachment" in r.headers["content-disposition"]
    r = client.get("%s/applications/%s/video" % (URL, app_id))
    assert r.status_code == 200 and r.content == VIDEO_BYTES


def test_video_without_consent_is_not_visible(client):
    _, _, app_id = setup(client, with_video=False)
    r = client.get("%s/applications/%s/video" % (URL, app_id))
    assert r.status_code == 403 and r.json()["detail"] == "NOT_VISIBLE"


def test_identity_and_ktp(client):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, "budi", with_video=False, identity=True)
    client.post(URL + "/auth/logout")
    login(client, owner)
    r = client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"})
    assert r.status_code == 200
    ident = client.get("%s/applications/%s/identity" % (URL, app_id))
    assert ident.status_code == 200
    body = ident.json()
    assert len(body["nik"]) == 16 and body["address"] == "Jl. Keputih, Surabaya"
    assert body["birth_date"] == "2000-05-17" and body["ktp_available"] is False
    r = client.get("%s/applications/%s/identity/ktp" % (URL, app_id))
    assert r.status_code == 404 and r.json()["detail"] == "NO_KTP"

    client.post(URL + "/auth/logout")
    login(client, "budi")
    assert upload(client, "ktp", "ktp.png", KTP_BYTES).status_code == 201
    client.post(URL + "/auth/logout")
    login(client, owner)
    assert client.get("%s/applications/%s/identity" % (URL, app_id)).json()["ktp_available"] is True
    r = client.get("%s/applications/%s/identity/ktp" % (URL, app_id))
    assert r.status_code == 200 and r.content == KTP_BYTES
    assert r.headers["content-type"] == "image/png"


def test_identity_endpoints_need_acceptance_and_an_open_window(client):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, "budi", with_video=False, identity=True)
    client.post(URL + "/auth/logout")
    login(client, owner)
    base = "%s/applications/%s/identity" % (URL, app_id)
    path = "%s/applications/%s/status" % (URL, app_id)

    def refused(code):
        for suffix in ("", "/ktp"):
            r = client.get(base + suffix)
            assert r.status_code == 403 and r.json()["detail"] == code

    refused("IDENTITY_LOCKED")  # submitted
    assert client.patch(path, json={"status": "shortlisted"}).status_code == 200
    refused("IDENTITY_LOCKED")

    assert client.patch(path, json={"status": "accepted"}).status_code == 200
    assert client.get(base).status_code == 200
    assert client.get(base + "/ktp").status_code == 404  # open; no ID card uploaded yet

    # the window passes (moved in the database; the clock is never advanced)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE applications SET identity_access_expires_at = now() - interval '1 second' WHERE id = :i"),
            {"i": app_id},
        )
    refused("IDENTITY_EXPIRED")


def test_deleted_document_clears_reference(client):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, "budi")
    client.post(URL + "/auth/logout")
    login(client, owner)
    client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "rejected"})
    client.post(URL + "/auth/logout")
    login(client, "budi")
    video_id = client.get("%s/me/applications/%s" % (URL, app_id)).json()["intro_video_document_id"]
    assert client.delete("%s/me/documents/%s" % (URL, video_id)).status_code == 204
    client.post(URL + "/auth/logout")
    login(client, owner)
    item = client.get("%s/jobs/%s/applications" % (URL, job_id)).json()["items"][0]
    assert item["documents"]["video"] is None and item["documents"]["cv"] is not None


def test_phone_appears_from_shortlisted(client):
    _, job_id, app_id = setup(client)
    list_url = "%s/jobs/%s/applications" % (URL, job_id)
    assert "phone" not in client.get(list_url).json()["items"][0]["applicant"]
    r = client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "shortlisted"})
    assert r.status_code == 200 and r.json()["applicant"]["phone"] == "+628123456789"
    assert client.get(list_url).json()["items"][0]["applicant"]["phone"] == "+628123456789"


def test_applicant_is_null_when_profile_consent_is_revoked(client):
    owner, job_id, app_id = setup(client)
    client.post(URL + "/auth/logout")
    login(client, "budi")
    r = client.patch(
        "%s/me/applications/%s/consents" % (URL, app_id), json={"revoke": ["profile"]}
    )
    assert r.status_code == 200
    client.post(URL + "/auth/logout")
    login(client, owner)
    item = client.get("%s/jobs/%s/applications" % (URL, job_id)).json()["items"][0]
    assert item["applicant"] is None and item["documents"]["cv"] is not None
    assert client.get("%s/applications/%s" % (URL, app_id)).json()["applicant"] is None


def test_revoked_cv_consent_hides_cv(client):
    owner, job_id, app_id = setup(client)
    client.post(URL + "/auth/logout")
    login(client, "budi")
    r = client.patch(
        "%s/me/applications/%s/consents" % (URL, app_id), json={"revoke": ["cv"]}
    )
    assert r.status_code == 200
    client.post(URL + "/auth/logout")
    login(client, owner)

    r = client.get("%s/applications/%s/cv" % (URL, app_id))
    assert r.status_code == 403 and r.json()["detail"] == "NOT_VISIBLE"
    assert client.get("%s/applications/%s/video" % (URL, app_id)).status_code == 200

    item = client.get("%s/jobs/%s/applications" % (URL, job_id)).json()["items"][0]
    assert item["documents"]["cv"] is None and item["documents"]["video"] is not None
    docs = client.get("%s/applications/%s" % (URL, app_id)).json()["documents"]
    assert docs["cv"] is None and docs["video"] is not None


def test_deleted_video_is_404_only_after_the_consent_check(client):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, "budi")
    client.post(URL + "/auth/logout")
    login(client, owner)
    client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "rejected"})
    client.post(URL + "/auth/logout")
    login(client, "budi")
    video_id = client.get("%s/me/applications/%s" % (URL, app_id)).json()["intro_video_document_id"]
    assert client.delete("%s/me/documents/%s" % (URL, video_id)).status_code == 204
    client.post(URL + "/auth/logout")
    login(client, owner)

    # consent still active, document gone
    r = client.get("%s/applications/%s/video" % (URL, app_id))
    assert r.status_code == 404 and r.json()["detail"] == "DOCUMENT_NOT_FOUND"

    # once the consent is revoked the answer is 403, not 404
    client.post(URL + "/auth/logout")
    login(client, "budi")
    client.patch("%s/me/applications/%s/consents" % (URL, app_id), json={"revoke": ["video"]})
    client.post(URL + "/auth/logout")
    login(client, owner)
    r = client.get("%s/applications/%s/video" % (URL, app_id))
    assert r.status_code == 403 and r.json()["detail"] == "NOT_VISIBLE"


def test_file_missing_on_disk_is_500_storage_error(client):
    _, _, app_id = setup(client)
    with engine.connect() as conn:
        keys = [r[0] for r in conn.execute(text(
            "SELECT c.storage_key FROM document_copies c "
            "JOIN documents d ON d.id = c.document_id WHERE d.type = 'cv'"
        ))]
    assert keys
    for key in keys:
        storage.delete(key)
    r = client.get("%s/applications/%s/cv" % (URL, app_id))
    assert r.status_code == 500 and r.json()["detail"] == "STORAGE_ERROR"


def window_of(app_id):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT accepted_at, identity_access_expires_at FROM applications WHERE id = :i"),
            {"i": app_id},
        ).one()
    return tuple(row)


def test_first_acceptance_opens_the_identity_window(client):
    _, _, app_id = setup(client)
    assert window_of(app_id) == (None, None)
    path = "%s/applications/%s/status" % (URL, app_id)

    before = datetime.now(timezone.utc)
    assert client.patch(path, json={"status": "accepted"}).status_code == 200
    after = datetime.now(timezone.utc)

    accepted_at, expires_at = window_of(app_id)
    assert before <= accepted_at <= after
    assert expires_at - accepted_at == timedelta(days=config.IDENTITY_ACCESS_DAYS)

    # the applicant sees when the window ends
    client.post(URL + "/auth/logout")
    login(client, "budi")
    mine = client.get("%s/me/applications/%s" % (URL, app_id)).json()
    assert datetime.fromisoformat(mine["identity_access_expires_at"]) == expires_at


def test_flip_flopping_does_not_move_the_window(client):
    _, _, app_id = setup(client)
    path = "%s/applications/%s/status" % (URL, app_id)
    assert client.patch(path, json={"status": "accepted"}).status_code == 200
    first = window_of(app_id)

    assert client.patch(path, json={"status": "shortlisted"}).status_code == 200
    assert window_of(app_id) == first
    assert client.patch(path, json={"status": "accepted"}).status_code == 200
    assert window_of(app_id) == first
    assert client.patch(path, json={"status": "rejected"}).status_code == 200
    assert window_of(app_id) == first


def test_shortlist_and_reject_never_open_the_window(client):
    _, _, app_id = setup(client)
    path = "%s/applications/%s/status" % (URL, app_id)
    assert client.patch(path, json={"status": "shortlisted"}).status_code == 200
    assert window_of(app_id) == (None, None)
    assert client.patch(path, json={"status": "rejected"}).status_code == 200
    assert window_of(app_id) == (None, None)


def test_window_follows_the_configured_days(client, monkeypatch):
    monkeypatch.setattr(config, "IDENTITY_ACCESS_DAYS", 7)
    _, _, app_id = setup(client)
    path = "%s/applications/%s/status" % (URL, app_id)
    assert client.patch(path, json={"status": "accepted"}).status_code == 200
    accepted_at, expires_at = window_of(app_id)
    assert expires_at - accepted_at == timedelta(days=7)


def identity_block(client, app_id):
    return client.get("%s/applications/%s" % (URL, app_id)).json()["identity"]


def test_identity_block_follows_status_and_window(client):
    _, _, app_id = setup(client, identity=True)
    path = "%s/applications/%s/status" % (URL, app_id)
    locked = {"state": "locked", "expires_at": None}

    assert identity_block(client, app_id) == locked  # submitted
    client.patch(path, json={"status": "shortlisted"})
    assert identity_block(client, app_id) == locked

    client.patch(path, json={"status": "accepted"})
    _, expires_at = window_of(app_id)
    block = identity_block(client, app_id)
    assert block["state"] == "available"
    assert datetime.fromisoformat(block["expires_at"]) == expires_at

    # shortlisted again: locked, and the date is hidden while it is locked
    client.patch(path, json={"status": "shortlisted"})
    assert identity_block(client, app_id) == locked

    # the window passes (moved in the database; the clock is never advanced)
    client.patch(path, json={"status": "accepted"})
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE applications SET identity_access_expires_at = now() - interval '1 second' WHERE id = :i"),
            {"i": app_id},
        )
    block = identity_block(client, app_id)
    assert block["state"] == "expired" and block["expires_at"] is not None

    # accepting again after expiry does not open a new window
    client.patch(path, json={"status": "shortlisted"})
    client.patch(path, json={"status": "accepted"})
    assert identity_block(client, app_id)["state"] == "expired"


def test_identity_block_is_locked_without_identity_consent(client):
    _, _, app_id = setup(client)  # the applicant did not grant identity
    client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"})
    assert window_of(app_id)[1] is not None  # the window exists, but nothing opens
    assert identity_block(client, app_id) == {"state": "locked", "expires_at": None}


def test_revoking_identity_consent_after_acceptance_locks_it(client):
    owner, _, app_id = setup(client, identity=True)
    client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"})
    assert identity_block(client, app_id)["state"] == "available"

    client.post(URL + "/auth/logout")
    login(client, "budi")
    r = client.patch(
        "%s/me/applications/%s/consents" % (URL, app_id), json={"revoke": ["identity"]}
    )
    assert r.status_code == 200
    client.post(URL + "/auth/logout")
    login(client, owner)

    # decision: once the consent is revoked the date is hidden as well
    assert identity_block(client, app_id) == {"state": "locked", "expires_at": None}
    assert window_of(app_id)[1] is not None
