"""Proof requests and grants: admin asks, alumni grants, admin opens."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, update

from app import config
from app.db import SessionLocal
from app.models import User, UserPublicKey
from test_job import login, make_user
from test_proof_purge import NOW, admin_key, grant, proof, request


def setup_admin(client, username="root", with_key=True):
    admin_id = uuid.UUID(make_user(client, username, "admin"))
    if with_key:
        with SessionLocal() as db:
            admin_key(db, db.get(User, admin_id))
            db.commit()
    return admin_id


def setup_alumni(client, username="sari", with_proof=True, status="pending"):
    alumni_id = uuid.UUID(make_user(client, username, "alumni", status))
    if with_proof:
        with SessionLocal() as db:
            proof(db, db.get(User, alumni_id))
            db.commit()
    return alumni_id


def ask(client, alumni_id):
    return client.post(f"/api/v1/admin/alumni/{alumni_id}/proof-request")


# ---------- POST /admin/alumni/{id}/proof-request ----------


def test_admin_can_request_proof(client):
    setup_admin(client)
    alumni_id = setup_alumni(client)
    login(client, "root")
    r = ask(client, alumni_id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending" and body["alumni_id"] == str(alumni_id)
    expires = datetime.fromisoformat(body["expires_at"])
    expected = NOW + timedelta(days=config.PROOF_REQUEST_TTL_DAYS)
    assert abs((expires - expected).total_seconds()) < 60


def test_no_proof_is_409(client):
    setup_admin(client)
    alumni_id = setup_alumni(client, with_proof=False)
    login(client, "root")
    assert ask(client, alumni_id).json()["detail"] == "NO_PROOF"


def test_no_key_is_409(client):
    setup_admin(client, with_key=False)
    alumni_id = setup_alumni(client)
    login(client, "root")
    r = ask(client, alumni_id)
    assert r.status_code == 409 and r.json()["detail"] == "NO_PUBLIC_KEY"


def test_expired_key_counts_as_no_key(client):
    admin_id = setup_admin(client)
    alumni_id = setup_alumni(client)
    with SessionLocal() as db:
        db.execute(
            update(UserPublicKey)
            .where(UserPublicKey.user_id == admin_id)
            .values(expires_at=NOW - timedelta(seconds=1))
        )
        db.commit()
    login(client, "root")
    assert ask(client, alumni_id).json()["detail"] == "NO_PUBLIC_KEY"


def test_same_admin_twice_is_409(client):
    setup_admin(client)
    alumni_id = setup_alumni(client)
    login(client, "root")
    assert ask(client, alumni_id).status_code == 201
    r = ask(client, alumni_id)
    assert r.status_code == 409 and r.json()["detail"] == "REQUEST_EXISTS"


def test_another_admin_can_also_request(client):
    setup_admin(client, "root")
    setup_admin(client, "root2")
    alumni_id = setup_alumni(client)
    login(client, "root")
    assert ask(client, alumni_id).status_code == 201
    login(client, "root2")
    assert ask(client, alumni_id).status_code == 201


def test_active_alumni_is_409(client):
    setup_admin(client)
    alumni_id = setup_alumni(client, status="active")
    login(client, "root")
    assert ask(client, alumni_id).json()["detail"] == "NOT_PENDING"


@pytest.mark.parametrize("target", ["not-a-uuid", str(uuid.uuid4())])
def test_unknown_alumni_is_404(client, target):
    setup_admin(client)
    login(client, "root")
    r = ask(client, target)
    assert r.status_code == 404 and r.json()["detail"] == "ALUMNI_NOT_FOUND"


def test_non_admin_is_403(client):
    alumni_id = setup_alumni(client)
    make_user(client, "budi", "alumni")
    login(client, "budi")
    assert ask(client, alumni_id).status_code == 403


# ---------- GET /me/verification-requests ----------

INBOX = "/api/v1/me/verification-requests"


def test_alumni_sees_open_requests_with_admin_and_fingerprint(client):
    setup_admin(client)
    alumni_id = setup_alumni(client)
    login(client, "root")
    req_id = ask(client, alumni_id).json()["id"]
    login(client, "sari")
    r = client.get(INBOX)
    assert r.status_code == 200, r.text
    (item,) = r.json()
    assert item["id"] == req_id and item["status"] == "pending"
    assert item["admin_username"] == "root" and item["admin_fingerprint"] == "0" * 64
    assert set(item) == {
        "id",
        "status",
        "admin_username",
        "admin_fingerprint",
        "created_at",
        "expires_at",
    }


def test_inbox_is_empty_without_requests(client):
    setup_alumni(client)
    login(client, "sari")
    assert client.get(INBOX).json() == []


def test_alumni_only_sees_their_own_requests(client):
    setup_admin(client)
    sari = setup_alumni(client, "sari")
    setup_alumni(client, "tono")
    login(client, "root")
    ask(client, sari)
    login(client, "tono")
    assert client.get(INBOX).json() == []


def test_closed_and_expired_requests_are_hidden(client):
    admin_id = setup_admin(client)
    alumni_id = setup_alumni(client)
    with SessionLocal() as db:
        admin, alumni = db.get(User, admin_id), db.get(User, alumni_id)
        request(db, alumni, admin, status="closed")
        request(
            db, alumni, admin, expires_at=NOW - timedelta(seconds=1)
        )  # cron has not run yet
        db.commit()
    login(client, "sari")
    assert client.get(INBOX).json() == []


def test_granted_request_shows_the_key_it_was_wrapped_for(client):
    admin_id = setup_admin(client)
    alumni_id = setup_alumni(client)
    with SessionLocal() as db:
        admin, alumni = db.get(User, admin_id), db.get(User, alumni_id)
        key = db.scalar(select(UserPublicKey).where(UserPublicKey.user_id == admin_id))
        req = request(db, alumni, admin, status="granted")
        grant(db, req, key)
        key.revoked_at = (
            NOW  # the admin moved on, but this grant still uses the old key
        )
        key.fingerprint = "1" * 64
        db.commit()
    login(client, "sari")
    (item,) = client.get(INBOX).json()
    assert item["status"] == "granted" and item["admin_fingerprint"] == "1" * 64


def test_inbox_is_for_alumni_only(client):
    setup_admin(client)
    login(client, "root")
    assert client.get(INBOX).status_code == 403
