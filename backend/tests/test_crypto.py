import inspect
import os

import pytest
from Crypto.Cipher import AES, DES

from app import config, crypto

CHUNK = crypto.CHUNK_SIZE
ITEM = "file:0f8d6a2e"

CIPHERS = {
    "aes": (crypto.aes_encrypt, crypto.aes_decrypt),
    "des": (crypto.des_encrypt, crypto.des_decrypt),
    "rc4": (crypto.rc4_encrypt, crypto.rc4_decrypt),
}
ALGS = pytest.mark.parametrize("alg", list(CIPHERS))
CTR = pytest.mark.parametrize("alg, module", [("aes", AES), ("des", DES)])


def chunks(data):
    return [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [b""]


def run(fn, data, salt, nonce, item=ITEM):
    return b"".join(fn(c, salt, nonce, item, i) for i, c in enumerate(chunks(data)))


def rc4_reference(key, data, drop=0):
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    out, i, j = bytearray(), 0, 0
    for n in range(drop + len(data)):
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        if n >= drop:
            out.append(data[n - drop] ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


# --- round trip --------------------------------------------------------------


@ALGS
@pytest.mark.parametrize(
    "data", [b"", b"\x00", os.urandom(2 * CHUNK), os.urandom(5_000_000)],
    ids=["empty", "1byte", "2chunks", "5mb"],
)
def test_round_trip(alg, data):
    enc, dec = CIPHERS[alg]
    salt, nonce = crypto.new_params(alg, ITEM)
    ct = run(enc, data, salt, nonce)
    assert len(ct) == len(data)
    if data:
        assert ct != data
    assert run(dec, ct, salt, nonce) == data


def test_new_params_sizes():
    for alg, nonce_len in [("aes", 8), ("des", 4), ("rc4", None)]:
        salt, nonce = crypto.new_params(alg, ITEM)
        assert len(salt) == 16
        assert nonce is None if nonce_len is None else len(nonce) == nonce_len


def test_derive_key_is_deterministic_and_bound_to_salt_and_context():
    salt = bytes(16)
    key = crypto.derive_key(salt, "aes:" + ITEM, 32)
    assert len(key) == 32
    assert crypto.derive_key(salt, "aes:" + ITEM, 32) == key
    assert crypto.derive_key(b"\x01" * 16, "aes:" + ITEM, 32) != key
    assert crypto.derive_key(salt, "des:" + ITEM, 32) != key


# --- test vectors ------------------------------------------------------------


def test_aes_ctr_nist_vector():
    # NIST SP 800-38A F.5.5 CTR-AES256.Encrypt
    key = bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
    pt = bytes.fromhex(
        "6bc1bee22e409f96e93d7e117393172a" "ae2d8a571e03ac9c9eb76fac45af8e51"
        "30c81c46a35ce411e5fbc1191a0a52ef" "f69f2445df4f9b17ad2b417be66c3710"
    )
    ct = bytes.fromhex(
        "601ec313775789a5b7a7f504bbf3d228" "f443e3ca4d62b59aca84e990cacaf5c5"
        "2b0930daa23de94ce87017ba2d84988d" "dfc9c58db67aada613c2dd08457941a6"
    )
    nonce = bytes.fromhex("f0f1f2f3f4f5f6f7")
    assert crypto._ctr(AES, key, nonce, pt, 0xF8F9FAFBFCFDFEFF) == ct
    assert crypto._ctr(AES, key, nonce, ct, 0xF8F9FAFBFCFDFEFF) == pt


def test_des_ctr_known_answer():
    # DES_k(0123456789ABCDEF) = 85E813540F0AB405, used as the CTR keystream block.
    key = bytes.fromhex("133457799BBCDFF1")
    ct = crypto._ctr(DES, key, bytes.fromhex("01234567"), bytes(8), 0x89ABCDEF)
    assert ct == bytes.fromhex("85E813540F0AB405")


def test_rc4_reference_matches_known_vector():
    assert rc4_reference(b"Key", b"Plaintext") == bytes.fromhex("BBF316E8D940AF0AD3")


def test_rc4_drops_first_1024_keystream_bytes(monkeypatch):
    key = bytes(range(16))
    monkeypatch.setattr(crypto, "derive_key", lambda salt, context, length: key)
    data = os.urandom(3000)
    assert crypto.rc4_encrypt(data, bytes(16), None, ITEM, 0) == rc4_reference(key, data, drop=1024)


# --- distinct inputs give distinct output ------------------------------------


@ALGS
def test_different_salt_nonce_or_item_change_the_ciphertext(alg):
    enc, _ = CIPHERS[alg]
    data = b"3578012345678901" * 4
    salt, nonce = crypto.new_params(alg, ITEM)
    other_salt, other_nonce = crypto.new_params(alg, ITEM)
    base = enc(data, salt, nonce, ITEM, 0)
    assert enc(data, other_salt, nonce, ITEM, 0) != base
    assert enc(data, salt, nonce, "file:other", 0) != base
    if nonce is not None:
        assert enc(data, salt, other_nonce, ITEM, 0) != base


# --- chunked equals whole stream ---------------------------------------------


@CTR
def test_chunked_ctr_equals_one_whole_stream(alg, module):
    enc, _ = CIPHERS[alg]
    data = os.urandom(2 * CHUNK + 12345)
    salt, nonce = crypto.new_params(alg, ITEM)
    key = crypto.derive_key(salt, alg + ":" + ITEM, crypto.KEY_BYTES[alg])
    whole = module.new(key, module.MODE_CTR, nonce=nonce, initial_value=0).encrypt(data)
    assert run(enc, data, salt, nonce) == whole


def test_rc4_uses_a_key_per_chunk():
    salt, _ = crypto.new_params("rc4", ITEM)
    data = bytes(64)
    assert crypto.rc4_encrypt(data, salt, None, ITEM, 0) != crypto.rc4_encrypt(data, salt, None, ITEM, 1)


# --- guards ------------------------------------------------------------------


def test_des_counter_overflow_guard():
    salt, nonce = crypto.new_params("des", ITEM)
    last = 2**32 // (CHUNK // DES.block_size) - 1  # chunk ending exactly at counter 2^32 - 1
    data = bytes(CHUNK)
    ct = crypto.des_encrypt(data, salt, nonce, ITEM, last)
    assert crypto.des_decrypt(ct, salt, nonce, ITEM, last) == data
    with pytest.raises(ValueError, match="CTR counter overflow"):
        crypto.des_encrypt(b"x", salt, nonce, ITEM, last + 1)


def test_aes_counter_overflow_guard():
    salt, nonce = crypto.new_params("aes", ITEM)
    with pytest.raises(ValueError, match="CTR counter overflow"):
        crypto.aes_encrypt(b"x", salt, nonce, ITEM, 2**64 // (CHUNK // AES.block_size))


@ALGS
def test_chunk_larger_than_chunk_size_is_rejected(alg):
    enc, _ = CIPHERS[alg]
    salt, nonce = crypto.new_params(alg, ITEM)
    with pytest.raises(ValueError):
        enc(bytes(CHUNK + 1), salt, nonce, ITEM, 0)


def test_des_key_rejected_by_library_is_rederived_with_new_salt(monkeypatch):
    real_new = DES.new
    rejected = []

    def picky_new(key, *args, **kwargs):
        if not rejected:
            rejected.append(key)
            raise ValueError("weak key")
        return real_new(key, *args, **kwargs)

    salts = iter([b"\x01" * 16, b"\x02" * 16])
    monkeypatch.setattr(crypto.secrets, "token_bytes", lambda n: next(salts) if n == 16 else bytes(n))
    monkeypatch.setattr(crypto.DES, "new", picky_new)
    salt, nonce = crypto.new_params("des", ITEM)
    assert rejected and salt == b"\x02" * 16 and len(nonce) == 4


@pytest.mark.parametrize("value", ["", "not base64!", "AAAAAAAAAAAAAAAAAAAAAA=="])
def test_invalid_master_key_is_rejected_without_echoing_it(monkeypatch, value):
    monkeypatch.setattr(config, "MASTER_KEY", value)
    with pytest.raises(RuntimeError) as exc:
        crypto.derive_key(bytes(16), "aes:" + ITEM, 32)
    if value:
        assert value not in str(exc.value)


# --- no ECB, no leaks ---------------------------------------------------------


def test_no_ecb_mode_in_module():
    assert "MODE_ECB" not in inspect.getsource(crypto)


@CTR
def test_identical_blocks_encrypt_differently(alg, module):
    enc, _ = CIPHERS[alg]
    salt, nonce = crypto.new_params(alg, ITEM)
    ct = enc(bytes(2 * module.block_size), salt, nonce, ITEM, 0)
    assert ct[:module.block_size] != ct[module.block_size:]


def test_nothing_is_logged_or_printed(caplog, capsys):
    caplog.set_level("DEBUG")
    for alg, (enc, dec) in CIPHERS.items():
        salt, nonce = crypto.new_params(alg, ITEM)
        dec(enc(b"secret plaintext", salt, nonce, ITEM, 0), salt, nonce, ITEM, 0)
    with pytest.raises(ValueError) as exc:
        crypto.des_encrypt(b"x", salt := bytes(16), nonce := b"\xab\xcd\xef\x01", ITEM, 2**13)
    assert nonce.hex() not in str(exc.value) and salt.hex() not in str(exc.value)
    assert caplog.records == []
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
