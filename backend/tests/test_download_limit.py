import pytest
from sqlalchemy import text

from app import config
from app.db import engine
from test_job import login
from test_owner import apply_as, new_owner, setup

URL = "/api/v1"
PATHS = ("/cv", "/video", "/identity", "/identity/ktp")


def url(app_id, suffix):
    return "%s/applications/%s%s" % (URL, app_id, suffix)


def accept(client, app_id):
    r = client.patch(url(app_id, "/status"), json={"status": "accepted"})
    assert r.status_code == 200


def expire_window(app_id):
    # the window passes (moved in the database; the clock is never advanced)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE applications SET identity_access_expires_at = now() - interval '1 second' WHERE id = :i"),
            {"i": app_id},
        )


def test_twenty_downloads_pass_and_the_21st_is_refused(client):
    assert config.DOWNLOAD_LIMIT_PER_HOUR == 20
    _, _, app_id = setup(client, with_video=False)
    for _ in range(20):
        assert client.get(url(app_id, "/cv")).status_code == 200
    r = client.get(url(app_id, "/cv"))
    assert r.status_code == 429 and r.json() == {"detail": "DOWNLOAD_LIMIT"}
    assert "retry-after" not in r.headers


@pytest.mark.parametrize("kind", ["not_visible", "identity_locked", "identity_expired"])
def test_refused_attempts_count_towards_the_limit(client, monkeypatch, kind):
    monkeypatch.setattr(config, "DOWNLOAD_LIMIT_PER_HOUR", 3)
    if kind == "not_visible":
        _, _, app_id = setup(client, with_video=False)  # no video consent
        suffix, code = "/video", "NOT_VISIBLE"
    elif kind == "identity_locked":
        _, _, app_id = setup(client, with_video=False, identity=True)  # not accepted yet
        suffix, code = "/identity", "IDENTITY_LOCKED"
    else:
        _, _, app_id = setup(client, with_video=False, identity=True)
        accept(client, app_id)
        expire_window(app_id)
        suffix, code = "/identity/ktp", "IDENTITY_EXPIRED"

    for _ in range(3):
        r = client.get(url(app_id, suffix))
        assert r.status_code == 403 and r.json()["detail"] == code
    r = client.get(url(app_id, suffix))
    assert r.status_code == 429 and r.json()["detail"] == "DOWNLOAD_LIMIT"
    assert "retry-after" not in r.headers


def test_another_owners_application_is_404_and_not_counted(client, monkeypatch):
    monkeypatch.setattr(config, "DOWNLOAD_LIMIT_PER_HOUR", 2)
    _, _, app_id = setup(client, with_video=False)
    client.post(URL + "/auth/logout")
    other, other_job = new_owner(client)
    own = apply_as(client, other_job, "sari", with_video=False)
    client.post(URL + "/auth/logout")
    login(client, other)

    for suffix in PATHS * 2:  # eight attempts, well over the limit of two
        r = client.get(url(app_id, suffix))
        assert r.status_code == 404 and r.json()["detail"] == "APPLICATION_NOT_FOUND"

    # none of them was counted: the other owner still has the whole allowance
    assert client.get(url(own, "/cv")).status_code == 200
    assert client.get(url(own, "/cv")).status_code == 200
    assert client.get(url(own, "/cv")).status_code == 429


def test_two_owners_do_not_affect_each_other(client, monkeypatch):
    monkeypatch.setattr(config, "DOWNLOAD_LIMIT_PER_HOUR", 2)
    owner_a, job_a = new_owner(client)
    app_a = apply_as(client, job_a, "budi", with_video=False)
    client.post(URL + "/auth/logout")
    owner_b, job_b = new_owner(client)
    app_b = apply_as(client, job_b, "sari", with_video=False)
    client.post(URL + "/auth/logout")

    login(client, owner_a)
    assert client.get(url(app_a, "/cv")).status_code == 200
    assert client.get(url(app_a, "/cv")).status_code == 200
    assert client.get(url(app_a, "/cv")).status_code == 429
    client.post(URL + "/auth/logout")

    login(client, owner_b)
    assert client.get(url(app_b, "/cv")).status_code == 200


def test_the_four_paths_share_one_count_per_owner(client, monkeypatch):
    monkeypatch.setattr(config, "DOWNLOAD_LIMIT_PER_HOUR", 4)
    _, _, app_id = setup(client, identity=True)
    accept(client, app_id)

    # one hit on each path; the ID card is missing (404) but the attempt still counts
    for suffix, status in (("/cv", 200), ("/video", 200), ("/identity", 200), ("/identity/ktp", 404)):
        assert client.get(url(app_id, suffix)).status_code == status

    for suffix in PATHS:
        r = client.get(url(app_id, suffix))
        assert r.status_code == 429 and r.json()["detail"] == "DOWNLOAD_LIMIT"


def revoke_consent(app_id, scope):
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE application_consents SET revoked_at = now() "
                "WHERE application_id = :i AND scope = :s"
            ),
            {"i": app_id, "s": scope},
        )


@pytest.mark.parametrize("suffix,scope", [("/cv", "cv"), ("/video", "video")])
def test_attempts_refused_for_a_revoked_consent_are_counted(client, monkeypatch, suffix, scope):
    monkeypatch.setattr(config, "DOWNLOAD_LIMIT_PER_HOUR", 3)
    _, _, app_id = setup(client)  # CV and video both attached and consented
    revoke_consent(app_id, scope)

    for _ in range(3):
        r = client.get(url(app_id, suffix))
        assert r.status_code == 403 and r.json()["detail"] == "NOT_VISIBLE"
    r = client.get(url(app_id, suffix))
    assert r.status_code == 429 and r.json()["detail"] == "DOWNLOAD_LIMIT"
    assert "retry-after" not in r.headers