import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

from app import config, tokens

UID = uuid.uuid4()
SECRET = config.SESSION_SECRET


def claims(**over):
    now = datetime.now(timezone.utc)
    data = {
        "sub": str(UID),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": "abc",
        "typ": "access",
    }
    data.update(over)
    return {k: v for k, v in data.items() if v is not None}


def sign(payload, secret=None, alg="HS256"):
    return jwt.encode(payload, SECRET if secret is None else secret, algorithm=alg)


# --- access tokens -------------------------------------------------------------


def test_roundtrip():
    assert tokens.verify_access_token(tokens.create_access_token(UID)) == UID


def test_claims_carry_identity_only():
    token = tokens.create_access_token(UID)
    decoded = jwt.decode(token, options={"verify_signature": False})
    # No role, username or status: those are read from the database on every request.
    assert set(decoded) == {"sub", "iat", "exp", "jti", "typ"}
    assert decoded["sub"] == str(UID)
    assert decoded["typ"] == "access"
    assert decoded["exp"] - decoded["iat"] == config.ACCESS_TOKEN_MINUTES * 60 == 900


def test_every_token_has_its_own_jti():
    a = jwt.decode(tokens.create_access_token(UID), options={"verify_signature": False})
    b = jwt.decode(tokens.create_access_token(UID), options={"verify_signature": False})
    assert a["jti"] != b["jti"]


def test_expired_token_is_rejected():
    past = datetime.now(timezone.utc) - timedelta(minutes=16)
    assert tokens.verify_access_token(tokens.create_access_token(UID, now=past)) is None


def test_token_close_to_expiry_still_works():
    almost = datetime.now(timezone.utc) - timedelta(minutes=14)
    assert tokens.verify_access_token(tokens.create_access_token(UID, now=almost)) == UID


def test_tampered_signature_is_rejected():
    token = tokens.create_access_token(UID)
    flipped = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert tokens.verify_access_token(flipped) is None


def test_tampered_payload_is_rejected():
    head, body, sig = tokens.create_access_token(UID).split(".")
    other = sign(claims(sub=str(uuid.uuid4()))).split(".")[1]
    assert tokens.verify_access_token(f"{head}.{other}.{sig}") is None


def test_token_signed_with_another_secret_is_rejected():
    assert tokens.verify_access_token(sign(claims(), secret="another-secret-" + "x" * 32)) is None


def test_alg_none_is_rejected():
    forged = jwt.encode(claims(), None, algorithm="none")
    assert tokens.verify_access_token(forged) is None


@pytest.mark.filterwarnings("ignore:The HMAC key")  # our 50-byte key is short for SHA-512
@pytest.mark.parametrize("alg", ["HS384", "HS512"])
def test_other_hmac_algorithms_are_rejected(alg):
    assert tokens.verify_access_token(sign(claims(), alg=alg)) is None


@pytest.mark.parametrize("missing", ["sub", "iat", "exp", "jti", "typ"])
def test_missing_required_claim_is_rejected(missing):
    assert tokens.verify_access_token(sign(claims(**{missing: None}))) is None


def test_wrong_token_type_is_rejected():
    assert tokens.verify_access_token(sign(claims(typ="refresh"))) is None


@pytest.mark.parametrize("sub", ["", "1", "admin", "not-a-uuid", "1" * 40])
def test_subject_must_be_a_uuid(sub):
    assert tokens.verify_access_token(sign(claims(sub=sub))) is None


@pytest.mark.parametrize("junk", [None, "", "abc", "a.b.c", "....", "x" * 5000])
def test_junk_is_not_a_token(junk):
    assert tokens.verify_access_token(junk) is None


# --- SESSION_SECRET ------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "short", "x" * 31])
def test_missing_or_short_secret_is_a_server_error(monkeypatch, bad):
    good = tokens.create_access_token(UID)
    monkeypatch.setattr(config, "SESSION_SECRET", bad)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        tokens.check_secret()
    with pytest.raises(RuntimeError):
        tokens.create_access_token(UID)
    # Not "not logged in": a misconfigured server must be loud.
    with pytest.raises(RuntimeError):
        tokens.verify_access_token(good)
    # ...but no cookie at all never needs the secret.
    assert tokens.verify_access_token(None) is None


def test_exactly_32_bytes_is_enough(monkeypatch):
    monkeypatch.setattr(config, "SESSION_SECRET", "x" * 32)
    tokens.check_secret()


def test_rotating_the_secret_invalidates_old_tokens(monkeypatch):
    old = tokens.create_access_token(UID)
    monkeypatch.setattr(config, "SESSION_SECRET", "a-different-secret-" + "y" * 32)
    assert tokens.verify_access_token(old) is None
    assert tokens.verify_access_token(tokens.create_access_token(UID)) == UID


# --- refresh tokens ------------------------------------------------------------


def test_refresh_tokens_are_random_and_long():
    seen = {tokens.new_refresh_token() for _ in range(200)}
    assert len(seen) == 200
    assert all(len(t) >= 43 for t in seen)  # 32 random bytes, base64url


def test_refresh_hash_is_stable_hex_and_differs_from_token():
    t = tokens.new_refresh_token()
    h = tokens.hash_refresh_token(t)
    assert h == tokens.hash_refresh_token(t)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert h != t
    assert tokens.hash_refresh_token(t + "x") != h


def test_refresh_expiry_is_seven_days():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert tokens.refresh_expiry(base) == base + timedelta(days=7)
    assert config.REFRESH_TOKEN_DAYS == 7


# --- configuration -------------------------------------------------------------


def run_config(env_extra, drop=()):
    import os

    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_extra)
    backend = Path(__file__).resolve().parent.parent
    out = subprocess.run(
        [sys.executable, "-c", "from app import config; print(config.COOKIE_SECURE)"],
        cwd=backend, env=env, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_cookie_secure_defaults_to_true():
    assert run_config({}, drop=["COOKIE_SECURE"]) == "True"


def test_cookie_secure_can_be_turned_off_explicitly():
    assert run_config({"COOKIE_SECURE": "false"}) == "False"
    assert run_config({"COOKIE_SECURE": "true"}) == "True"