import errno
import logging
import os
import re
import secrets
import stat
import threading

from app import config

log = logging.getLogger("tcancy.storage")

CHUNK_SIZE = 64 * 1024

_KEY = re.compile(r"[0-9a-f]{32}")  # used with fullmatch: "$" would let a trailing newline through
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_NEW_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_KEY_TRIES = 8  # new random keys to try when one already exists (it practically never does)
_DIR_TRIES = 5  # times to re-create a shard directory that was removed under our feet
_REMOVED = (errno.ENOENT, errno.EINVAL)  # a directory removed while we held it: ENOENT on Linux, EINVAL on macOS
_shard_lock = threading.Lock()  # a shard directory is never removed between a writer opening it and using it


class StorageError(Exception):
    pass


def _open_root(create: bool = False) -> int:
    """UPLOAD_DIR itself comes from the configuration, so it may be a symlink (a mounted volume)."""
    root = config.UPLOAD_DIR
    if create:
        os.makedirs(root, mode=0o700, exist_ok=True)
    return os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)


def _open_shard(root_fd: int, key: str, create: bool = False) -> int:
    shard = key[:2]
    for attempt in range(_DIR_TRIES):
        created = False
        if create:
            try:
                os.mkdir(shard, 0o700, dir_fd=root_fd)
                created = True
            except FileExistsError:
                pass
        try:
            fd = os.open(shard, _DIR_FLAGS, dir_fd=root_fd)  # a symlink in its place is refused
        except FileNotFoundError:
            if create and attempt < _DIR_TRIES - 1:  # a delete() removed the empty directory just now
                continue
            raise
        if created:
            try:
                os.fchmod(fd, 0o700)  # whatever the umask said
                os.fsync(root_fd)
            except BaseException:
                os.close(fd)
                raise
        return fd
    raise AssertionError("unreachable")


def _unlink(name: str, dir_fd: int) -> None:
    try:
        os.unlink(name, dir_fd=dir_fd)
    except OSError:
        pass


def _new_key() -> str:
    return secrets.token_hex(16)


def write(chunks) -> str:
    """Frozen interface: write an iterable of bytes atomically and return the storage key.

    Raises StorageError on any OS error. Any other exception raised while the chunks are
    produced (for example the 413 of an upload that turned out to be too large) passes through
    unchanged. Either way nothing is left behind: no .part file and no half-written key.
    """
    try:
        root_fd = _open_root(create=True)
    except OSError as e:
        raise StorageError(str(e)) from e
    fds: list[int] = []  # shard descriptors to close
    part: tuple[int, str] | None = None  # (shard fd, name) of the temporary file
    linked: tuple[int, str] | None = None  # (shard fd, name) once the final name exists
    shards: set[str] = set()
    try:
        key = _new_key()
        part_name = key + ".part"
        for attempt in range(_DIR_TRIES):
            with _shard_lock:  # delete() cannot remove the shard before the .part file is in it
                shard_fd = _open_shard(root_fd, key, create=True)
                fds.append(shard_fd)
                shards.add(key[:2])
                try:
                    fd = os.open(part_name, _NEW_FLAGS, 0o600, dir_fd=shard_fd)
                except OSError as e:  # the shard was removed by another process
                    if e.errno not in _REMOVED or attempt == _DIR_TRIES - 1:
                        raise
                    continue
            break
        part = (shard_fd, part_name)
        try:
            os.fchmod(fd, 0o600)
            for chunk in chunks:
                view = memoryview(chunk).cast("B")
                while view:
                    view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        last_error: OSError | None = None
        for attempt in range(_KEY_TRIES * _DIR_TRIES):
            with _shard_lock:
                target_fd = _open_shard(root_fd, key, create=True)
                fds.append(target_fd)
                shards.add(key[:2])
                try:
                    os.link(part_name, key, src_dir_fd=shard_fd, dst_dir_fd=target_fd)
                except FileExistsError:  # that key is taken: the data is safe in .part, try another
                    key = _new_key()
                    continue
                except OSError as e:  # the target shard was removed by another process
                    if e.errno not in _REMOVED:
                        raise
                    last_error = e
                    continue
                linked = (target_fd, key)
            break
        else:
            raise OSError(errno.EEXIST, "could not give the file its final name") from last_error
        os.unlink(part_name, dir_fd=shard_fd)
        part = None
        os.fsync(target_fd)
        if target_fd != shard_fd:
            os.fsync(shard_fd)
        return key
    except OSError as e:
        _undo(root_fd, part, linked, shards)
        raise StorageError(str(e)) from e
    except BaseException:
        _undo(root_fd, part, linked, shards)
        raise
    finally:
        for fd in fds:
            os.close(fd)
        os.close(root_fd)


def _undo(root_fd: int, part, linked, shards) -> None:
    """Remove what a failed write left: the temporary file, a key nobody was told about, and
    shard directories that are empty now (rmdir refuses to remove one that is not)."""
    if part is not None:
        _unlink(part[1], part[0])
    if linked is not None:
        _unlink(linked[1], linked[0])
    with _shard_lock:
        for shard in shards:
            try:
                os.rmdir(shard, dir_fd=root_fd)
            except OSError:
                pass


def _open_for_read(key: str) -> int:
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise StorageError("not a storage key")
    try:
        root_fd = _open_root()
        try:
            shard_fd = _open_shard(root_fd, key)
            try:
                fd = os.open(key, _READ_FLAGS, dir_fd=shard_fd)
            finally:
                os.close(shard_fd)
        finally:
            os.close(root_fd)
    except OSError as e:
        raise StorageError(str(e)) from e
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise StorageError("not a regular file")
    except BaseException:
        os.close(fd)
        raise
    return fd


def read(storage_key: str):
    """Frozen interface: iterate the stored bytes in 64 KiB chunks.

    Raises StorageError, on first iteration, when the key cannot be read: it is not a key,
    the file is missing, or it is a symlink or anything but a regular file.
    """
    fd = _open_for_read(storage_key)
    try:
        while True:
            try:
                chunk = os.read(fd, CHUNK_SIZE)
            except OSError as e:
                raise StorageError(str(e)) from e
            if not chunk:
                return
            yield chunk
    finally:
        os.close(fd)


def delete(storage_key: str) -> None:
    """Remove a stored file and its shard directory when that is empty now.

    Never raises: a key that is not there (or not a key at all) is nothing to do, and a file
    that cannot be removed is logged. A symlink under a key is removed itself, never followed.
    """
    if not isinstance(storage_key, str) or not _KEY.fullmatch(storage_key):
        return
    try:
        root_fd = _open_root()
    except OSError:
        return
    try:
        with _shard_lock:
            try:
                shard_fd = _open_shard(root_fd, storage_key)
            except OSError:
                return
            try:
                os.unlink(storage_key, dir_fd=shard_fd)
            except FileNotFoundError:
                pass
            except OSError as e:
                log.warning("could not delete stored file %s (%s)", storage_key, type(e).__name__)
            finally:
                os.close(shard_fd)
            try:
                os.rmdir(storage_key[:2], dir_fd=root_fd)
            except OSError:
                pass
    finally:
        os.close(root_fd)