"""The routes of the privacy and access area write an audit entry for each sensitive action.

audit.record is replaced by a recorder, so these tests check that the call happens with the right
action, target and details, and that no personal value reaches it. They do not need the real
audit module.
"""

import json

import pytest

from app import audit, config
from helpers import CONSENTS_WITH_VIDEO, make_profile
from test_admin import admin_login, new_alumni
from test_job import as_user, job_body, login, make_user
from test_owner import apply_as, new_owner, setup
from test_testimonial import accepted_app
from test_testimonial import post as post_testimonial

URL = "/api/v1"

# Values that must never appear in an audit entry.
PERSONAL = ("Budi Santoso", "example.com", "Jl. Keputih", "+628123456789", "rahasia123", "secret reason")


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(db, **kwargs):
        seen.append(kwargs)

    monkeypatch.setattr(audit, "record", fake)
    return seen


def named(calls, action):
    return [c for c in calls if c["action"] == action]


def one(calls, action):
    found = named(calls, action)
    assert len(found) == 1, "expected one %s, got %s" % (action, [c["action"] for c in calls])
    return found[0]


def assert_no_personal_values(calls):
    for c in calls:
        text = json.dumps(c, default=str)
        for value in PERSONAL:
            assert value not in text, "%s leaked in %s" % (value, c["action"])


def test_profile_update_logs_field_names_only(client, calls):
    as_user(client, "budi", "applicant")
    data = make_profile()
    calls.clear()
    assert client.put(URL + "/me/profile", json=data).status_code == 200
    c = one(calls, "profile.update")
    assert c["actor_role"] == "applicant" and c["target_type"] == "user"
    assert c["details"] == {"fields": sorted(data)}
    assert_no_personal_values(calls)


def test_apply_withdraw_and_revoke_are_logged(client, calls):
    owner, job_id = new_owner(client)
    app_id = apply_as(client, job_id, "budi")
    c = one(calls, "application.apply")
    assert c["actor_role"] == "applicant"
    assert c["target_type"] == "application" and c["target_id"] == app_id
    assert c["details"] == {"consents": len(CONSENTS_WITH_VIDEO), "video": True}

    calls.clear()
    r = client.patch("%s/me/applications/%s/consents" % (URL, app_id), json={"revoke": ["video", "cv", "video"]})
    assert r.status_code == 200
    c = one(calls, "application.consent_revoke")
    assert c["target_id"] == app_id and c["details"] == {"scopes": ["cv", "video"]}

    calls.clear()
    assert client.delete("%s/me/applications/%s" % (URL, app_id)).status_code == 200
    c = one(calls, "application.withdraw")
    assert c["target_type"] == "application" and c["target_id"] == app_id and c["details"] is None
    assert_no_personal_values(calls)


def test_a_failed_action_is_not_logged(client, calls):
    as_user(client, "budi", "applicant")
    calls.clear()
    r = client.delete(URL + "/me/applications/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert named(calls, "application.withdraw") == []


def test_owner_actions_are_logged(client, calls):
    owner, job_id, app_id = setup(client)
    calls.clear()

    assert client.get("%s/jobs/%s/applications" % (URL, job_id)).status_code == 200
    c = one(calls, "owner.view_applicants")
    assert c["actor_role"] == "alumni" and c["target_type"] == "job" and c["target_id"] == job_id
    assert c["details"] == {"count": 1}

    r = client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "shortlisted"})
    assert r.status_code == 200
    c = one(calls, "application.status_change")
    assert c["target_id"] == app_id and c["details"] == {"to": "shortlisted"}

    assert client.get("%s/applications/%s/cv" % (URL, app_id)).status_code == 200
    assert client.get("%s/applications/%s/video" % (URL, app_id)).status_code == 200
    assert one(calls, "owner.download_cv")["target_id"] == app_id
    assert one(calls, "owner.download_video")["target_id"] == app_id
    assert named(calls, "owner.access_denied") == []
    assert_no_personal_values(calls)


def test_identity_view_is_logged_when_it_opens(client, calls):
    owner, job_id, app_id = setup(client, identity=True)
    assert client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"}).status_code == 200
    calls.clear()
    assert client.get("%s/applications/%s/identity" % (URL, app_id)).status_code == 200
    assert one(calls, "owner.view_identity")["target_id"] == app_id
    assert named(calls, "owner.access_denied") == []
    assert_no_personal_values(calls)


