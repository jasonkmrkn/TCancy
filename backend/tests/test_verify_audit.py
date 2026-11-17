"""A2 V9 (Raynald): every verification step leaves an audit entry, and no secret ever does."""
import base64
import json
import uuid
from datetime import timedelta

import pytest
from Crypto.PublicKey import RSA
from sqlalchemy import select, update

from app import audit, cli
from app.db import SessionLocal
from app.models import AuditLog, VerificationRequest
from test_job import login
from test_proof_purge import NOW
from test_verify_requests import VECTORS, do_grant, granted_world

FINGERPRINT_A = VECTORS["rsa"]["fingerprint_sha256_hex"]


@pytest.fixture
def keks(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "PROOF_KEKS", {1: b"\x11" * 32})
    monkeypatch.setattr(config, "PROOF_KEK_VERSION", 1)
    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "assignment")


def entries(prefix="verify."):
    with SessionLocal() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.action.startswith(prefix)).order_by(AuditLog.created_at)).all()
        return [(r.action, r.target_type, r.target_id, r.details or {}) for r in rows]


def actions():
    return [a for a, *_ in entries()]


# --- details(): the new value shapes ---------------------------------------------------


def test_details_takes_ids_fingerprints_and_short_words():
    grant = uuid.uuid4()
    value = audit.details(grant=grant, fingerprint="ab" * 32, reason="key_revoked", ext="pdf", size=7)
    assert value == {"grant": str(grant), "fingerprint": "ab" * 32, "reason": "key_revoked", "ext": "pdf", "size": 7}


@pytest.mark.parametrize("key, value", [
    ("fingerprint", "AB" * 32),                       # not lower-case hex
    ("fingerprint", "ab" * 31),                       # not 64 characters
    ("fingerprint", base64.b64encode(b"k" * 384).decode()),  # an access code is not a fingerprint
    ("reason", "Budi Santoso"),                       # free text
    ("ext", "../etc/passwd"),
    ("note", "anything"),                             # text under a key that takes none
    ("grant", str(uuid.uuid4())),                     # an id must come as uuid.UUID, not text
])
def test_details_refuses_other_text(key, value):
    with pytest.raises(ValueError) as caught:
        audit.details(**{key: value})
    assert value not in str(caught.value)


def test_record_accepts_what_details_builds(client):
    with SessionLocal() as db:
        audit.record(db, actor_id=None, actor_role=None, action="verify.test",
                     details=audit.details(grant=uuid.uuid4(), fingerprint="0" * 64))
        db.commit()
    assert entries()[0][3]["fingerprint"] == "0" * 64


# --- the whole flow ------------------------------------------------------------------


def test_the_flow_is_logged_step_by_step(client, keks):
    req_id, _ = granted_world(client)  # key registered, proof uploaded, request created
    assert actions() == ["verify.key.register", "verify.proof.upload", "verify.request.create"]
    _, _, _, reg = entries()[0]
    assert reg["fingerprint"] == FINGERPRINT_A and reg["valid_days"] == 365
    _, target, _, up = entries()[1]
    assert target == "user" and up["ext"] == "pdf" and up["size"] == 10_000

    r = do_grant(client, req_id)
    assert r.status_code == 201
    action, target, target_id, details = entries()[-1]
    assert (action, target, str(target_id)) == ("verify.grant", "verification_request", req_id)
    assert details["grant"] == r.json()["grant_id"]
    assert details["fingerprint"] == FINGERPRINT_A and details["kek_version"] == 1

    login(client, "root")
    for _ in range(2):
        assert client.get(f"/api/v1/admin/proof-grants/{req_id}/package").status_code == 200
    opens = [d for a, _, _, d in entries() if a == "verify.package.open"]
    assert [d["first"] for d in opens] == [1, 0]  # every download is logged, the first is marked


def test_no_secret_ever_reaches_the_log(client, keks):
    req_id, content = granted_world(client)
    code = do_grant(client, req_id).json()["access_code"]
    login(client, "root")
    client.get(f"/api/v1/admin/proof-grants/{req_id}/package")
    with SessionLocal() as db:
        dumped = json.dumps([r.details for r in db.scalars(select(AuditLog))])
    assert code not in dumped and code[:40] not in dumped
    assert content[:32].hex() not in dumped
    assert "%PDF" not in dumped


def test_a_new_key_logs_the_revoke_with_the_grants_it_ended(client, keks):
    req_id, _ = granted_world(client)
    do_grant(client, req_id)
    login(client, "root")
    spki_b = base64.b64encode(RSA.generate(3072).public_key().export_key("DER")).decode()
    assert client.post("/api/v1/admin/keys", json={"spki": spki_b}).status_code == 201
    revoke = [d for a, _, _, d in entries() if a == "verify.key.revoke"]
    assert revoke == [{"fingerprint": FINGERPRINT_A, "grants_ended": 1}]
    assert actions().count("verify.key.register") == 2  # same transaction as the revoke


def test_deleting_the_proof_is_logged(client, keks):
    granted_world(client)
    assert client.delete("/api/v1/me/verification-proof").status_code == 204
    assert actions()[-1] == "verify.proof.delete"


def test_a_refused_request_leaves_no_entry(client, keks):
    req_id, _ = granted_world(client)
    login(client, "root")
    with SessionLocal() as db:
        alumni_id = db.get(VerificationRequest, uuid.UUID(req_id)).alumni_id
    assert client.post(f"/api/v1/admin/alumni/{alumni_id}/proof-request").status_code == 409
    assert actions().count("verify.request.create") == 1  # the 409 rolled its entry back


def test_the_cron_purge_is_logged_without_an_actor(client, keks):
    req_id, _ = granted_world(client)
    with SessionLocal() as db:
        db.execute(update(VerificationRequest).values(expires_at=NOW - timedelta(minutes=1)))
        db.commit()
    assert cli.main(["purge-expired-proofs"]) == 0
    action, _, _, details = entries()[-1]
    assert (action, details) == ("verify.purge_expired", {"requests": 1})
    with SessionLocal() as db:
        row = db.scalars(select(AuditLog).where(AuditLog.action == "verify.purge_expired")).one()
        assert row.actor_id is None
