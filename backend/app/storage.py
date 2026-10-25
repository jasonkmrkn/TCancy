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
