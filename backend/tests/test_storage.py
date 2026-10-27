import errno
import logging
import os
import re
import signal
import stat
import threading
import uuid
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from app import config, storage

CHUNKS = [b"hello ", b"world", b"x" * 200_000, b"!"]
DATA = b"".join(CHUNKS)


def root():
    return config.UPLOAD_DIR


def tree(top=None):
    top = top or root()
    return sorted(os.path.relpath(os.path.join(d, n), top) for d, dirs, files in os.walk(top) for n in dirs + files)


def path_of(key):
    return os.path.join(root(), key[:2], key)


def mode_of(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


def stored(data=b"payload"):
    return storage.write(iter([data]))


def contents(key):
    return b"".join(storage.read(key))


@contextmanager
def deadline(seconds=10):
    def fail(signum, frame):
        raise AssertionError("still running after %d seconds: it hangs" % seconds)

    old = signal.signal(signal.SIGALRM, fail)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


@pytest.fixture(params=[0o000, 0o022, 0o077], ids=["umask000", "umask022", "umask077"])
def umask(request):
    old = os.umask(request.param)
    yield request.param
    os.umask(old)


@pytest.fixture
def keys(monkeypatch):
    """Make the next keys the ones given (the real ones are random)."""

    def use(*values):
        it = iter(values)
        monkeypatch.setattr(storage, "_new_key", lambda: next(it))

    return use


def key_in(shard, filler):
    return shard + filler * (32 - len(shard))


# --- keys and layout ------------------------------------------------------------


def test_a_key_is_32_random_hex_characters_without_an_extension():
    first, second = stored(), stored()
    assert re.fullmatch(r"[0-9a-f]{32}", first) and re.fullmatch(r"[0-9a-f]{32}", second)
    assert first != second


def test_the_file_lives_in_a_directory_named_after_the_first_two_characters_of_the_key():
    key = stored()
    assert tree() == [key[:2], key[:2] + "/" + key]


def test_directories_are_0700_and_files_0600_whatever_the_umask(umask):
    key = stored()
    assert mode_of(os.path.join(root(), key[:2])) == 0o700
    assert mode_of(path_of(key)) == 0o600


def test_a_missing_upload_directory_is_created_0700(tmp_path, monkeypatch, umask):
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "does" / "not" / "exist"))
    key = stored()
    assert mode_of(config.UPLOAD_DIR) == 0o700
    assert contents(key) == b"payload"


def test_an_upload_directory_that_is_a_symlink_to_a_volume_still_works(tmp_path, monkeypatch):
    volume = tmp_path / "volume"
    volume.mkdir()
    link = tmp_path / "uploads"
    link.symlink_to(volume)
    monkeypatch.setattr(config, "UPLOAD_DIR", str(link))
    key = stored()
    assert (volume / key[:2] / key).read_bytes() == b"payload"


def test_nothing_but_the_final_name_is_left_and_it_has_one_link():
    key = stored()
    assert not any(name.endswith(".part") for name in tree())
    assert os.stat(path_of(key)).st_nlink == 1


def test_the_old_unused_helpers_are_gone():
    assert not any(hasattr(storage, name) for name in ("save", "path_of", "exists"))


# --- write ----------------------------------------------------------------------


def test_what_is_written_is_what_is_read():
    assert contents(storage.write(iter(CHUNKS))) == DATA


def test_write_takes_any_iterable_and_any_bytes_like_chunk():
    assert contents(storage.write(chunk for chunk in CHUNKS)) == DATA
    assert contents(storage.write([bytearray(b"ab"), memoryview(b"cd"), b"", b"ef"])) == b"abcdef"
    assert contents(storage.write([])) == b""


def test_the_final_name_does_not_exist_until_the_data_is_complete():
    seen = []

    def producer():
        yield b"first"
        seen.append(tree())
        yield b"second"
        seen.append(tree())

    key = storage.write(producer())
    for during in seen:
        files = [name for name in during if "/" in name]
        assert len(files) == 1 and files[0].endswith(".part")
    assert contents(key) == b"firstsecond"


def test_a_part_file_is_private_while_it_is_written():
    modes = []

    def producer():
        yield b"data"
        modes.extend(mode_of(os.path.join(root(), name)) for name in tree() if name.endswith(".part"))

    storage.write(producer())
    assert modes == [0o600]


def test_a_chunk_that_is_not_bytes_is_refused_and_leaves_nothing():
    with pytest.raises(TypeError):
        storage.write(iter([b"a", "text"]))
    assert tree() == []


def test_an_exception_from_the_producer_passes_through_unchanged_and_leaves_nothing():
    def producer():
        yield b"some data"
        raise RuntimeError("the producer failed")

    with pytest.raises(RuntimeError, match="the producer failed"):
        storage.write(producer())
    assert tree() == []


