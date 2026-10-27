from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db import engine
from test_job import login
from test_document import upload
from test_owner import KTP_BYTES, apply_as, identity_block, new_owner, setup

URL = "/api/v1"
LOCKED = {"state": "locked", "expires_at": None}

# status, identity consent granted, window end in seconds from now (None = no window), state
CASES = [
    ("submitted", True, 3600, "locked"),
    ("shortlisted", True, 3600, "locked"),
    ("accepted", True, 3600, "available"),
    ("accepted", True, -1, "expired"),
    ("accepted", False, 3600, "locked"),
    ("accepted", True, None, "locked"),
    ("rejected", True, 3600, "locked"),
    ("withdrawn", True, 3600, "locked"),
]


def base(app_id):
    return "%s/applications/%s/identity" % (URL, app_id)


def accept(client, app_id):
    r = client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "accepted"})
    assert r.status_code == 200


@pytest.mark.parametrize("status,consented,window,state", CASES)
def test_identity_state_table(client, status, consented, window, state):
    _, _, app_id = setup(client, with_video=False, identity=consented)
    ends = None if window is None else datetime.now(timezone.utc) + timedelta(seconds=window)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE applications SET status = :s, identity_access_expires_at = :e WHERE id = :i"),
            {"s": status, "e": ends, "i": app_id},
        )
    block = identity_block(client, app_id)
    assert block["state"] == state
    assert (block["expires_at"] is None) is (state == "locked")

    if state == "available":
        assert client.get(base(app_id)).status_code == 200
        r = client.get(base(app_id) + "/ktp")
        assert r.status_code == 404 and r.json()["detail"] == "NO_KTP"
    else:
        for suffix in ("", "/ktp"):
            r = client.get(base(app_id) + suffix)
            assert r.status_code == 403 and r.json()["detail"] == "IDENTITY_" + state.upper()


def test_revoking_identity_consent_closes_the_endpoints(client):
    owner, _, app_id = setup(client, with_video=False, identity=True)
    accept(client, app_id)
    assert client.get(base(app_id)).status_code == 200

    client.post(URL + "/auth/logout")
    login(client, "budi")
    r = client.patch(
        "%s/me/applications/%s/consents" % (URL, app_id), json={"revoke": ["identity"]}
    )
    assert r.status_code == 200
    client.post(URL + "/auth/logout")
    login(client, owner)

    assert identity_block(client, app_id) == LOCKED
    for suffix in ("", "/ktp"):
        r = client.get(base(app_id) + suffix)
        assert r.status_code == 403 and r.json()["detail"] == "IDENTITY_LOCKED"


def test_rejecting_after_acceptance_locks_identity_again(client):
    _, _, app_id = setup(client, with_video=False, identity=True)
    accept(client, app_id)
    assert client.get(base(app_id)).status_code == 200
    r = client.patch("%s/applications/%s/status" % (URL, app_id), json={"status": "rejected"})
    assert r.status_code == 200
    assert identity_block(client, app_id) == LOCKED
    r = client.get(base(app_id))
    assert r.status_code == 403 and r.json()["detail"] == "IDENTITY_LOCKED"


def test_admin_who_owns_the_job_can_open_identity(client):
    owner, job_id = new_owner(client, "admin")
    app_id = apply_as(client, job_id, "budi", with_video=False, identity=True)
    client.post(URL + "/auth/logout")
    login(client, owner)
    accept(client, app_id)
    assert client.get(base(app_id)).status_code == 200


def test_another_admin_cannot_reach_identity(client):
    _, _, app_id = setup(client, with_video=False, identity=True)
    accept(client, app_id)
    client.post(URL + "/auth/logout")
    other, _ = new_owner(client, "admin")
    client.post(URL + "/auth/logout")
    login(client, other)
    for suffix in ("", "/ktp"):
        assert client.get(base(app_id) + suffix).status_code == 404


def test_owner_gets_the_newest_ktp(client):
    owner, _, app_id = setup(client, with_video=False, identity=True)
    accept(client, app_id)
    newest = b"\x89PNG\r\n\x1a\n second card"
    for content in (KTP_BYTES, newest):
        client.post(URL + "/auth/logout")
        login(client, "budi")
        assert upload(client, "ktp", "ktp.png", content).status_code == 201
    client.post(URL + "/auth/logout")
    login(client, owner)
    r = client.get(base(app_id) + "/ktp")
    assert r.status_code == 200 and r.content == newest