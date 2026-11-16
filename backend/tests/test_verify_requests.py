"""Proof requests and grants: admin asks, alumni grants, admin opens."""

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from sqlalchemy import select, update

from app import config, storage, verify_crypto
from app.db import SessionLocal
from app.models import ProofGrant, User, UserPublicKey, VerificationRequest
from test_job import login, make_user
from test_proof_purge import NOW, admin_key, exists, grant, proof, request
from test_verify_proof import proof_bytes


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
    expected = datetime.now(timezone.utc) + timedelta(
        days=config.PROOF_REQUEST_TTL_DAYS
    )
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


# ---------- POST /me/verification-requests/{id}/grant ----------

VECTORS = json.loads((Path(__file__).parent / "verify_crypto_vectors.json").read_text())
PRIVATE_KEY = RSA.import_key(base64.b64decode(VECTORS["rsa"]["private_pkcs8_b64"]))


@pytest.fixture
def keks(monkeypatch):
    monkeypatch.setattr(config, "PROOF_KEKS", {1: b"\x11" * 32})
    monkeypatch.setattr(config, "PROOF_KEK_VERSION", 1)
    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "assignment")


def granted_world(client, content=None):
    """A real admin key (from the test vectors), a real uploaded proof and a pending request."""
    setup_admin(client, with_key=False)
    login(client, "root")
    assert (
        client.post(
            "/api/v1/admin/keys", json={"spki": VECTORS["rsa"]["public_spki_b64"]}
        ).status_code
        == 201
    )
    alumni_id = setup_alumni(client, with_proof=False)
    login(client, "sari")
    content = content or proof_bytes(10_000)
    assert (
        client.post(
            "/api/v1/me/verification-proof", files={"file": ("bukti.pdf", content)}
        ).status_code
        == 201
    )
    login(client, "root")
    req_id = ask(client, alumni_id).json()["id"]
    login(client, "sari")
    return req_id, content


def do_grant(client, req_id):
    return client.post(f"/api/v1/me/verification-requests/{req_id}/grant")


def open_package(grant_row, k):
    """Decrypt the stored package the way the admin's browser will (V7)."""
    data = b"".join(storage.read(grant_row.pkg_storage_key))
    step = config.PROOF_CHUNK_SIZE + verify_crypto.TAG_BYTES
    pieces = [data[i : i + step] for i in range(0, len(data), step)]
    out = b""
    for i, piece in enumerate(pieces):
        pos = i.to_bytes(4, "big")
        cipher = AES.new(k, AES.MODE_GCM, nonce=bytes(grant_row.pkg_nonce) + pos)
        cipher.update(grant_row.id.bytes + pos + bytes([i == len(pieces) - 1]))
        out += cipher.decrypt_and_verify(piece[:-16], piece[-16:])
    return out


def test_grant_gives_an_access_code_the_admin_can_open(client, keks):
    req_id, content = granted_world(client)
    r = do_grant(client, req_id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["access_code"]) == 512
    assert body["admin_fingerprint"] == VECTORS["rsa"]["fingerprint_sha256_hex"]

    k = PKCS1_OAEP.new(PRIVATE_KEY, hashAlgo=SHA256).decrypt(
        base64.b64decode(body["access_code"])
    )
    with SessionLocal() as db:
        row = db.get(ProofGrant, uuid.UUID(body["grant_id"]))
        assert verify_crypto.unwrap_kek(row) == k  # the server copy holds the same K
        assert open_package(row, k) == content
        assert row.pkg_size == len(b"".join(storage.read(row.pkg_storage_key)))
        assert row.opened_at is None
        assert db.get(VerificationRequest, uuid.UUID(req_id)).status == "granted"


def test_a_proof_larger_than_one_chunk_still_opens(client, keks, monkeypatch):
    monkeypatch.setattr(config, "PROOF_CHUNK_SIZE", 4096)  # 20 kB proof -> 5 chunks
    req_id, content = granted_world(client, proof_bytes(20_000))
    body = do_grant(client, req_id).json()
    k = PKCS1_OAEP.new(PRIVATE_KEY, hashAlgo=SHA256).decrypt(
        base64.b64decode(body["access_code"])
    )
    with SessionLocal() as db:
        assert (
            open_package(db.get(ProofGrant, uuid.UUID(body["grant_id"])), k) == content
        )


def test_grant_twice_is_409(client, keks):
    req_id, _ = granted_world(client)
    assert do_grant(client, req_id).status_code == 201
    r = do_grant(client, req_id)
    assert r.status_code == 409 and r.json()["detail"] == "REQUEST_ENDED"


def test_expired_request_cannot_be_granted(client, keks):
    req_id, _ = granted_world(client)
    with SessionLocal() as db:
        db.execute(
            update(VerificationRequest).values(expires_at=NOW - timedelta(seconds=1))
        )
        db.commit()
    assert do_grant(client, req_id).json()["detail"] == "REQUEST_ENDED"


def test_admin_key_gone_since_the_request_is_409(client, keks):
    req_id, _ = granted_world(client)
    with SessionLocal() as db:
        db.execute(update(UserPublicKey).values(expires_at=NOW - timedelta(seconds=1)))
        db.commit()
    assert do_grant(client, req_id).json()["detail"] == "NO_PUBLIC_KEY"


def test_proof_deleted_since_the_request_is_409(client, keks):
    req_id, _ = granted_world(client)
    assert client.delete("/api/v1/me/verification-proof").status_code == 204
    assert do_grant(client, req_id).json()["detail"] == "NO_PROOF"


def test_another_alumni_gets_404(client, keks):
    req_id, _ = granted_world(client)
    make_user(client, "tono", "alumni", "pending")
    login(client, "tono")
    r = do_grant(client, req_id)
    assert r.status_code == 404 and r.json()["detail"] == "REQUEST_NOT_FOUND"


@pytest.mark.parametrize("target", ["not-a-uuid", str(uuid.uuid4())])
def test_unknown_request_is_404(client, target):
    setup_alumni(client, with_proof=False)
    login(client, "sari")
    assert do_grant(client, target).json()["detail"] == "REQUEST_NOT_FOUND"


def test_failed_commit_leaves_no_package_file(client, keks, monkeypatch):
    req_id, _ = granted_world(client)
    written = []
    real_write = storage.write

    def spy(chunks):
        written.append(real_write(chunks))
        return written[-1]

    def boom(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(storage, "write", spy)
    monkeypatch.setattr(verify_crypto, "wrap_kek", boom)
    with pytest.raises(RuntimeError):
        do_grant(client, req_id)
    assert written and not exists(written[0])
    with SessionLocal() as db:
        assert db.scalar(select(ProofGrant)) is None
        assert db.get(VerificationRequest, uuid.UUID(req_id)).status == "pending"
