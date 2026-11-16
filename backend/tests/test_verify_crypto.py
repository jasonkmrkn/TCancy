import base64
import hashlib
import inspect
import json
import logging
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Hash import SHA1, SHA256
from Crypto.PublicKey import ECC, RSA
from Crypto.Util.asn1 import DerSequence
from fastapi import HTTPException

from app import config, verify_crypto

MiB = 1024 * 1024
TAG = verify_crypto.TAG_BYTES

VECTORS = json.loads((Path(__file__).parent / "verify_crypto_vectors.json").read_text())
PRIVATE = RSA.import_key(base64.b64decode(VECTORS["rsa"]["private_pkcs8_b64"]))
SPKI = base64.b64decode(VECTORS["rsa"]["public_spki_b64"])

GRANT = uuid.UUID("0b6e2f3c-1d4a-4c5b-8e9f-a0b1c2d3e4f5")
RECIPIENT = uuid.UUID("9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d")


@pytest.fixture(autouse=True)
def keks(monkeypatch):
    monkeypatch.setattr(config, "PROOF_KEKS", {1: b"\x11" * 32, 2: b"\x22" * 32})
    monkeypatch.setattr(config, "PROOF_KEK_VERSION", 1)


@pytest.fixture(scope="module")
def small_spki():
    return RSA.generate(2048).public_key().export_key("DER")


def grant_of(wrapped, grant_id=GRANT, recipient=RECIPIENT, **changes):
    return SimpleNamespace(id=grant_id, recipient_key_id=recipient, **{**wrapped, **changes})


def flip(data: bytes, at: int) -> bytes:
    out = bytearray(data)
    out[at] ^= 0x01
    return bytes(out)


def open_package(parts, k, grant_id, pkg_nonce):
    """What the browser does: chunk i with iv pkg_nonce || i and AAD grant || i || last."""
    out = b""
    for i, part in enumerate(parts):
        pos = i.to_bytes(4, "big")
        cipher = AES.new(k, AES.MODE_GCM, nonce=pkg_nonce + pos)
        cipher.update(grant_id.bytes + pos + bytes([i == len(parts) - 1]))
        out += cipher.decrypt_and_verify(part[:-TAG], part[-TAG:])
    return out


def status(exc_info):
    return exc_info.value.status_code, exc_info.value.detail


# --- K ------------------------------------------------------------------------------------

def test_share_keys_are_32_fresh_bytes():
    a, b = verify_crypto.new_share_key(), verify_crypto.new_share_key()
    assert len(a) == len(b) == 32 and a != b


# --- KEK wrap ----------------------------------------------------------------------------

def test_kek_round_trip_with_the_grant_columns():
    k = verify_crypto.new_share_key()
    wrapped = verify_crypto.wrap_kek(k, grant_id=GRANT, recipient_key_id=RECIPIENT)
    assert set(wrapped) == {"kek_version", "kek_salt", "kek_nonce", "k_wrapped"}
    assert wrapped["kek_version"] == 1
    assert len(wrapped["kek_salt"]) == 16 and len(wrapped["kek_nonce"]) == 12
    assert len(wrapped["k_wrapped"]) == 32 + TAG and k not in wrapped["k_wrapped"]
    assert verify_crypto.unwrap_kek(grant_of(wrapped)) == k


def test_two_wraps_of_the_same_key_differ():
    k = verify_crypto.new_share_key()
    a = verify_crypto.wrap_kek(k, grant_id=GRANT, recipient_key_id=RECIPIENT)
    b = verify_crypto.wrap_kek(k, grant_id=GRANT, recipient_key_id=RECIPIENT)
    assert a["kek_salt"] != b["kek_salt"] and a["kek_nonce"] != b["kek_nonce"]
    assert a["k_wrapped"] != b["k_wrapped"]


