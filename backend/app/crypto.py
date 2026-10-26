"""Cryptographic primitives (AES, DES, RC4) shared by the vault and document storage.

Every item gets its own key: HKDF-SHA256 over MASTER_KEY with a random 16-byte salt and a
context naming the algorithm and the item ("aes:file:<id>"). Data is processed in chunks of
CHUNK_SIZE; the caller splits a stream and passes each chunk with its index. In CTR mode,
chunk i starts at counter i * CHUNK_SIZE / block_size, so chunked output equals one whole
stream. RC4 cannot seek, so each chunk gets its own key ("rc4:<item>:<i>").

Pure functions: no database, no storage, no logging. ECB is never used.
"""
import base64
import binascii
import secrets

from Crypto.Cipher import AES, ARC4, DES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF

from app import config

CHUNK_SIZE = 4 * 1024 * 1024
SALT_BYTES = 16
NONCE_BYTES = {"aes": 8, "des": 4, "rc4": None}
KEY_BYTES = {"aes": 32, "des": 8, "rc4": 16}
RC4_DROP = 1024


def _master_key() -> bytes:
    try:
        key = base64.b64decode(config.MASTER_KEY, validate=True)
    except (binascii.Error, ValueError):
        key = b""
    if len(key) != 32:
        raise RuntimeError("MASTER_KEY must be base64 of 32 bytes, e.g. `openssl rand -base64 32`")
    return key


def derive_key(salt: bytes, context: str, length: int) -> bytes:
    return HKDF(_master_key(), length, salt, SHA256, context=context.encode())


def new_params(algorithm: str, item: str) -> tuple[bytes, bytes | None]:
    """A fresh (salt, nonce) for one item. Retries with a new salt if DES rejects the key."""
    nonce_len = NONCE_BYTES[algorithm]
    while True:
        salt = secrets.token_bytes(SALT_BYTES)
        nonce = None if nonce_len is None else secrets.token_bytes(nonce_len)
        if algorithm != "des":
            return salt, nonce
        try:
            DES.new(derive_key(salt, "des:" + item, KEY_BYTES["des"]), DES.MODE_CTR, nonce=nonce)
        except ValueError:
            continue
        return salt, nonce


def _ctr(module, key: bytes, nonce: bytes, data: bytes, start: int) -> bytes:
    """CTR from block `start`. Raises instead of letting the counter wrap."""
    block = module.block_size
    blocks = -(-len(data) // block)
    if start + blocks > 2 ** (8 * (block - len(nonce))):
        raise ValueError("CTR counter overflow")
    return module.new(key, module.MODE_CTR, nonce=nonce, initial_value=start).encrypt(data)


def _check(chunk: bytes) -> None:
    if len(chunk) > CHUNK_SIZE:
        raise ValueError("chunk larger than CHUNK_SIZE")


def aes_encrypt(chunk: bytes, salt: bytes, nonce: bytes | None, item: str, index: int) -> bytes:
    _check(chunk)
    key = derive_key(salt, "aes:" + item, KEY_BYTES["aes"])
    return _ctr(AES, key, nonce, chunk, index * CHUNK_SIZE // AES.block_size)


def aes_decrypt(chunk: bytes, salt: bytes, nonce: bytes | None, item: str, index: int) -> bytes:
    return aes_encrypt(chunk, salt, nonce, item, index)


def des_encrypt(chunk: bytes, salt: bytes, nonce: bytes | None, item: str, index: int) -> bytes:
    _check(chunk)
    key = derive_key(salt, "des:" + item, KEY_BYTES["des"])
    return _ctr(DES, key, nonce, chunk, index * CHUNK_SIZE // DES.block_size)


def des_decrypt(chunk: bytes, salt: bytes, nonce: bytes | None, item: str, index: int) -> bytes:
    return des_encrypt(chunk, salt, nonce, item, index)


def rc4_encrypt(chunk: bytes, salt: bytes, nonce: bytes | None, item: str, index: int) -> bytes:
    _check(chunk)
    key = derive_key(salt, "rc4:%s:%d" % (item, index), KEY_BYTES["rc4"])
    return ARC4.new(key, drop=RC4_DROP).encrypt(chunk)


def rc4_decrypt(chunk: bytes, salt: bytes, nonce: bytes | None, item: str, index: int) -> bytes:
    return rc4_encrypt(chunk, salt, nonce, item, index)