def test_the_413_of_an_upload_that_is_too_large_passes_through_and_leaves_nothing():
    def producer():
        yield b"some data"
        raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")

    with pytest.raises(HTTPException) as caught:
        storage.write(producer())
    assert caught.value.status_code == 413
    assert tree() == []


def test_an_os_error_from_the_producer_becomes_a_storage_error_and_leaves_nothing():
    def producer():
        yield b"some data"
        raise OSError(errno.EIO, "read error")

    with pytest.raises(storage.StorageError):
        storage.write(producer())
    assert tree() == []


def test_a_full_disk_is_a_storage_error_and_leaves_nothing(monkeypatch):
    real = os.write
    calls = []

    def full(fd, data):
        calls.append(fd)
        if len(calls) > 1:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(fd, data)

    with monkeypatch.context() as m:
        m.setattr(storage.os, "write", full)
        with pytest.raises(storage.StorageError):
            storage.write(iter([b"a" * 10, b"b" * 10]))
    assert tree() == []


def test_a_failed_link_is_a_storage_error_and_leaves_nothing(monkeypatch):
    def refused(*args, **kwargs):
        raise OSError(errno.EPERM, "Operation not permitted")

    with monkeypatch.context() as m:
        m.setattr(storage.os, "link", refused)
        with pytest.raises(storage.StorageError):
            stored()
    assert tree() == []


def test_a_failure_after_the_file_got_its_final_name_removes_that_name_too(monkeypatch):
    real_link, real_fsync = os.link, os.fsync
    linked = []

    def link(*args, **kwargs):
        real_link(*args, **kwargs)
        linked.append(True)

    def fsync(fd):
        if linked and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "I/O error")
        return real_fsync(fd)

    with monkeypatch.context() as m:
        m.setattr(storage.os, "link", link)
        m.setattr(storage.os, "fsync", fsync)
        with pytest.raises(storage.StorageError):
            stored()
    assert linked and tree() == []  # no key that nobody was told about, no .part


def test_a_failed_write_does_not_touch_other_files():
    keep = stored(b"keep me")
    before = tree()

    def producer():
        yield b"x"
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        storage.write(producer())
    assert tree() == before and contents(keep) == b"keep me"


def test_a_shard_directory_that_is_a_symlink_is_refused_on_write(tmp_path, keys):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, os.path.join(root(), "aa"))
    keys(key_in("aa", "1"))
    with pytest.raises(storage.StorageError):
        stored()
    assert list(elsewhere.iterdir()) == []


# --- keys are never overwritten -------------------------------------------------


def test_a_key_that_exists_is_never_overwritten(keys):
    taken = key_in("aa", "a")
    keys(taken, taken, key_in("bb", "b"))
    first = stored(b"first")
    second = stored(b"second")
    assert first == taken and second == key_in("bb", "b")
    assert contents(first) == b"first" and contents(second) == b"second"
    assert not any(name.endswith(".part") for name in tree())


def test_when_every_key_is_taken_nothing_is_overwritten_and_nothing_is_left(keys):
    taken = key_in("aa", "a")
    keys(*[taken] * 100)
    first = stored(b"first")
    before = tree()
    with pytest.raises(storage.StorageError):
        stored(b"second")
    assert tree() == before and contents(first) == b"first"


# --- read -----------------------------------------------------------------------


def test_read_gives_chunks_of_at_most_64_KiB_that_add_up_to_the_file():
    key = storage.write(iter(CHUNKS))
    pieces = list(storage.read(key))
    assert all(isinstance(p, bytes) and 0 < len(p) <= 64 * 1024 for p in pieces)
    assert len(pieces) >= 4 and b"".join(pieces) == DATA


def test_an_empty_file_reads_as_nothing():
    assert list(storage.read(storage.write(iter([])))) == []


def test_read_fails_on_the_first_iteration_not_on_the_call():
    generator = storage.read("0" * 32)  # nothing is opened yet
    with pytest.raises(storage.StorageError):
        next(generator)


def test_a_missing_file_and_a_missing_upload_directory_are_storage_errors(tmp_path, monkeypatch):
    with pytest.raises(storage.StorageError):
        list(storage.read("0" * 32))
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "nope"))
    with pytest.raises(storage.StorageError):
        list(storage.read("0" * 32))


@pytest.mark.parametrize(
    "bad",
    ["", "../x", "ab/" + "0" * 29, "A" * 32, "0" * 31, "0" * 33, "0" * 32 + ".part", "0" * 31 + "\x00", "0" * 32 + "\n",
     "..", "ab/../" + "0" * 27, None, 5, b"0" * 32],
)
def test_something_that_is_not_a_key_cannot_be_read(bad):
    with pytest.raises(storage.StorageError):
        list(storage.read(bad))


def test_a_symlink_in_place_of_the_file_is_refused(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"TOPSECRET")
    key = stored()
    os.remove(path_of(key))
    os.symlink(secret, path_of(key))
    got = []
    with pytest.raises(storage.StorageError):
        for piece in storage.read(key):
            got.append(piece)
    assert got == []


