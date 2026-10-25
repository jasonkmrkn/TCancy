"""Password hashing with Argon2id (argon2-cffi).

Everything that stores or checks a password goes through this module, so the
algorithm and its parameters live in exactly one place.
"""
import secrets

from argon2 import PasswordHasher, profiles
from argon2.exceptions import InvalidHashError, VerificationError

hasher = PasswordHasher.from_parameters(profiles.RFC_9106_LOW_MEMORY)

DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))

def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """True only when `password` matches `stored_hash`. Never raises for bad input."""
    try:
        return hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """True when the hash was made with parameters different from the current ones."""
    return hasher.check_needs_rehash(stored_hash)