@pytest.mark.parametrize("change", [
    "ciphertext", "tag", "nonce", "salt", "version", "grant_id", "recipient", "short", "long",
])
def test_a_changed_wrap_is_an_integrity_error(change):
    wrapped = verify_crypto.wrap_kek(verify_crypto.new_share_key(), grant_id=GRANT, recipient_key_id=RECIPIENT)
    other = uuid.uuid4()
    grant = {
        "ciphertext": lambda: grant_of(wrapped, k_wrapped=flip(wrapped["k_wrapped"], 0)),
        "tag": lambda: grant_of(wrapped, k_wrapped=flip(wrapped["k_wrapped"], -1)),
        "nonce": lambda: grant_of(wrapped, kek_nonce=flip(wrapped["kek_nonce"], 0)),
        "salt": lambda: grant_of(wrapped, kek_salt=flip(wrapped["kek_salt"], 0)),
        "version": lambda: grant_of(wrapped, kek_version=2),  # another configured KEK
        "grant_id": lambda: grant_of(wrapped, grant_id=other),
        "recipient": lambda: grant_of(wrapped, recipient=other),
        "short": lambda: grant_of(wrapped, k_wrapped=wrapped["k_wrapped"][:-1]),
        "long": lambda: grant_of(wrapped, k_wrapped=wrapped["k_wrapped"] + b"\x00"),
    }[change]()
    with pytest.raises(HTTPException) as e:
        verify_crypto.unwrap_kek(grant)
    assert status(e) == (500, "INTEGRITY_ERROR")


def test_a_kek_version_removed_from_the_environment_ends_the_grant(monkeypatch):
    wrapped = verify_crypto.wrap_kek(verify_crypto.new_share_key(), grant_id=GRANT, recipient_key_id=RECIPIENT)
    monkeypatch.setattr(config, "PROOF_KEKS", {2: b"\x22" * 32})
    with pytest.raises(HTTPException) as e:
        verify_crypto.unwrap_kek(grant_of(wrapped))
    assert status(e) == (410, "GRANT_ENDED")
    with pytest.raises(HTTPException) as e:
        verify_crypto.unwrap_kek(grant_of(wrapped, kek_version=3))
    assert status(e) == (410, "GRANT_ENDED")


def test_rotation_new_wraps_use_the_active_version_and_old_ones_still_open(monkeypatch):
    k = verify_crypto.new_share_key()
    old = verify_crypto.wrap_kek(k, grant_id=GRANT, recipient_key_id=RECIPIENT)
    monkeypatch.setattr(config, "PROOF_KEK_VERSION", 2)
    new = verify_crypto.wrap_kek(k, grant_id=GRANT, recipient_key_id=RECIPIENT)
    assert (old["kek_version"], new["kek_version"]) == (1, 2)
    assert verify_crypto.unwrap_kek(grant_of(old)) == verify_crypto.unwrap_kek(grant_of(new)) == k


def test_wrapping_without_the_active_root_key_is_a_configuration_error(monkeypatch):
    monkeypatch.setattr(config, "PROOF_KEKS", {})
    with pytest.raises(RuntimeError):
        verify_crypto.wrap_kek(verify_crypto.new_share_key(), grant_id=GRANT, recipient_key_id=RECIPIENT)


def test_the_kek_does_not_depend_on_master_key(monkeypatch):
    k = verify_crypto.new_share_key()
    wrapped = verify_crypto.wrap_kek(k, grant_id=GRANT, recipient_key_id=RECIPIENT)
    monkeypatch.setattr(config, "MASTER_KEY", base64.b64encode(b"\x42" * 32).decode())
    assert verify_crypto.unwrap_kek(grant_of(wrapped)) == k


@pytest.mark.parametrize("k", [b"", b"\x00" * 31, b"\x00" * 33, "x" * 32])
def test_only_a_32_byte_key_is_wrapped(k):
    with pytest.raises(ValueError):
        verify_crypto.wrap_kek(k, grant_id=GRANT, recipient_key_id=RECIPIENT)
    with pytest.raises(ValueError):
        verify_crypto.wrap_for_recipient(SPKI, k)


# --- public key and access code -----------------------------------------------------------

def test_fingerprint_is_lowercase_sha256_hex_of_the_spki():
    fingerprint = verify_crypto.check_public_key(SPKI)
    assert fingerprint == hashlib.sha256(SPKI).hexdigest() == VECTORS["rsa"]["fingerprint_sha256_hex"]
    assert fingerprint == fingerprint.lower() and len(fingerprint) == 64


