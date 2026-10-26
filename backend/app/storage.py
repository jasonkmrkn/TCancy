import os
import uuid
from pathlib import Path

from app import config


class StorageError(Exception):
    pass


def _path(key: str) -> Path:
    return Path(config.UPLOAD_DIR) / key


def save(data: bytes, ext: str) -> str:
    """Write the bytes under a fresh random key and return the key."""
    key = uuid.uuid4().hex + "." + ext
    try:
        os.makedirs(config.UPLOAD_DIR, exist_ok=True)
        with open(_path(key), "wb") as f:
            f.write(data)
    except OSError as e:
        raise StorageError(str(e)) from e
    return key


def path_of(key: str) -> Path:
    return _path(key)


def exists(key: str) -> bool:
    return _path(key).is_file()


def delete(key: str) -> None:
    try:
        _path(key).unlink()
    except OSError:
        pass

CHUNK_SIZE = 64 * 1024


# STUB-RAYNALD
def write(chunks) -> str:
    """Frozen interface: write an iterable of bytes atomically and return the storage key.

    The key is a bare UUID hex with no extension: the extension lives in documents.ext and
    nothing reads it from the key. Data goes to a temporary file first and os.replace moves
    it into place, so a failed write never leaves a half-written key behind.
    Raises StorageError on any OS error.
    """
    key = uuid.uuid4().hex
    tmp = _path(key + ".tmp")
    try:
        os.makedirs(config.UPLOAD_DIR, exist_ok=True)
        with open(tmp, "wb") as f:
            for chunk in chunks:
                f.write(chunk)
        os.replace(tmp, _path(key))
    except OSError as e:
        raise StorageError(str(e)) from e
    finally:
        tmp.unlink(missing_ok=True)
    return key


# STUB-RAYNALD
def read(storage_key: str):
    """Frozen interface: iterate the stored bytes in 64 KiB chunks.

    Raises StorageError, on first iteration, when the key cannot be read.
    """
    try:
        with open(_path(storage_key), "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                yield chunk
    except OSError as e:
        raise StorageError(str(e)) from e