def test_a_symlink_in_place_of_the_shard_directory_is_refused(tmp_path):
    key = stored()
    elsewhere = tmp_path / "elsewhere"
    os.rename(os.path.join(root(), key[:2]), elsewhere)
    os.symlink(elsewhere, os.path.join(root(), key[:2]))
    with pytest.raises(storage.StorageError):
        list(storage.read(key))
    storage.delete(key)  # does not follow it either
    assert (elsewhere / key).read_bytes() == b"payload"


def test_a_fifo_is_refused_and_does_not_hang():
    key = key_in("cc", "c")
    os.mkdir(os.path.join(root(), "cc"), 0o700)
    os.mkfifo(path_of(key))
    with deadline():
        with pytest.raises(storage.StorageError):
            list(storage.read(key))


def test_a_directory_in_place_of_the_file_is_refused():
    key = key_in("dd", "d")
    os.makedirs(path_of(key))
    with pytest.raises(storage.StorageError):
        list(storage.read(key))


def descriptors():
    return len(os.listdir("/proc/self/fd"))


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="needs /proc")
def test_files_are_closed_after_a_complete_read_an_early_stop_and_a_failure():
    key = storage.write(iter(CHUNKS))
    before = descriptors()
    for _ in range(20):
        list(storage.read(key))
        generator = storage.read(key)
        next(generator)
        generator.close()
        generator = storage.read(key)
        next(generator)
        del generator
        with pytest.raises(storage.StorageError):
            list(storage.read("0" * 32))
    assert descriptors() == before


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="needs /proc")
def test_descriptors_are_not_leaked_by_writes_either(keys):
    before = descriptors()
    for _ in range(10):
        stored()
    taken = key_in("aa", "a")
    keys(*[taken] * 100)
    stored()
    with pytest.raises(storage.StorageError):
        stored()
    assert descriptors() == before


# --- delete ---------------------------------------------------------------------


def test_delete_removes_the_file_and_its_empty_shard_directory():
    key = stored()
    storage.delete(key)
    assert tree() == []
    with pytest.raises(storage.StorageError):
        list(storage.read(key))


def test_delete_keeps_the_shard_directory_while_another_key_is_in_it(keys):
    keys(key_in("aa", "1"), key_in("aa", "2"))
    first, second = stored(b"one"), stored(b"two")
    storage.delete(first)
    assert tree() == ["aa", "aa/" + second] and contents(second) == b"two"
    storage.delete(second)
    assert tree() == []


def test_delete_of_what_is_not_there_does_nothing():
    keep = stored()
    for key in ("0" * 32, keep[:2] + "0" * 30, keep):
        assert storage.delete(key) is None
    assert storage.delete(keep) is None  # twice
    assert tree() == []


@pytest.mark.parametrize("bad", ["", "../victim.txt", "does-not-exist", "A" * 32, "0" * 32 + ".part", None, 5, b"0" * 32])
def test_delete_of_something_that_is_not_a_key_does_nothing(tmp_path, monkeypatch, bad):
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"do not touch")
    inside = tmp_path / "uploads"
    inside.mkdir(mode=0o700)
    monkeypatch.setattr(config, "UPLOAD_DIR", str(inside))
    assert storage.delete(bad) is None
    assert victim.read_bytes() == b"do not touch"


def test_delete_with_a_missing_upload_directory_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "nope"))
    assert storage.delete("0" * 32) is None


def test_delete_removes_a_symlink_but_not_what_it_points_to(tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"still here")
    key = key_in("ee", "e")
    os.mkdir(os.path.join(root(), "ee"), 0o700)
    os.symlink(target, path_of(key))
    storage.delete(key)
    assert target.read_bytes() == b"still here" and not os.path.lexists(path_of(key))


def test_delete_does_not_raise_when_the_file_cannot_be_removed(monkeypatch, caplog):
    key = stored()

    def refused(*args, **kwargs):
        raise PermissionError(errno.EACCES, "Permission denied", "/secret/path")

    with monkeypatch.context() as m:
        m.setattr(storage.os, "unlink", refused)
        with caplog.at_level(logging.WARNING, logger="tcancy.storage"):
            assert storage.delete(key) is None
    assert "could not delete stored file" in caplog.text and "/secret/path" not in caplog.text
    assert contents(key) == b"payload"


# --- writers and deleters at the same time --------------------------------------


def test_writers_and_deleters_in_one_shard_do_not_trip_over_each_other(monkeypatch):
    monkeypatch.setattr(storage, "_new_key", lambda: "ab" + uuid.uuid4().hex[:30])  # one busy shard
    failures = []

    def worker():
        try:
            for _ in range(60):
                key = stored(b"data")
                assert contents(key) == b"data"
                storage.delete(key)
        except BaseException as e:  # noqa: BLE001
            failures.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads)
    assert failures == []
    assert tree() == []