def invalid_keys(small_spki):
    n = PRIVATE.n
    return {
        "rsa 2048": small_spki,
        "exponent 3": RSA.construct((n, 3)).export_key("DER"),
        "pem": PRIVATE.public_key().export_key("PEM"),
        "pkcs1": DerSequence([n, PRIVATE.e]).encode(),
        "private pkcs8": base64.b64decode(VECTORS["rsa"]["private_pkcs8_b64"]),
        "ec p-256": ECC.generate(curve="P-256").public_key().export_key(format="DER"),
        "trailing byte": SPKI + b"\x00",
        "truncated": SPKI[:-1],
        "garbage": b"not a key",
        "empty": b"",
        "text": SPKI.hex(),
    }


@pytest.mark.parametrize("name", [
    "rsa 2048", "exponent 3", "pem", "pkcs1", "private pkcs8", "ec p-256",
    "trailing byte", "truncated", "garbage", "empty", "text",
])
def test_only_rsa_3072_spki_der_is_a_valid_public_key(name, small_spki):
    spki = invalid_keys(small_spki)[name]
    for call in (lambda: verify_crypto.check_public_key(spki),
                 lambda: verify_crypto.wrap_for_recipient(spki, verify_crypto.new_share_key())):
        with pytest.raises(HTTPException) as e:
            call()
        assert status(e) == (422, "INVALID_PUBLIC_KEY")


def test_access_code_opens_with_the_private_key_and_oaep_sha256():
    k = verify_crypto.new_share_key()
    code = verify_crypto.wrap_for_recipient(SPKI, k)
    assert len(code) == 512
    raw = base64.b64decode(code)
    assert len(raw) == 384
    assert PKCS1_OAEP.new(PRIVATE, hashAlgo=SHA256).decrypt(raw) == k
    with pytest.raises(ValueError):
        PKCS1_OAEP.new(PRIVATE).decrypt(raw)  # pycryptodome's default, SHA-1
    with pytest.raises(ValueError):
        PKCS1_OAEP.new(PRIVATE, hashAlgo=SHA1).decrypt(raw)


def test_two_access_codes_for_the_same_key_differ():
    k = verify_crypto.new_share_key()
    assert verify_crypto.wrap_for_recipient(SPKI, k) != verify_crypto.wrap_for_recipient(SPKI, k)


# --- package --------------------------------------------------------------------------------

