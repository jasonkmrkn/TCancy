"""A2 V6 (Raynald): proofs, packages and wrapped keys disappear when they must."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import account, cli, proof_purge, storage
from app.db import SessionLocal
from app.models import (
    ProofGrant,
    User,
    UserPublicKey,
    VerificationProof,
    VerificationProofCopy,
    VerificationRequest,
)

NOW = datetime.now(timezone.utc)


def exists(key: str) -> bool:
    try:
        b"".join(storage.read(key))
        return True
    except storage.StorageError:
        return False


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def user(db, role, status="active"):
    u = User(username="u%s" % uuid.uuid4().hex[:10], password_hash="x", role=role, status=status)
    db.add(u)
    db.flush()
    return u


def admin_key(db, admin):
    k = UserPublicKey(
        user_id=admin.id, algorithm="RSA-OAEP-3072-SHA256", public_key_spki=b"spki",
        fingerprint="0" * 64, expires_at=NOW + timedelta(days=365),
    )
    db.add(k)
    db.flush()
    return k


def proof(db, alumni, copies=("aes", "des", "rc4")):
    p = VerificationProof(alumni_id=alumni.id, ext="pdf", size=10, sha256="a" * 64)
    db.add(p)
    db.flush()
    keys = []
    for alg in copies:
        key = storage.write([b"ciphertext of " + alg.encode()])
        keys.append(key)
        db.add(VerificationProofCopy(
            proof_id=p.id, algorithm=alg, salt=b"s" * 16, nonce=b"n" * 8,
            storage_key=key, ciphertext_size=10,
        ))
    db.flush()
    return p, keys


def request(db, alumni, admin, status="pending", expires_at=None):
    r = VerificationRequest(
        alumni_id=alumni.id, admin_id=admin.id, status=status,
        expires_at=expires_at or NOW + timedelta(days=14),
    )
    db.add(r)
    db.flush()
    return r


def grant(db, req, key):
    pkg = storage.write([b"package"])
    g = ProofGrant(
        request_id=req.id, recipient_key_id=key.id, k_wrapped=b"k" * 48, kek_salt=b"s" * 16,
        kek_nonce=b"n" * 12, kek_version=1, pkg_nonce=b"p" * 8, pkg_storage_key=pkg, pkg_size=7,
    )
    db.add(g)
    db.flush()
    return g, pkg


@pytest.fixture
def world(db):
    """One alumni with a proof, a granted request to admin A and a pending one to admin B."""
    alumni = user(db, "alumni", "pending")
    admin_a, admin_b = user(db, "admin"), user(db, "admin")
    key_a, key_b = admin_key(db, admin_a), admin_key(db, admin_b)
    p, copy_keys = proof(db, alumni)
    granted = request(db, alumni, admin_a, "granted")
    g, pkg = grant(db, granted, key_a)
    pending = request(db, alumni, admin_b, "pending")
    db.commit()
    return dict(alumni=alumni, admin_a=admin_a, admin_b=admin_b, key_a=key_a, key_b=key_b,
                proof=p, copy_keys=copy_keys, granted=granted, pending=pending, grant=g, pkg=pkg)


# --- purge_for_alumni (approve / reject) ------------------------------------------------


def test_decision_removes_proof_copies_grants_and_files(db, world):
    keys = proof_purge.purge_for_alumni(db, world["alumni"].id, "approved")
    assert set(keys) == set(world["copy_keys"]) | {world["pkg"]}
    db.commit()
    proof_purge.delete_files(keys)

    assert count(db, VerificationProof) == 0
    assert count(db, VerificationProofCopy) == 0
    assert count(db, ProofGrant) == 0
    assert not any(exists(k) for k in keys)
    for req in (world["granted"], world["pending"]):
        db.refresh(req)
        assert (req.status, req.close_reason) == ("closed", "approved")
        assert req.closed_at is not None
    assert db.get(User, world["alumni"].id) is not None  # the account itself stays


def test_nothing_is_committed_and_no_file_goes_until_the_caller_says_so(db, world):
    keys = proof_purge.purge_for_alumni(db, world["alumni"].id, "rejected")
    db.rollback()
    assert count(db, VerificationProof) == 1
    assert count(db, ProofGrant) == 1
    assert all(exists(k) for k in keys)
    db.refresh(world["pending"])
    assert world["pending"].status == "pending"


def test_decision_twice_is_harmless(db, world):
    keys = proof_purge.purge_for_alumni(db, world["alumni"].id, "approved")
    db.commit()
    proof_purge.delete_files(keys)
    assert proof_purge.purge_for_alumni(db, world["alumni"].id, "approved") == []
    db.commit()
    db.refresh(world["granted"])
    assert world["granted"].close_reason == "approved"  # the first reason is kept


def test_a_file_that_is_already_gone_is_not_an_error(db, world):
    storage.delete(world["pkg"])
    storage.delete(world["copy_keys"][0])
    keys = proof_purge.purge_for_alumni(db, world["alumni"].id, "approved")
    db.commit()
    proof_purge.delete_files(keys)
    proof_purge.delete_files(keys + ["not-a-key", "0" * 32])
    assert not any(exists(k) for k in keys)


def test_other_alumni_are_not_touched(db, world):
    other = user(db, "alumni", "pending")
    _, other_keys = proof(db, other)
    db.commit()
    keys = proof_purge.purge_for_alumni(db, world["alumni"].id, "approved")
    db.commit()
    proof_purge.delete_files(keys)
    assert count(db, VerificationProof) == 1
    assert all(exists(k) for k in other_keys)


# --- end_grants_for_alumni (new proof uploaded) -----------------------------------------


def test_new_proof_ends_granted_requests_but_keeps_pending_ones_and_the_proof(db, world):
    keys = proof_purge.end_grants_for_alumni(db, world["alumni"].id)
    assert keys == [world["pkg"]]
    db.commit()
    proof_purge.delete_files(keys)

    assert count(db, ProofGrant) == 0
    assert not exists(world["pkg"])
    db.refresh(world["granted"])
    db.refresh(world["pending"])
    assert (world["granted"].status, world["granted"].close_reason) == ("closed", "proof_replaced")
    assert world["pending"].status == "pending"
    assert count(db, VerificationProof) == 1  # the router replaces the proof itself
    assert all(exists(k) for k in world["copy_keys"])


# --- end_grants_for_key (admin key revoked) ---------------------------------------------


def test_revoked_key_ends_only_the_grants_wrapped_for_it(db, world):
    other_alumni = user(db, "alumni", "pending")
    proof(db, other_alumni)
    to_b = request(db, other_alumni, world["admin_b"], "granted")
    _, pkg_b = grant(db, to_b, world["key_b"])
    db.commit()

    keys = proof_purge.end_grants_for_key(db, world["key_a"].id)
    assert keys == [world["pkg"]]
    db.commit()
    proof_purge.delete_files(keys)

    db.refresh(world["granted"])
    db.refresh(to_b)
    assert (world["granted"].status, world["granted"].close_reason) == ("closed", "key_revoked")
    assert to_b.status == "granted" and exists(pkg_b)
    assert count(db, ProofGrant) == 1
    assert db.get(UserPublicKey, world["key_a"].id) is not None  # revoking the key is the router's job


# --- purge_expired (cron) ---------------------------------------------------------------


def test_expired_requests_close_and_the_proof_goes_when_nothing_else_needs_it(db, world):
    for req in (world["granted"], world["pending"]):
        req.expires_at = NOW - timedelta(minutes=1)
    db.commit()

    assert proof_purge.purge_expired(db) == 2
    assert count(db, ProofGrant) == 0
    assert count(db, VerificationProof) == 0
    assert not exists(world["pkg"])
    assert not any(exists(k) for k in world["copy_keys"])
    for req in (world["granted"], world["pending"]):
        db.refresh(req)
        assert (req.status, req.close_reason) == ("expired", "expired")

    assert proof_purge.purge_expired(db) == 0  # running it again does nothing


def test_the_proof_stays_while_another_request_still_needs_it(db, world):
    world["granted"].expires_at = NOW - timedelta(minutes=1)
    db.commit()

    assert proof_purge.purge_expired(db) == 1
    db.refresh(world["pending"])
    assert world["pending"].status == "pending"
    assert count(db, VerificationProof) == 1
    assert all(exists(k) for k in world["copy_keys"])
    assert not exists(world["pkg"])


def test_requests_that_have_not_expired_are_left_alone(db, world):
    assert proof_purge.purge_expired(db) == 0
    assert proof_purge.purge_expired(db, now=NOW + timedelta(days=13)) == 0
    assert count(db, ProofGrant) == 1 and exists(world["pkg"])
    assert proof_purge.purge_expired(db, now=NOW + timedelta(days=15)) == 2


def test_closed_requests_are_not_expired_again(db, world):
    keys = proof_purge.purge_for_alumni(db, world["alumni"].id, "rejected")
    db.commit()
    proof_purge.delete_files(keys)
    assert proof_purge.purge_expired(db, now=NOW + timedelta(days=30)) == 0
    db.refresh(world["pending"])
    assert world["pending"].close_reason == "rejected"


# --- CLI --------------------------------------------------------------------------------


def test_cli_purge_expired_proofs(db, world, capsys):
    world["pending"].expires_at = NOW - timedelta(minutes=1)
    db.commit()
    assert cli.main(["purge-expired-proofs"]) == 0
    assert "Expired 1 verification request(s)." in capsys.readouterr().out
    assert cli.main(["purge-expired-proofs"]) == 0
    assert "Expired 0 verification request(s)." in capsys.readouterr().out


# --- account deletion -------------------------------------------------------------------


def test_deleting_the_alumni_account_removes_proof_and_package_files(db, world):
    files = world["copy_keys"] + [world["pkg"]]
    account.delete_account(db, db.get(User, world["alumni"].id))
    assert not any(exists(k) for k in files)
    assert count(db, VerificationProof) == 0 and count(db, ProofGrant) == 0


def test_deleting_an_admin_account_removes_the_packages_made_for_it(db, world):
    account.delete_account(db, db.get(User, world["admin_a"].id))
    assert not exists(world["pkg"])
    assert count(db, ProofGrant) == 0
    assert all(exists(k) for k in world["copy_keys"])  # the alumni's proof is not the admin's
    assert count(db, VerificationProof) == 1