@pytest.mark.parametrize(
    "suffix,action,reason",
    [
        ("/identity", "owner.view_identity", "IDENTITY_LOCKED"),
        ("/identity/ktp", "owner.download_ktp", "IDENTITY_LOCKED"),
    ],
)
def test_refused_identity_access_is_logged(client, calls, suffix, action, reason):
    owner, job_id, app_id = setup(client, identity=True)  # not accepted yet
    calls.clear()
    assert client.get("%s/applications/%s%s" % (URL, app_id, suffix)).status_code == 403
    c = one(calls, "owner.access_denied")
    assert c["target_id"] == app_id and c["details"] == {"action": action, "reason": reason}
    assert named(calls, action) == []  # a refusal is not recorded as a success


def test_a_video_without_consent_is_logged_as_denied(client, calls):
    owner, job_id, app_id = setup(client, with_video=False)
    calls.clear()
    assert client.get("%s/applications/%s/video" % (URL, app_id)).status_code == 403
    c = one(calls, "owner.access_denied")
    assert c["details"] == {"action": "owner.download_video", "reason": "NOT_VISIBLE"}


def test_the_download_limit_refusal_is_logged(client, calls, monkeypatch):
    monkeypatch.setattr(config, "DOWNLOAD_LIMIT_PER_HOUR", 1)
    owner, job_id, app_id = setup(client, with_video=False)
    calls.clear()
    assert client.get("%s/applications/%s/cv" % (URL, app_id)).status_code == 200
    assert client.get("%s/applications/%s/cv" % (URL, app_id)).status_code == 429
    c = one(calls, "owner.access_denied")
    assert c["details"] == {"action": "owner.download_cv", "reason": "DOWNLOAD_LIMIT"}
    assert len(named(calls, "owner.download_cv")) == 1


def test_another_owners_application_leaves_no_owner_entry(client, calls):
    owner, job_id, app_id = setup(client, with_video=False)
    client.post(URL + "/auth/logout")
    other, _ = new_owner(client)
    login(client, other)
    calls.clear()
    for suffix in ("/cv", "/video", "/identity", "/identity/ktp"):
        assert client.get("%s/applications/%s%s" % (URL, app_id, suffix)).status_code == 404
    assert [c for c in calls if c["action"].startswith("owner.")] == []


def test_job_actions_are_logged(client, calls):
    as_user(client, "alum", "alumni")
    calls.clear()
    job_id = client.post(URL + "/jobs", json=job_body()).json()["id"]
    c = one(calls, "job.create")
    assert c["actor_role"] == "alumni" and c["target_type"] == "job" and c["target_id"] == job_id

    assert client.put("%s/jobs/%s" % (URL, job_id), json=job_body(title="Other title")).status_code == 200
    assert one(calls, "job.update")["target_id"] == job_id
    assert client.post("%s/jobs/%s/close" % (URL, job_id)).status_code == 200
    assert one(calls, "job.close")["target_id"] == job_id


def test_testimonial_actions_are_logged(client, calls):
    app_id = accepted_app(client)
    calls.clear()
    r = post_testimonial(client, app_id)
    assert r.status_code == 201
    t_id = r.json()["id"]
    c = one(calls, "testimonial.create")
    assert c["target_type"] == "testimonial" and c["target_id"] == t_id and c["details"] is None

    assert client.delete("%s/testimonials/%s" % (URL, t_id)).status_code == 204
    assert one(calls, "testimonial.delete")["target_id"] == t_id
    assert_no_personal_values(calls)


def test_testimonial_moderation_is_logged(client, calls):
    app_id = accepted_app(client)
    t_id = post_testimonial(client, app_id).json()["id"]
    client.post(URL + "/auth/logout")
    admin_login(client)
    calls.clear()
    r = client.patch("%s/admin/testimonials/%s" % (URL, t_id), json={"status": "approved"})
    assert r.status_code == 200
    c = one(calls, "admin.testimonial_moderate")
    assert c["actor_role"] == "admin" and c["target_id"] == t_id and c["details"] == {"status": "approved"}


def test_admin_account_actions_are_logged(client, calls):
    approved = new_alumni(client, "alum1")
    rejected = new_alumni(client, "alum2")
    applicant_id = make_user(client, "pel", "applicant")
    admin_login(client)
    calls.clear()

    assert client.post("%s/admin/alumni/%s/approve" % (URL, approved)).status_code == 200
    c = one(calls, "admin.alumni_approve")
    assert c["actor_role"] == "admin" and c["target_type"] == "user" and c["target_id"] == approved

    r = client.post("%s/admin/alumni/%s/reject" % (URL, rejected), json={"reason": "secret reason text"})
    assert r.status_code == 200
    c = one(calls, "admin.alumni_reject")
    assert c["target_id"] == rejected and c["details"] is None  # the reason text stays out

    r = client.patch("%s/admin/users/%s/status" % (URL, applicant_id), json={"status": "suspended"})
    assert r.status_code == 200
    c = one(calls, "admin.user_status")
    assert c["target_id"] == applicant_id and c["details"] == {"status": "suspended"}
    assert_no_personal_values(calls)