@pytest.mark.parametrize("size", [1, 4 * MiB, 4 * MiB + 1, 10 * MiB])
def test_package_round_trip(size):
    data = bytes(i % 251 for i in range(size))
    k = verify_crypto.new_share_key()
    pkg_nonce, parts = verify_crypto.encrypt_package([data], k, GRANT)
    parts = list(parts)
    assert len(pkg_nonce) == 8
    assert len(parts) == -(-size // config.PROOF_CHUNK_SIZE)
    assert all(len(p) == config.PROOF_CHUNK_SIZE + TAG for p in parts[:-1])
    assert open_package(parts, k, GRANT, pkg_nonce) == data


def test_package_parts_do_not_depend_on_how_the_input_is_split(monkeypatch):
    data = bytes(i % 251 for i in range(4 * MiB + 100))
    k = verify_crypto.new_share_key()
    monkeypatch.setattr(verify_crypto.secrets, "token_bytes", lambda n: b"\x07" * n)
    _, whole = verify_crypto.encrypt_package([data], k, GRANT)
    pieces = [data[i:i + 65536] for i in range(0, len(data), 65536)]
    _, split = verify_crypto.encrypt_package(pieces, k, GRANT)
    assert list(whole) == list(split)


def test_an_empty_proof_still_gives_one_chunk():
    k = verify_crypto.new_share_key()
    pkg_nonce, parts = verify_crypto.encrypt_package([], k, GRANT)
    parts = list(parts)
    assert [len(p) for p in parts] == [TAG]
    assert open_package(parts, k, GRANT, pkg_nonce) == b""


def tampered(parts, how):
    parts = list(parts)
    if how == "drop last":
        return parts[:-1]
    if how == "swap last two":
        return parts[:-2] + [parts[-1], parts[-2]]
    if how == "change last":
        return parts[:-1] + [flip(parts[-1], 0)]
    if how == "change tag":
        return parts[:-1] + [flip(parts[-1], -1)]
    if how == "append a copy":
        return parts + [parts[-1]]
    raise AssertionError(how)


@pytest.mark.parametrize("how", ["drop last", "swap last two", "change last", "change tag", "append a copy"])
def test_a_changed_package_fails_to_decrypt(how):
    data = b"x" * 40
    k = verify_crypto.new_share_key()
    pkg_nonce, parts = verify_crypto.encrypt_package([data], k, GRANT, chunk_size=16)
    with pytest.raises(ValueError):
        open_package(tampered(parts, how), k, GRANT, pkg_nonce)


def test_a_package_is_bound_to_its_grant():
    k = verify_crypto.new_share_key()
    pkg_nonce, parts = verify_crypto.encrypt_package([b"proof"], k, GRANT)
    with pytest.raises(ValueError):
        open_package(list(parts), k, uuid.uuid4(), pkg_nonce)


def test_two_packages_get_different_nonces():
    k = verify_crypto.new_share_key()
    a_nonce, a = verify_crypto.encrypt_package([b"same proof"], k, GRANT)
    b_nonce, b = verify_crypto.encrypt_package([b"same proof"], k, GRANT)
    assert a_nonce != b_nonce and list(a) != list(b)


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_chunk_size_must_be_positive(chunk_size):
    with pytest.raises(ValueError):
        verify_crypto.encrypt_package([b"x"], verify_crypto.new_share_key(), GRANT, chunk_size=chunk_size)


# --- fixed vectors for the frontend (tests/verify_crypto_vectors.json) ---------------------

def test_vector_rsa_key_pair_is_a_valid_3072_bit_pair():
    assert PRIVATE.has_private() and PRIVATE.size_in_bits() == 3072 and PRIVATE.e == 65537
    assert PRIVATE.public_key().export_key("DER") == SPKI
    assert verify_crypto.check_public_key(SPKI) == VECTORS["rsa"]["fingerprint_sha256_hex"]


def test_vector_access_code_opens_to_the_expected_key():
    code = VECTORS["access_code"]["code_b64"]
    assert len(code) == 512
    k = PKCS1_OAEP.new(PRIVATE, hashAlgo=SHA256).decrypt(base64.b64decode(code))
    assert k.hex() == VECTORS["access_code"]["expected_k_hex"]


def test_vector_package_is_what_encrypt_package_makes(monkeypatch):
    v = VECTORS["package"]
    grant_id = uuid.UUID(v["grant_id"])
    k = bytes.fromhex(v["k_hex"])
    pkg_nonce = bytes.fromhex(v["pkg_nonce_hex"])
    plaintext = bytes.fromhex(v["plaintext_hex"])
    assert grant_id.bytes.hex() == v["grant_id_hex"] and plaintext.decode() == v["plaintext_utf8"]

    monkeypatch.setattr(verify_crypto.secrets, "token_bytes", lambda n: pkg_nonce)
    nonce, parts = verify_crypto.encrypt_package([plaintext], k, grant_id, chunk_size=v["chunk_size"])
    parts = list(parts)
    assert nonce == pkg_nonce
    assert [p.hex() for p in parts] == [c["ciphertext_and_tag_hex"] for c in v["chunks"]]

    for i, c in enumerate(v["chunks"]):
        last = i == len(v["chunks"]) - 1
        assert c["index"] == i and c["last"] == last
        assert c["iv_hex"] == (pkg_nonce + i.to_bytes(4, "big")).hex()
        assert c["additional_data_hex"] == (grant_id.bytes + i.to_bytes(4, "big") + bytes([last])).hex()
    assert open_package(parts, k, grant_id, pkg_nonce) == plaintext


# --- no secrets in logs, only secrets for randomness ---------------------------------------

def test_nothing_is_logged(caplog):
    caplog.set_level(logging.DEBUG)
    k = verify_crypto.new_share_key()
    wrapped = verify_crypto.wrap_kek(k, grant_id=GRANT, recipient_key_id=RECIPIENT)
    verify_crypto.unwrap_kek(grant_of(wrapped))
    verify_crypto.wrap_for_recipient(SPKI, k)
    _, parts = verify_crypto.encrypt_package([b"secret proof"], k, GRANT)
    list(parts)
    for bad in (grant_of(wrapped, k_wrapped=flip(wrapped["k_wrapped"], 0)), grant_of(wrapped, kek_version=3)):
        with pytest.raises(HTTPException):
            verify_crypto.unwrap_kek(bad)
    assert caplog.records == []


def test_source_uses_secrets_for_randomness_and_never_ecb():
    source = inspect.getsource(verify_crypto)
    assert "import logging" not in source and "print(" not in source
    assert "MODE_ECB" not in source
    assert "import random" not in source and "from random" not in source
