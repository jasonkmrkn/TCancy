"""A2 V3 (Axel): admins register their RSA-3072 public key at /admin/keys."""
import base64
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from Crypto.PublicKey import ECC, RSA
from sqlalchemy import select, text

from app import config
from app.db import SessionLocal, engine
from app.models import User, UserPublicKey, VerificationRequest
from test_job import login, make_user
from test_proof_purge import exists, grant, request

URL = "/api/v1/admin/keys"
VECTORS = json.loads((Path(__file__).parent / "verify_crypto_vectors.json").read_text())
SPKI_A = VECTORS["rsa"]["public_spki_b64"]


@pytest.fixture(scope="module")
def spki_b():
    return base64.b64encode(RSA.generate(3072).public_key().export_key("DER")).decode()


def as_admin(client, username="root"):
    uid = make_user(client, username, "admin")
    login(client, username)
    return uuid.UUID(uid)


def keys_of(user_id):
    with SessionLocal() as db:
        return list(db.scalars(select(UserPublicKey).where(UserPublicKey.user_id == user_id)
                               .order_by(UserPublicKey.created_at)))


def post(client, spki):
    return client.post(URL, json={"spki": spki})


def test_valid_key_is_stored_and_shown(client):
    uid = as_admin(client)
    r = post(client, SPKI_A)
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"id", "algorithm", "fingerprint", "created_at", "expires_at"}
    assert body["fingerprint"] == hashlib.sha256(base64.b64decode(SPKI_A)).hexdigest()
    assert body["fingerprint"] == VECTORS["rsa"]["fingerprint_sha256_hex"]
    expires = datetime.fromisoformat(body["expires_at"])
    expected = datetime.now(timezone.utc) + timedelta(days=config.ADMIN_KEY_TTL_DAYS)
    assert abs((expires - expected).total_seconds()) < 60
    (key,) = keys_of(uid)
    assert key.public_key_spki == base64.b64decode(SPKI_A) and key.revoked_at is None
    assert client.get(URL).json() == body
    assert "spki" not in client.get(URL).text


def test_get_is_404_without_a_key(client):
    as_admin(client)
    r = client.get(URL)
    assert (r.status_code, r.json()["detail"]) == (404, "KEY_NOT_FOUND")


def _der(key):
    return base64.b64encode(key.export_key("DER")).decode()


@pytest.mark.parametrize("make", [
    lambda: "not base64 !!",
    lambda: "",
    lambda: base64.b64encode(b"garbage").decode(),
    lambda: _der(RSA.generate(2048).public_key()),
    lambda: base64.b64encode(RSA.import_key(base64.b64decode(SPKI_A)).export_key("PEM")).decode(),
    lambda: VECTORS["rsa"]["private_pkcs8_b64"],
    lambda: base64.b64encode(ECC.generate(curve="P-256").public_key().export_key(format="DER")).decode(),
])
def test_invalid_keys_are_422(client, make):
    uid = as_admin(client)
    r = post(client, make())
    assert (r.status_code, r.json()["detail"]) == (422, "INVALID_PUBLIC_KEY")
    assert keys_of(uid) == []


def test_extra_fields_and_huge_bodies_are_rejected(client):
    as_admin(client)
    assert client.post(URL, json={"spki": SPKI_A, "user_id": str(uuid.uuid4())}).status_code == 422
    assert post(client, "A" * 5000).status_code == 422


def test_new_key_revokes_the_old_one(client, spki_b):
    uid = as_admin(client)
    first = post(client, SPKI_A).json()
    second = post(client, spki_b).json()
    old, new = keys_of(uid)
    assert str(old.id) == first["id"] and old.revoked_at is not None
    assert str(new.id) == second["id"] and new.revoked_at is None
    assert client.get(URL).json() == second


def test_new_key_ends_the_grants_wrapped_for_the_old_one(client, spki_b):
    uid = as_admin(client)
    old_id = uuid.UUID(post(client, SPKI_A).json()["id"])
    alumni_id = uuid.UUID(make_user(client, "sari", "alumni", "pending"))
    with SessionLocal() as db:
        req = request(db, db.get(User, alumni_id), db.get(User, uid), "granted")
        _, pkg = grant(db, req, db.get(UserPublicKey, old_id))
        db.commit()
        req_id = req.id
    assert exists(pkg)
    assert post(client, spki_b).status_code == 201
    with SessionLocal() as db:
        req = db.get(VerificationRequest, req_id)
        assert (req.status, req.close_reason) == ("closed", "key_revoked")
    assert not exists(pkg)


def test_expired_key_counts_as_none(client, spki_b):
    uid = as_admin(client)
    post(client, SPKI_A)
    with engine.begin() as conn:
        conn.execute(text("UPDATE user_public_keys SET expires_at = now() - interval '1 minute'"))
    assert client.get(URL).status_code == 404
    assert post(client, spki_b).status_code == 201  # the expired one is revoked, no unique clash
    assert client.get(URL).json()["fingerprint"] == keys_of(uid)[-1].fingerprint


@pytest.mark.parametrize("role, status, code", [
    ("alumni", "active", 403), ("alumni", "pending", 403), ("applicant", "active", 403), ("admin", "pending", 403),
])
def test_non_admins_are_rejected(client, role, status, code):
    make_user(client, "someone", role, status)
    login(client, "someone")
    assert post(client, SPKI_A).status_code == code
    assert client.get(URL).status_code == code


def test_not_logged_in_is_401(client):
    assert client.get(URL).status_code == 401


def test_admins_only_see_and_replace_their_own_key(client, spki_b):
    a = as_admin(client, "root")
    post(client, SPKI_A)
    client.post("/api/v1/auth/logout")
    b = as_admin(client, "root2")
    assert client.get(URL).status_code == 404
    assert post(client, spki_b).status_code == 201
    assert client.get(URL).json()["fingerprint"] != VECTORS["rsa"]["fingerprint_sha256_hex"]
    (key_a,) = keys_of(a)
    assert key_a.revoked_at is None and len(keys_of(b)) == 1
